const configuredApiBaseUrl = import.meta.env.VITE_API_BASE_URL

if (import.meta.env.PROD && !configuredApiBaseUrl) {
  throw new Error('VITE_API_BASE_URL must be set to the CropRetain API URL in production.')
}

const API_BASE_URL = configuredApiBaseUrl || 'http://localhost:8000'

function getToken() {
  return localStorage.getItem('cropretain_token')
}

// Previously this had NO client-side timeout at all: if the backend hung
// (e.g. a slow/unreachable upstream government API on the server side)
// the browser would sit on this fetch indefinitely with nothing to show
// the user but a spinner, until whatever happened server-side eventually
// resolved -- often minutes later. A request-level timeout means a slow
// backend surfaces as a fast, clear error the UI can react to (retry,
// show cached data, etc.) instead of an indefinite hang.
const DEFAULT_TIMEOUT_MS = 15000

async function request(path, { method = 'GET', body, auth = false, form = false, token = null, timeoutMs = DEFAULT_TIMEOUT_MS } = {}) {
  const headers = {}
  if (!form) headers['Content-Type'] = 'application/json'
  if (auth) {
    const t = token || getToken()
    if (t) headers['Authorization'] = `Bearer ${t}`
  }
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  let res
  try {
    res = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: form ? body : body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    })
  } catch (e) {
    if (e.name === 'AbortError') {
      throw new Error(`Request timed out after ${timeoutMs / 1000}s`)
    }
    throw e
  } finally {
    clearTimeout(timer)
  }
  if (!res.ok) {
    let detail = `Request failed (${res.status})`
    try {
      const errJson = await res.json()
      detail = errJson.detail || detail
    } catch (e) {}
    const err = new Error(detail)
    err.status = res.status   // lets callers distinguish e.g. 409 stale-round conflicts
    throw err
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  // Auth
  loginFarmer: (email, password) => {
    const form = new URLSearchParams()
    form.set('username', email)
    form.set('password', password)
    return request('/auth/login', { method: 'POST', body: form, form: true })
  },
  registerFarmer: (payload) => request('/auth/register/farmer', { method: 'POST', body: payload }),
  registerBuyer: (payload) => request('/auth/register/buyer', { method: 'POST', body: payload }),
  registerTransporter: (payload) => request('/auth/register/transporter', { method: 'POST', body: payload }),
  me: () => request('/auth/me', { auth: true }),

  // Transporter dashboard
  transporterAvailableRequests: () => request('/transporter/requests/available', { auth: true }),
  transporterMyRequests: () => request('/transporter/requests/mine', { auth: true }),
  transporterClaimRequest: (id) => request(`/transporter/requests/${id}/claim`, { method: 'POST', auth: true }),
  transporterRequestDetail: (id) => request(`/transporter/requests/${id}`, { auth: true }),
  transporterProfile: () => request('/transporter/profile', { auth: true }),
  updateTransporterProfile: (payload) => request('/transporter/profile', { method: 'PATCH', body: payload, auth: true }),

  // Negotiation -- shared endpoints, identity/role comes from the JWT so the
  // same calls work for the farmer's side and the transporter's side.
  listTransportOffers: (requestId) => request(`/transport/requests/${requestId}/offers`, { auth: true }),
  makeTransportOffer: (requestId, payload) =>
    request(`/transport/requests/${requestId}/offers`, { method: 'POST', body: payload, auth: true }),
  acceptTransportOffer: (requestId, offerId) =>
    request(`/transport/requests/${requestId}/offers/${offerId}/accept`, { method: 'POST', auth: true }),
  rejectTransportOffer: (requestId, offerId) =>
    request(`/transport/requests/${requestId}/offers/${offerId}/reject`, { method: 'POST', auth: true }),
  listTransportMessages: (requestId) => request(`/transport/requests/${requestId}/messages`, { auth: true }),
  sendTransportMessage: (requestId, message) =>
    request(`/transport/requests/${requestId}/messages`, { method: 'POST', body: { message }, auth: true }),
  updateTransportStatus: (requestId, status) =>
    request(`/transport/requests/${requestId}/transporter-status`, { method: 'POST', body: { status }, auth: true }),
  submitTransportReview: (requestId, payload) =>
    request(`/transport/requests/${requestId}/review`, { method: 'POST', body: payload, auth: true }),
  listTransportReviews: (requestId) => request(`/transport/requests/${requestId}/reviews`, { auth: true }),

  // Market
  getCrops: () => request('/market/crops'),
  getMarkets: () => request('/market/markets'),
  getSoilOptions: () => request('/soil/options'),
  soilAdvise: (payload) => request('/soil/advise', { method: 'POST', body: payload }),
  nearestMarket: (latitude, longitude) => request(`/market/nearest-market?latitude=${latitude}&longitude=${longitude}`),
  getFarmerWeather: () => request('/weather/farmer', { auth: true }),
  getWeatherByLocation: (latitude, longitude, location) => {
    const params = new URLSearchParams()
    if (latitude != null) params.set('latitude', latitude)
    if (longitude != null) params.set('longitude', longitude)
    if (location) params.set('location', location)
    return request(`/weather?${params.toString()}`)
  },
  getPrices: (crop, market, days = 30, includeDemo = false) => request(`/market/prices?crop=${encodeURIComponent(crop)}&market=${encodeURIComponent(market)}&days=${days}&include_demo=${includeDemo}`),
  compareMarkets: (crop, quantityKg, location) => request(`/market/compare?crop=${encodeURIComponent(crop)}&quantity_kg=${quantityKg}&location=${encodeURIComponent(location)}`),
  getLiveMarkets: (state = 'Chhattisgarh') => request(`/market/live-markets?state=${encodeURIComponent(state)}`),

  // Advisor
  advisorRecommend: (payload) => request('/advisor/recommend', { method: 'POST', body: payload }),

  // Forecast
  getForecast: (crop, market, includeDemo = false) => request(`/forecast?crop=${encodeURIComponent(crop)}&market=${encodeURIComponent(market)}&include_demo=${includeDemo}`),
  // ML forecast (separate route; see backend docs/ML_PRICE_FORECAST.md). includeSnapshot = explicit historical replay.
  getMlForecast: (crop, market, includeSnapshot = false) => request(`/forecast/ml?crop=${encodeURIComponent(crop)}&market=${encodeURIComponent(market)}&include_snapshot=${includeSnapshot}`),
  // Precomputed held-out-test analysis of the ML forecast (baselines, per-crop/state error, drivers).
  getMlAnalysis: () => request('/forecast/ml/analysis'),
  // Next-7-day STATEWIDE average forecast (separate model trained on state-level daily averages).
  getMlStateForecast: (crop, state) => request(`/forecast/ml/state?crop=${encodeURIComponent(crop)}&state=${encodeURIComponent(state)}`),
  // Recorded past prices for one crop/market (bundled history + live rows); days omitted = everything recorded; otherwise a window ending at the newest record.
  getPastPrices: (crop, market, days = null, scope = 'auto') => request(`/market/past-prices?crop=${encodeURIComponent(crop)}&market=${encodeURIComponent(market)}${days ? `&days=${days}` : ''}&scope=${scope}`),

  // Listings
  createListing: (payload) => request('/listings', { method: 'POST', body: payload, auth: true }),
  getListings: (params = {}) => {
    const qs = new URLSearchParams(params).toString()
    return request(`/listings${qs ? `?${qs}` : ''}`)
  },
  myListings: () => request('/listings/mine', { auth: true }),
  getListing: (id) => request(`/listings/${id}`),
  updateListingStatus: (id, status) => request(`/listings/${id}/status?new_status=${status}`, { method: 'PATCH', auth: true }),
  deleteListing: (id) => request(`/listings/${id}`, { method: 'DELETE', auth: true }),

  // Offers
  createOffer: (payload) => request('/offers', { method: 'POST', body: payload, auth: true }),
  offersForListing: (listingId) => request(`/offers/listing/${listingId}`, { auth: true }),
  offersForLot: (lotId) => request(`/offers/lot/${lotId}`, { auth: true }),
  myOffers: () => request('/offers/mine', { auth: true }),
  acceptOffer: (id) => request(`/offers/${id}/accept`, { method: 'PATCH', auth: true }),
  rejectOffer: (id) => request(`/offers/${id}/reject`, { method: 'PATCH', auth: true }),
  // Multi-round negotiation (buyer <-> farmer). Identity is derived server-side from the token.
  offersAwaitingMe: () => request('/offers/awaiting-me', { auth: true }),
  offerThread: (offerId) => request(`/offers/${offerId}`, { auth: true }),
  offerRounds: (offerId) => request(`/offers/${offerId}/rounds`, { auth: true }),
  counterOffer: (offerId, payload) => request(`/offers/${offerId}/counter`, { method: 'POST', body: payload, auth: true }),
  acceptOfferRound: (offerId, roundId) => request(`/offers/${offerId}/rounds/${roundId}/accept`, { method: 'POST', auth: true }),
  rejectOfferRound: (offerId, roundId) => request(`/offers/${offerId}/rounds/${roundId}/reject`, { method: 'POST', auth: true }),
  withdrawOffer: (offerId) => request(`/offers/${offerId}/withdraw`, { method: 'POST', auth: true }),

  // Matching
  matchBuyers: (listingId) => request(`/matching/listing/${listingId}`, { auth: true }),
  matchBuyersForLot: (lotId, topN = 5) => request(`/matching/lot/${lotId}?top_n=${topN}`, { auth: true }),

  // Logistics
  getVehicles: () => request('/logistics/vehicles'),
  farmPool: (payload) => request('/logistics/farmpool', { method: 'POST', body: payload }),

  // Profit
  profitSimulate: (payload) => request('/profit/simulate', { method: 'POST', body: payload }),
  profitCompare: (payload) => request('/profit/compare', { method: 'POST', body: payload }),

  // Group selling
  getGroupPools: (crop) => request(`/group-selling${crop ? `?crop=${encodeURIComponent(crop)}` : ''}`),
  joinGroupPool: (payload) => request('/group-selling/join', { method: 'POST', body: payload, auth: true }),

  // Notifications
  myNotifications: () => request('/notifications/mine', { auth: true }),
  markNotificationRead: (id) => request(`/notifications/${id}/read`, { method: 'PATCH', auth: true }),
  generateNotification: () => request('/notifications/generate', { method: 'POST', auth: true }),

  // Quality
  gradeQuality: (payload) => request('/quality/grade', { method: 'POST', body: payload }),
  analyzeQualityImage: (crop, file) => {
    const formData = new FormData()
    formData.append('crop', crop)
    formData.append('image', file)
    return request('/quality/analyze', { method: 'POST', body: formData, form: true })
  },

  // Assistant
  askAssistant: (payload) => request('/assistant/ask', { method: 'POST', body: payload }),
  assistantLanguages: () => request('/assistant/languages'),

  // Admin
  getImpact: (adminToken) => request('/admin/impact', { auth: true, token: adminToken }),
  getUserActivity: (adminToken) => request('/admin/user-activity', { auth: true, token: adminToken }),
  getRecentActivity: (adminToken, limit = 20) => request(`/admin/recent-activity?limit=${limit}`, { auth: true, token: adminToken }),
  getAdminUsers: (adminToken, { role, q } = {}) => {
    const params = new URLSearchParams()
    if (role) params.set('role', role)
    if (q) params.set('q', q)
    const qs = params.toString()
    return request(`/admin/users${qs ? `?${qs}` : ''}`, { auth: true, token: adminToken })
  },
  adminLogin: (username, password) => {
    const form = new URLSearchParams()
    form.set('username', username)
    form.set('password', password)
    return request('/auth/admin/login', { method: 'POST', body: form, form: true })
  },
  getDataSourceStatus: () => request('/market/data-source-status'),

  // Farmers/Buyers
  updateFarmerProfile: (payload) => request('/farmers/me', { method: 'PUT', body: payload, auth: true }),
  listBuyers: (crop) => request(`/buyers${crop ? `?crop=${encodeURIComponent(crop)}` : ''}`),

  // Lots (Phase 4)
  createLot: (payload) => request('/lots', { method: 'POST', body: payload, auth: true }),
  getLots: (params = {}) => { const qs = new URLSearchParams(params).toString(); return request(`/lots${qs ? `?${qs}` : ''}`) },
  myLots: () => request('/lots/mine', { auth: true }),
  getLot: (id) => request(`/lots/${id}`),
  updateLot: (id, payload) => request(`/lots/${id}`, { method: 'PATCH', body: payload, auth: true }),
  cancelLot: (id) => request(`/lots/${id}`, { method: 'DELETE', auth: true }),

  // Buyer Demands (Phase 1)
  createDemand: (payload) => request('/buyer-demands', { method: 'POST', body: payload, auth: true }),
  getDemands: (params = {}) => { const qs = new URLSearchParams(params).toString(); return request(`/buyer-demands${qs ? `?${qs}` : ''}`) },
  myDemands: () => request('/buyer-demands/mine', { auth: true }),
  getDemand: (id) => request(`/buyer-demands/${id}`),
  updateDemand: (id, payload) => request(`/buyer-demands/${id}`, { method: 'PATCH', body: payload, auth: true }),
  cancelDemand: (id) => request(`/buyer-demands/${id}/cancel`, { method: 'PATCH', auth: true }),
  demandMatches: (id) => request(`/buyer-demands/${id}/matches`, { auth: true }),

  // Buyer Verification (Phase 2)
  submitVerification: (payload) => request('/buyer-verification', { method: 'POST', body: payload, auth: true }),
  myVerification: () => request('/buyer-verification/me', { auth: true }),
  getBuyerVerification: (buyerId) => request(`/buyer-verification/${buyerId}`),
  getBuyerVerificationBadge: (buyerId) => request(`/buyer-verification/${buyerId}/badge`),
  adminListVerifications: (status = 'UNDER_REVIEW') => request(`/buyer-verification?status=${status}`, { auth: true }),
  adminApproveVerification: (buyerId, notes = '') => request(`/buyer-verification/${buyerId}/approve?notes=${encodeURIComponent(notes)}`, { method: 'PATCH', auth: true }),
  adminRejectVerification: (buyerId, reason) => request(`/buyer-verification/${buyerId}/reject?reason=${encodeURIComponent(reason)}`, { method: 'PATCH', auth: true }),

  // Transactions (Phase 10)
  myTransactions: () => request('/transactions/mine', { auth: true }),
  getTransaction: (id) => request(`/transactions/${id}`, { auth: true }),
  getTransactionTimeline: (id) => request(`/transactions/${id}/timeline`, { auth: true }),
  updateTransactionStatus: (id, status) => request(`/transactions/${id}/status`, { method: 'PATCH', body: { status }, auth: true }),
  adminListTransactions: (params = {}) => { const qs = new URLSearchParams(params).toString(); return request(`/transactions${qs ? `?${qs}` : ''}`, { auth: true }) },

  // Payments (Phase 11)
  myPayments: () => request('/payments/mine', { auth: true }),
  paymentForTransaction: (txnId) => request(`/payments/transaction/${txnId}`, { auth: true }),
  createPayment: (payload) => request('/payments', { method: 'POST', body: payload, auth: true }),
  initiatePayment: (id, method = 'UPI') => request(`/payments/${id}/initiate?payment_method=${encodeURIComponent(method)}`, { method: 'PATCH', auth: true }),
  confirmPaymentReceived: (id) => request(`/payments/${id}/confirm-received`, { method: 'PATCH', auth: true }),
  completeTransaction: (id) => request(`/payments/${id}/complete-transaction`, { method: 'PATCH', auth: true }),
  generateReceipt: (txnId) => request(`/receipts/transaction/${txnId}`, { method: 'POST', auth: true }),
  receiptForTransaction: (txnId) => request(`/receipts/transaction/${txnId}`, { auth: true }),
  verifyReceipt: (receiptId) => request(`/receipts/${receiptId}/verify`, { auth: true }),
  // Not run through request(): the endpoint returns a plain-text document
  // (Content-Disposition: attachment), not JSON, so request()'s res.json()
  // would fail on it. Fetches the raw text with the same auth header and
  // hands it back for the caller to save as a file client-side.
  downloadReceipt: async (receiptId) => {
    const token = getToken()
    const headers = {}
    if (token) headers['Authorization'] = `Bearer ${token}`
    const res = await fetch(`${API_BASE_URL}/receipts/${receiptId}/download`, { headers })
    if (!res.ok) {
      let detail = `Download failed (${res.status})`
      try { detail = (await res.json()).detail || detail } catch (e) {}
      throw new Error(detail)
    }
    return res.text()
  },

  // Grievances (Phase 13)
  raiseGrievance: (payload) => request('/grievances', { method: 'POST', body: payload, auth: true }),
  myGrievances: () => request('/grievances/mine', { auth: true }),
  getGrievance: (id) => request(`/grievances/${id}`, { auth: true }),
  updateGrievance: (id, payload) => request(`/grievances/${id}`, { method: 'PATCH', body: payload, auth: true }),
  adminListGrievances: (params = {}) => { const qs = new URLSearchParams(params).toString(); return request(`/grievances${qs ? `?${qs}` : ''}`, { auth: true }) },

  // Storage (Phase 6)
  getStorageFacilities: (params = {}) => { const qs = new URLSearchParams(params).toString(); return request(`/storage/facilities${qs ? `?${qs}` : ''}`) },
  getStorageFacility: (id) => request(`/storage/facilities/${id}`),
  estimateStorageCost: (facilityId, quantityKg, days) => request(`/storage/estimate?facility_id=${facilityId}&quantity_kg=${quantityKg}&days=${days}`),
  createStorageBooking: (payload) => request('/storage/bookings', { method: 'POST', body: payload, auth: true }),
  myStorageBookings: () => request('/storage/bookings/mine', { auth: true }),
  getStorageBooking: (id) => request(`/storage/bookings/${id}`, { auth: true }),
  cancelStorageBooking: (id) => request(`/storage/bookings/${id}/cancel`, { method: 'PATCH', auth: true }),

  // Transport (Phase 9)
  createTransportRequest: (payload) => request('/transport/requests', { method: 'POST', body: payload, auth: true }),
  myTransportRequests: () => request('/transport/requests/mine', { auth: true }),
  getTransportRequest: (id) => request(`/transport/requests/${id}`, { auth: true }),
  updateTransportStatus: (id, status, extra = {}) => request(`/transport/requests/${id}/status`, { method: 'PATCH', body: { status, ...extra }, auth: true }),
  cancelTransportRequest: (id) => request(`/transport/requests/${id}/cancel`, { method: 'PATCH', auth: true }),
  submitTransportQuote: (id, quotedPrice) => request(`/transport/requests/${id}/quote`, { method: 'POST', body: { quoted_price: quotedPrice }, auth: true }),
  counterTransportOffer: (id, counterPrice) => request(`/transport/requests/${id}/quote/counter-offer`, { method: 'POST', body: { counter_price: counterPrice }, auth: true }),
  acceptTransportQuote: (id) => request(`/transport/requests/${id}/quote/accept`, { method: 'POST', auth: true }),
  rejectTransportQuote: (id) => request(`/transport/requests/${id}/quote/reject`, { method: 'POST', auth: true }),
  getVehicleOptions: (quantityKg) => request(`/transport/vehicle-options${quantityKg ? `?quantity_kg=${quantityKg}` : ''}`),

  // Trip reviews (FarmPool / shared-logistics trust layer).
  // Distinct from the farmer<->buyer `ratings` endpoints above: these
  // attach to a TransportRequest and cover the transporter, the shared
  // journey, and the FPO/pool. Eligibility and the `verified` flag are
  // decided server-side -- the client never sends them.
  submitTripReview: (payload) => request('/trip-reviews', { method: 'POST', body: payload, auth: true }),
  tripReviewsForTrip: (transportRequestId) => request(`/trip-reviews/for-trip/${transportRequestId}`),
  myTripReviews: (transportRequestId) => request(`/trip-reviews/my/${transportRequestId}`, { auth: true }),

  // Ratings (Phase 14)
  rateAsBuyer: (payload) => request('/ratings/buyer-rates-farmer', { method: 'POST', body: payload, auth: true }),
  rateAsFarmer: (payload) => request('/ratings/farmer-rates-buyer', { method: 'POST', body: payload, auth: true }),
  ratingsForBuyer: (buyerId) => request(`/ratings/for-buyer/${buyerId}`),
  ratingsForFarmer: (farmerId) => request(`/ratings/for-farmer/${farmerId}`),
  myTransactionRating: (transactionId) => request(`/ratings/my-transaction/${transactionId}`, { auth: true }),

  // Arrivals + Selling Window (Phase 7 & 8)
  getArrivals: (crop, market, days = 14) => request(`/market/arrivals?crop=${encodeURIComponent(crop)}&market=${encodeURIComponent(market)}&days=${days}`),
  getSellingWindow: (crop, market, quantityKg, storageCostPerKgPerDay = 0.05) =>
    request(`/market/selling-window?crop=${encodeURIComponent(crop)}&market=${encodeURIComponent(market)}&quantity_kg=${quantityKg}&storage_cost_per_kg_per_day=${storageCostPerKgPerDay}`),

  // Buyer notifications (Phase 16)
  myBuyerNotifications: () => request('/notifications/buyer/mine', { auth: true }),
  markBuyerNotificationRead: (id) => request(`/notifications/buyer/${id}/read`, { method: 'PATCH', auth: true }),
  generateBuyerAlert: () => request('/notifications/buyer/generate', { method: 'POST', auth: true }),
}

export { API_BASE_URL, getToken }
