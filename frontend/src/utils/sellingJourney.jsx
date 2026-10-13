// The Selling Journey: derives a farmer's current stage from real, persisted
// application state (Lots + Transactions) -- never from UI interaction (page
// views, clicks, rendered components). See FarmerDashboard.jsx inspection
// notes for the exact state mapping this implements.
//
// Five stages:
//   01 ADD_PRODUCE      -- has the farmer created any lot at all?
//   02 MARKET_ANALYSIS  -- lot exists and is still being compared/offered on
//   03 FIND_BUYER       -- an accepted offer has become a real Transaction
//   04 CREATE_SHIP      -- transaction has progressed through logistics
//   05 PAYMENT_RECEIVED -- transaction has reached a paid/completed state
//
// `label` values below are translation KEYS, not display text -- this file
// is a plain module (not a component), so it can't call the t() hook
// itself. SellingJourney.jsx resolves each key via t() at render time, so
// stage labels re-render correctly on language switch. See
// sellingJourney.stage.* in en.json/hi.json/mr.json etc.
export const STAGES = [
  { key: 'ADD_PRODUCE', order: 1, label: 'sellingJourney.stage.addProduce' },
  { key: 'MARKET_ANALYSIS', order: 2, label: 'sellingJourney.stage.marketAnalysis' },
  { key: 'FIND_BUYER', order: 3, label: 'sellingJourney.stage.findBuyer' },
  { key: 'CREATE_SHIP', order: 4, label: 'sellingJourney.stage.createShip' },
  { key: 'PAYMENT_RECEIVED', order: 5, label: 'sellingJourney.stage.paymentReceived' },
]

const TXN_TERMINAL_PAID = ['PAYMENT_RECEIVED', 'COMPLETED']
const TXN_PAYMENT_IN_PROGRESS = ['PAYMENT_PENDING', 'PAYMENT_INITIATED']
const TXN_SHIPPING_IN_PROGRESS = [
  'ORDER_CONFIRMED', 'LOGISTICS_PENDING', 'LOGISTICS_CONFIRMED', 'PICKED_UP', 'IN_TRANSIT',
]
const TXN_SHIP_COMPLETE = ['DELIVERED', 'PAYMENT_PENDING', 'PAYMENT_INITIATED', 'PAYMENT_RECEIVED', 'COMPLETED']

/**
 * Derive the stage state (completed / current / upcoming) for a single
 * lot + its transaction (if any). Returns null if this lot shouldn't be
 * considered at all (defensive -- callers already filter).
 */
export function deriveJourneyForLot(lot, transaction) {
  const stageStatus = {} // key -> 'completed' | 'current' | 'upcoming'
  let currentKey = 'ADD_PRODUCE'

  // 01 Add Produce -- true the moment a lot object exists.
  stageStatus.ADD_PRODUCE = 'completed'

  // 02 Market Analysis
  const pastAnalysis = lot.status === 'UNDER_OFFER' || lot.status === 'SOLD' || Boolean(transaction)
  stageStatus.MARKET_ANALYSIS = pastAnalysis ? 'completed' : 'current'
  if (!pastAnalysis) currentKey = 'MARKET_ANALYSIS'

  // 03 Find Buyer
  const buyerFound = Boolean(transaction)
  stageStatus.FIND_BUYER = buyerFound ? 'completed' : (pastAnalysis ? 'current' : 'upcoming')
  if (pastAnalysis && !buyerFound) currentKey = 'FIND_BUYER'

  // 04 Create & Ship
  const shipComplete = transaction && TXN_SHIP_COMPLETE.includes(transaction.status)
  const shipInProgress = transaction && TXN_SHIPPING_IN_PROGRESS.includes(transaction.status)
  stageStatus.CREATE_SHIP = shipComplete ? 'completed' : (buyerFound ? 'current' : 'upcoming')
  if (buyerFound && !shipComplete) currentKey = 'CREATE_SHIP'

  // 05 Payment Received
  const paid = transaction && TXN_TERMINAL_PAID.includes(transaction.status)
  stageStatus.PAYMENT_RECEIVED = paid ? 'completed' : (shipComplete ? 'current' : 'upcoming')
  if (shipComplete && !paid) currentKey = 'PAYMENT_RECEIVED'
  if (paid) currentKey = 'PAYMENT_RECEIVED' // fully done -- journey "current" rests on the final stage

  const isFullyComplete = paid

  return {
    lot,
    transaction: transaction || null,
    stageStatus,
    currentStageKey: currentKey,
    isFullyComplete,
    // Attention priority (lower = more urgent), see selectFocusJourney():
    //   0 = an in-flight (non-terminal) transaction exists
    //   1 = no transaction yet, but a decision is pending (offer under review)
    //   2 = brand-new, undecided produce (still at Market Analysis)
    //   3 = fully completed sale (nothing left to do)
    priority: (() => {
      if (transaction && !isFullyComplete) return 0
      if (lot.status === 'UNDER_OFFER') return 1
      if (lot.status === 'AVAILABLE') return 2
      return 3
    })(),
    lastUpdated: (transaction && (transaction.updated_at || transaction.created_at)) || lot.created_at || lot.available_date,
  }
}

/**
 * Pick which lot the dashboard's journey should focus on, per the
 * attention-priority rule: active/in-flight sale > pending decision >
 * new/unsold produce > fully completed sale. Ties broken by most recently
 * updated. `transactions` should already be the farmer's full transaction
 * list; this matches each lot to its transaction via lot_id.
 */
export function selectFocusJourney(lots, transactions) {
  if (!lots || lots.length === 0) {
    return {
      lot: null,
      transaction: null,
      stageStatus: { ADD_PRODUCE: 'current', MARKET_ANALYSIS: 'upcoming', FIND_BUYER: 'upcoming', CREATE_SHIP: 'upcoming', PAYMENT_RECEIVED: 'upcoming' },
      currentStageKey: 'ADD_PRODUCE',
      isFullyComplete: false,
      priority: -1,
      lastUpdated: null,
    }
  }

  const txnByLotId = new Map()
  for (const t of transactions || []) {
    if (!t.lot_id) continue
    // A lot can only have one governing transaction at a time in practice
    // (accepting an offer marks the lot SOLD), but defensively prefer the
    // most recently updated if more than one is ever linked.
    const existing = txnByLotId.get(t.lot_id)
    if (!existing || new Date(t.updated_at || t.created_at) > new Date(existing.updated_at || existing.created_at)) {
      txnByLotId.set(t.lot_id, t)
    }
  }

  const derived = lots
    .filter(l => l.status !== 'CANCELLED')
    .map(l => deriveJourneyForLot(l, txnByLotId.get(l.id)))

  derived.sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority
    const aTime = a.lastUpdated ? new Date(a.lastUpdated).getTime() : 0
    const bTime = b.lastUpdated ? new Date(b.lastUpdated).getTime() : 0
    return bTime - aTime // most recent first
  })

  return derived[0]
}

// Like STAGES above, `title`/`description`/`ctaLabel` here are translation
// KEYS (not display text) for the same reason -- this is a plain module,
// not a component. SellingJourney.jsx resolves each via t(). See
// sellingJourney.destination.* in en.json/hi.json/mr.json etc.
export const NEXT_DESTINATION = {
  ADD_PRODUCE: {
    title: 'sellingJourney.destination.addProduce.title',
    description: 'sellingJourney.destination.addProduce.description',
    ctaLabel: 'sellingJourney.destination.addProduce.cta',
    ctaTo: '/lots',
  },
  MARKET_ANALYSIS: {
    title: 'sellingJourney.destination.marketAnalysis.title',
    description: 'sellingJourney.destination.marketAnalysis.description',
    ctaLabel: 'sellingJourney.destination.marketAnalysis.cta',
    ctaTo: '/best-option',
  },
  FIND_BUYER: {
    title: 'sellingJourney.destination.findBuyer.title',
    description: 'sellingJourney.destination.findBuyer.description',
    ctaLabel: 'sellingJourney.destination.findBuyer.cta',
    ctaTo: '/buyer-demands',
  },
  CREATE_SHIP: {
    title: 'sellingJourney.destination.createShip.title',
    description: 'sellingJourney.destination.createShip.description',
    ctaLabel: 'sellingJourney.destination.createShip.cta',
    ctaTo: null, // filled in with /transactions/:id by the caller, which knows the transaction id
  },
  PAYMENT_RECEIVED: {
    title: 'sellingJourney.destination.paymentReceived.title',
    description: 'sellingJourney.destination.paymentReceived.description',
    ctaLabel: 'sellingJourney.destination.paymentReceived.cta',
    ctaTo: null,
  },
}
