import React, { useEffect, useState } from 'react'
import { Warehouse, Snowflake, ShieldCheck, Search, CalendarRange, MapPin, CheckCircle2, AlertTriangle } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'
import { useI18n } from '../i18n/I18nContext'

const TYPE_KEYS = {
  WAREHOUSE: 'storage.type.WAREHOUSE',
  COLD_STORAGE: 'storage.type.COLD_STORAGE',
  FPO_STORAGE: 'storage.type.FPO_STORAGE',
  PRIVATE_STORAGE: 'storage.type.PRIVATE_STORAGE',
  GOVERNMENT_STORAGE: 'storage.type.GOVERNMENT_STORAGE',
}

const CROP_KEY_MAP = {
  Tomato: 'auth.crop.tomato',
  'Paddy (Rice)': 'auth.crop.paddyRice',
  Wheat: 'auth.crop.wheat',
  Potato: 'auth.crop.potato',
  Onion: 'auth.crop.onion',
  Soybean: 'auth.crop.soybean',
  Maize: 'auth.crop.maize',
  'Chana (Gram)': 'auth.crop.chanaGram',
  Groundnut: 'auth.crop.groundnut',
  Sugarcane: 'auth.crop.sugarcane',
}

function getLocalizedCropName(name, t) {
  if (!name) return name
  const key = CROP_KEY_MAP[name]
  return key ? t(key) : name
}

const TYPE_COLORS = {
  WAREHOUSE: 'blue',
  COLD_STORAGE: 'purple',
  FPO_STORAGE: 'green',
  PRIVATE_STORAGE: 'orange',
  GOVERNMENT_STORAGE: 'red',
}

const BOOKING_STATUS_COLORS = {
  REQUESTED: 'blue',
  CONFIRMED: 'green',
  ACTIVE: 'purple',
  COMPLETED: 'gray',
  CANCELLED: 'red',
}

export default function Storage() {
  const { user, role } = useAuth()
  const { t } = useI18n()
  const [facilities, setFacilities] = useState([])
  const [bookings, setBookings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [activeTab, setActiveTab] = useState('browse') // browse | my-bookings
  const [cropFilter, setCropFilter] = useState('')
  const [typeFilter, setTypeFilter] = useState('')
  const [selectedFacility, setSelectedFacility] = useState(null)
  const [showBookingForm, setShowBookingForm] = useState(false)
  const [bookingForm, setBookingForm] = useState({
    quantity_kg: '',
    start_date: '',
    end_date: '',
    lot_id: '',
  })
  const [estimatedCost, setEstimatedCost] = useState(null)
  const [booking, setBooking] = useState(false)
  const [bookingSuccess, setBookingSuccess] = useState('')
  const [crops, setCrops] = useState([])

  useEffect(() => {
    api.getCrops().then(setCrops).catch(() => {})
    loadFacilities()
    if (role === 'farmer') loadBookings()
  }, [role])

  async function loadFacilities() {
    setLoading(true)
    try {
      const params = {}
      if (cropFilter) params.crop = cropFilter
      if (typeFilter) params.facility_type = typeFilter
      const data = await api.getStorageFacilities(params)
      setFacilities(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function loadBookings() {
    try {
      const data = await api.myStorageBookings()
      setBookings(data)
    } catch (e) {}
  }

  async function estimateCost() {
    if (!selectedFacility || !bookingForm.quantity_kg || !bookingForm.start_date || !bookingForm.end_date) return
    try {
      const start = new Date(bookingForm.start_date)
      const end = new Date(bookingForm.end_date)
      const days = Math.max(Math.ceil((end - start) / (1000 * 60 * 60 * 24)), 1)
      const data = await api.estimateStorageCost(selectedFacility.id, bookingForm.quantity_kg, days)
      setEstimatedCost(data)
    } catch (e) {}
  }

  async function submitBooking(e) {
    e.preventDefault()
    if (!selectedFacility) return
    setBooking(true)
    try {
      await api.createStorageBooking({
        storage_facility_id: selectedFacility.id,
        quantity_kg: parseFloat(bookingForm.quantity_kg),
        start_date: bookingForm.start_date,
        end_date: bookingForm.end_date || null,
        lot_id: bookingForm.lot_id ? parseInt(bookingForm.lot_id) : null,
      })
      setBookingSuccess(t('storage.bookingRequestedAt', { name: selectedFacility.name }))
      setShowBookingForm(false)
      setSelectedFacility(null)
      loadBookings()
      setActiveTab('my-bookings')
    } catch (e) {
      setError(e.message)
    } finally {
      setBooking(false)
    }
  }

  async function cancelBooking(id) {
    if (!window.confirm(t('storage.cancelConfirm'))) return
    try {
      await api.cancelStorageBooking(id)
      loadBookings()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-1">
        <Warehouse size={22} className="text-forest" />
        <h1 className="font-display text-3xl font-bold">{t('storage.title')}</h1>
      </div>
      <p className="text-ink/60 dark:text-paper/60 mb-1">{t('storage.subtitle')}</p>
      <p className="text-xs text-amber-600 dark:text-amber-400 mb-6 inline-flex items-center gap-2">
        <AlertTriangle size={14} /> {t('storage.illustrativeNotice')}
      </p>

      {bookingSuccess && (
        <div className="mb-4 p-3 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-700 rounded-lg text-emerald-700 dark:text-emerald-300 text-sm inline-flex items-center gap-2">
          <CheckCircle2 size={16} /> {bookingSuccess}
        </div>
      )}

      {/* Tabs */}
      {role === 'farmer' && (
        <div className="flex gap-2 mb-6">
          {['browse', 'my-bookings'].map(tab => (
            <button key={tab} onClick={() => setActiveTab(tab)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                activeTab === tab
                  ? 'bg-forest text-paper'
                  : 'bg-white dark:bg-white/5 border border-black/10 dark:border-white/10 text-ink/70 dark:text-paper/70 hover:bg-black/5'
              }`}>
              {tab === 'browse' ? <span className="inline-flex items-center gap-2"><Search size={14} /> {t('storage.browseStorage')}</span> : <span className="inline-flex items-center gap-2"><CalendarRange size={14} /> {t('storage.myBookings')}</span>}
            </button>
          ))}
        </div>
      )}

      {activeTab === 'browse' && (
        <>
          {/* Filters */}
          <div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-4 mb-6 flex flex-wrap gap-3 items-end">
            <div>
              <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.crop')}</label>
              <select value={cropFilter} onChange={e => setCropFilter(e.target.value)}
                className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper">
                <option value="">{t('storage.allCrops')}</option>
                {crops.map(c => <option key={c.name} value={c.name}>{c.emoji} {getLocalizedCropName(c.name, t)}</option>)}
              </select>
            </div>
            <div>
              <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('storage.typeLabel')}</label>
              <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)}
                className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper">
                <option value="">{t('storage.allTypes')}</option>
                {Object.entries(TYPE_KEYS).map(([k, key]) => <option key={k} value={k}>{t(key)}</option>)}
              </select>
            </div>
            <button onClick={loadFacilities}
              className="bg-forest text-paper px-4 py-2 rounded-lg text-sm font-semibold hover:bg-forest/90">
              {t('ui.search')}
            </button>
          </div>

          {loading ? <LoadingSpinner /> : error ? (
            <div className="text-red-500 text-sm">{error}</div>
          ) : facilities.length === 0 ? (
            <div className="text-center py-12 text-ink/40 dark:text-paper/40">
              <p className="text-4xl mb-3">🏭</p>
              <p className="font-medium">{t('storage.noFacilitiesFound')}</p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {facilities.map(f => (
                <div key={f.id} className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-5 shadow-card hover:shadow-lg transition-shadow">
                  <div className="flex items-start justify-between mb-3">
                    <div>
                      <h3 className="font-bold text-ink dark:text-paper">{f.name}</h3>
                      <p className="text-xs text-ink/50 dark:text-paper/50 mt-0.5 inline-flex items-center gap-1"><MapPin size={12} /> {f.location}</p>
                    </div>
                    <Badge color={TYPE_COLORS[f.facility_type] || 'gray'} size="sm">
                      {t(TYPE_KEYS[f.facility_type] || 'storage.typeUnknown')}
                    </Badge>
                  </div>

                  {f.is_demo && (
                    <p className="text-xs text-amber-600 dark:text-amber-400 mb-2 inline-flex items-center gap-1"><AlertTriangle size={12} /> {t('storage.demoFacility')}</p>
                  )}

                  <div className="grid grid-cols-2 gap-2 mb-3 text-sm">
                    <div className="bg-black/3 dark:bg-white/5 rounded-lg p-2">
                      <p className="text-xs text-ink/50 dark:text-paper/50">{t('storage.totalCapacity')}</p>
                      <p className="font-semibold">{(f.capacity_kg / 1000).toFixed(0)}t</p>
                    </div>
                    <div className="bg-black/3 dark:bg-white/5 rounded-lg p-2">
                      <p className="text-xs text-ink/50 dark:text-paper/50">{t('storage.available')}</p>
                      <p className="font-semibold text-emerald-600">{(f.available_capacity_kg / 1000).toFixed(0)}t</p>
                    </div>
                    <div className="bg-black/3 dark:bg-white/5 rounded-lg p-2">
                      <p className="text-xs text-ink/50 dark:text-paper/50">{t('storage.rate')}</p>
                      <p className="font-semibold">₹{f.price_per_kg_per_day}/kg/day</p>
                    </div>
                    <div className="bg-black/3 dark:bg-white/5 rounded-lg p-2">
                      <p className="text-xs text-ink/50 dark:text-paper/50">{t('storage.utilised')}</p>
                      <p className="font-semibold">{f.utilisation_pct}%</p>
                    </div>
                  </div>

                  {/* Utilisation bar */}
                  <div className="mb-3">
                    <div className="h-1.5 bg-black/10 dark:bg-white/10 rounded-full overflow-hidden">
                      <div className="h-full bg-forest rounded-full" style={{ width: `${f.utilisation_pct}%` }} />
                    </div>
                  </div>

                  {f.temperature_controlled && (
                    <p className="text-xs text-blue-600 dark:text-blue-400 mb-2 inline-flex items-center gap-1"><Snowflake size={12} /> {t('storage.temperatureControlled')}</p>
                  )}

                  {f.crop_types?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mb-3">
                      {f.crop_types.slice(0, 4).map(c => (
                        <span key={c} className="text-xs bg-forest/10 text-forest px-2 py-0.5 rounded-full">{getLocalizedCropName(c, t)}</span>
                      ))}
                      {f.crop_types.length > 4 && <span className="text-xs text-ink/40">+{f.crop_types.length - 4}</span>}
                    </div>
                  )}

                  {role === 'farmer' && (
                    <button
                      onClick={() => { setSelectedFacility(f); setShowBookingForm(true); setEstimatedCost(null) }}
                      className="w-full mt-2 bg-forest text-paper py-2 rounded-lg text-sm font-semibold hover:bg-forest/90 transition-colors">
                      {t('storage.bookStorage')}
                    </button>
                  )}
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {activeTab === 'my-bookings' && role === 'farmer' && (
        bookings.length === 0 ? (
          <div className="text-center py-12 text-ink/40 dark:text-paper/40">
            <p className="text-4xl mb-3">📋</p>
            <p className="font-medium">{t('storage.noBookingsYet')}</p>
            <button onClick={() => setActiveTab('browse')}
              className="mt-3 text-forest font-semibold text-sm">{t('storage.browseFacilities')} →</button>
          </div>
        ) : (
          <div className="space-y-4">
            {bookings.map(b => (
              <div key={b.id} className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-5">
                <div className="flex items-start justify-between">
                  <div>
                    <h3 className="font-bold">{b.facility_name || t('storage.storageFacility')}</h3>
                    <p className="text-xs text-ink/50 dark:text-paper/50">{b.facility_location} • {t(TYPE_KEYS[b.facility_type] || 'storage.typeUnknown')}</p>
                    {b.is_demo_facility && <p className="text-xs text-amber-500">⚠️ {t('storage.demoFacility')}</p>}
                  </div>
                  <Badge color={BOOKING_STATUS_COLORS[b.status] || 'gray'} size="sm">{t(`storage.bookingStatus.${b.status}`)}</Badge>
                </div>
                <div className="mt-3 grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm">
                  <div><p className="text-xs text-ink/50 dark:text-paper/50">{t('grievance.category.QUANTITY')}</p><p className="font-semibold">{b.quantity_kg} kg</p></div>
                  <div><p className="text-xs text-ink/50 dark:text-paper/50">{t('storage.from')}</p><p className="font-semibold">{b.start_date}</p></div>
                  <div><p className="text-xs text-ink/50 dark:text-paper/50">{t('storage.to')}</p><p className="font-semibold">{b.end_date || '—'}</p></div>
                  <div><p className="text-xs text-ink/50 dark:text-paper/50">{t('storage.estCost')}</p><p className="font-semibold">{b.estimated_cost ? `₹${b.estimated_cost.toLocaleString('en-IN')}` : '—'}</p></div>
                </div>
                {['REQUESTED', 'CONFIRMED'].includes(b.status) && (
                  <button onClick={() => cancelBooking(b.id)}
                    className="mt-3 text-red-500 text-xs font-semibold hover:underline">
                    {t('storage.cancelBooking')}
                  </button>
                )}
              </div>
            ))}
          </div>
        )
      )}

      {/* Booking Modal */}
      {showBookingForm && selectedFacility && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-900 rounded-2xl p-6 max-w-md w-full shadow-2xl">
            <h3 className="font-bold text-xl mb-1">{t('storage.bookStorage')}</h3>
            <p className="text-ink/60 dark:text-paper/60 text-sm mb-4">{selectedFacility.name} — {selectedFacility.location}</p>

            {selectedFacility.is_demo && (
              <p className="text-xs text-amber-600 mb-4 p-2 bg-amber-50 dark:bg-amber-900/20 rounded-lg">
                ⚠️ {t('storage.demoFacilityNotice')}
              </p>
            )}

            <form onSubmit={submitBooking} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('storage.quantityKgRequired')}</label>
                <input type="number" min="1" max={selectedFacility.available_capacity_kg}
                  value={bookingForm.quantity_kg} onChange={e => setBookingForm(f => ({ ...f, quantity_kg: e.target.value }))}
                  required className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
                <p className="text-xs text-ink/40 mt-0.5">{t('storage.availableAmount', { amount: selectedFacility.available_capacity_kg.toLocaleString('en-IN') })}</p>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('storage.startDateRequired')}</label>
                  <input type="date" value={bookingForm.start_date}
                    onChange={e => setBookingForm(f => ({ ...f, start_date: e.target.value }))}
                    required className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('storage.endDate')}</label>
                  <input type="date" value={bookingForm.end_date}
                    onChange={e => setBookingForm(f => ({ ...f, end_date: e.target.value }))}
                    className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('storage.lotIdOptional')}</label>
                <input type="number" value={bookingForm.lot_id}
                  onChange={e => setBookingForm(f => ({ ...f, lot_id: e.target.value }))}
                  placeholder={t('storage.linkToLot')}
                  className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
              </div>

              {bookingForm.quantity_kg && bookingForm.start_date && bookingForm.end_date && (
                <button type="button" onClick={estimateCost}
                  className="text-forest text-sm font-semibold hover:underline">
                  {t('storage.calculateEstimatedCost')}
                </button>
              )}

              {estimatedCost && (
                <div className="p-3 bg-forest/10 rounded-lg text-sm">
                  <p className="font-semibold text-forest">{t('storage.estimatedCostValue', { cost: estimatedCost.estimated_cost?.toLocaleString('en-IN') })}</p>
                  <p className="text-xs text-ink/50 dark:text-paper/50">
                    {t('storage.costBreakdown', { quantity: estimatedCost.quantity_kg, rate: estimatedCost.price_per_kg_per_day, days: estimatedCost.days })}
                  </p>
                </div>
              )}

              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => { setShowBookingForm(false); setSelectedFacility(null) }}
                  className="flex-1 border border-black/10 dark:border-white/15 py-2 rounded-lg text-sm font-semibold">
                  {t('cancel')}
                </button>
                <button type="submit" disabled={booking}
                  className="flex-1 bg-forest text-paper py-2 rounded-lg text-sm font-semibold disabled:opacity-60">
                  {booking ? t('storage.bookingInProgress') : t('storage.requestBooking')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
