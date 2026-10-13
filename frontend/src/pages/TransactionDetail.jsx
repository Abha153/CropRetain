import React, { useEffect, useState, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import { useI18n } from '../i18n/I18nContext'
import { formatTimestamp as fmt } from '../utils/datetime'

const STATUS_TONE = {
  OFFER_CREATED: 'neutral', OFFER_ACCEPTED: 'info', ORDER_CONFIRMED: 'info',
  LOGISTICS_PENDING: 'warning', LOGISTICS_CONFIRMED: 'info', PICKED_UP: 'marigold',
  IN_TRANSIT: 'marigold', DELIVERED: 'success', PAYMENT_PENDING: 'warning',
  PAYMENT_INITIATED: 'info', PAYMENT_RECEIVED: 'success', COMPLETED: 'forest',
}
const PAYMENT_STATUS_TONE = {
  PENDING: 'neutral', DUE: 'warning', INITIATED: 'info',
  PAID: 'success', FAILED: 'warning', CANCELLED: 'neutral', DISPUTED: 'warning'
}

// Next action a user can take from each status
const FARMER_NEXT = {
  LOGISTICS_CONFIRMED: 'PICKED_UP',
  PICKED_UP: 'IN_TRANSIT',
  PAYMENT_RECEIVED: 'COMPLETED',
}
const BUYER_NEXT = {
  OFFER_ACCEPTED: 'ORDER_CONFIRMED',
  IN_TRANSIT: 'DELIVERED',
  DELIVERED: 'PAYMENT_PENDING',
  PAYMENT_PENDING: 'PAYMENT_INITIATED',
}

function Timeline({ events }) {
  const { t } = useI18n()
  return (
    <div className="space-y-0">
      {events.map((e, i) => (
        <div key={e.id} className="flex gap-3">
          <div className="flex flex-col items-center">
            <div className={`w-3 h-3 rounded-full mt-1 flex-shrink-0 ${i === events.length - 1 ? 'bg-forest' : 'bg-marigold'}`} />
            {i < events.length - 1 && <div className="w-0.5 bg-black/10 dark:bg-white/10 flex-1 my-1" />}
          </div>
          <div className="pb-4">
            <div className="text-sm font-semibold">{t(`transaction.status.${e.event_type}`)}</div>
            {e.description && <div className="text-xs text-ink/60 dark:text-paper/60">{e.description}</div>}
            <div className="text-xs text-ink/40 dark:text-paper/40 mt-0.5">{fmt(e.created_at)}</div>
          </div>
        </div>
      ))}
    </div>
  )
}


function PaymentPanel({ txnId, role, onUpdated }) {
  const { t } = useI18n()
  const [payment, setPayment] = useState(undefined)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const load = useCallback(() => {
    api.paymentForTransaction(txnId).then(setPayment).catch(() => setPayment(null))
  }, [txnId])

  useEffect(() => { load() }, [load])

  // Payment status tracking, not payment processing. CropRetain records the
  // agreed payment lifecycle (PENDING -> INITIATED -> PAID); it does not
  // move money and is not integrated with a payment gateway. The buyer
  // marks payment as initiated here, and the farmer confirms receipt --
  // both are server-timestamped by the backend, never by the client.
  async function payNow() {
    setBusy(true); setError('')
    try {
      let p = payment
      if (!p) {
        p = await api.createPayment({ transaction_id: txnId })
      }
      await api.initiatePayment(p.id)
      setPayment(await api.paymentForTransaction(txnId))
      onUpdated()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function confirmReceived() {
    if (!payment) return
    setBusy(true); setError('')
    try {
      await api.confirmPaymentReceived(payment.id)
      load(); onUpdated()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function completeTransaction() {
    if (!payment) return
    setBusy(true); setError('')
    try {
      await api.completeTransaction(payment.id)
      load(); onUpdated()
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (payment === undefined) return <div className="text-xs text-ink/50">{t('transactionDetail.loadingPayment')}</div>

  return (
    <div className="space-y-3">
      {error && <div className="text-xs text-red-600">{error}</div>}
      {payment ? (
        <div className="space-y-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">₹{payment.amount.toLocaleString('en-IN')}</span>
            <Badge tone={PAYMENT_STATUS_TONE[payment.payment_status] || 'neutral'}>{t(`payment.status.${payment.payment_status}`)}</Badge>
          </div>
          {payment.payment_reference && (
            <div className="text-xs text-ink/50 font-mono-data">{t('transactionDetail.ref', { ref: payment.payment_reference })}</div>
          )}
          {payment.payment_status === 'PAID' && (
            <div className="text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 rounded px-2 py-1">
              {t('transactionDetail.paymentSuccessful')}<br />₹{payment.amount.toLocaleString('en-IN')}
            </div>
          )}
          {payment.payment_status === 'FAILED' && (
            <div className="text-xs text-red-600 bg-red-50 dark:bg-red-950/30 rounded px-2 py-1">
              {t('transactionDetail.paymentFailed')}
            </div>
          )}
          {payment.payment_status === 'CANCELLED' && (
            <div className="text-xs text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded px-2 py-1">
              {t('transactionDetail.paymentCancelled')}
            </div>
          )}
          {payment.is_demo && (
            <div className="text-xs text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 rounded px-2 py-1">
              {t('transactionDetail.demoPaymentNotice')}
            </div>
          )}
          {payment.payment_due_date && (
            <div className="text-xs text-ink/50">{t('transactionDetail.due', { date: payment.payment_due_date })}</div>
          )}
          <div className="text-xs space-y-1">
            {payment.initiated_at && <div>{t('transactionDetail.initiated', { date: fmt(payment.initiated_at) })}</div>}
            {payment.received_at && <div>{t('transactionDetail.received', { date: fmt(payment.received_at) })}</div>}
          </div>
          {/* Buyer: initiate if pending/due */}
          {role === 'buyer' && ['PENDING', 'DUE', 'FAILED', 'CANCELLED', 'INITIATED'].includes(payment.payment_status) && (
            <button onClick={payNow} disabled={busy}
              className="w-full text-sm bg-forest text-paper font-semibold rounded-lg py-2 disabled:opacity-60">
              {busy ? t('transactionDetail.recording') : t('transactionDetail.markPaymentInitiated')}
            </button>
          )}
          {/* Farmer: confirm received if initiated */}
          {role === 'farmer' && payment.is_demo && payment.payment_status === 'INITIATED' && (
            <button onClick={confirmReceived} disabled={busy}
              className="w-full text-sm bg-forest text-paper font-semibold rounded-lg py-2 disabled:opacity-60">
              {busy ? t('transactionDetail.confirming') : t('transactionDetail.confirmPaymentReceivedDemo')}
            </button>
          )}
          {/* Farmer: complete transaction after payment received */}
          {role === 'farmer' && payment.payment_status === 'PAID' && (
            <button onClick={completeTransaction} disabled={busy}
              className="w-full text-sm bg-marigold text-ink font-semibold rounded-lg py-2 disabled:opacity-60">
              {busy ? t('transactionDetail.completing') : t('transactionDetail.markComplete')}
            </button>
          )}
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-ink/50 dark:text-paper/50">{t('transactionDetail.noPaymentYet')}</p>
          {role === 'buyer' && (
            <button onClick={payNow} disabled={busy}
              className="w-full text-sm bg-forest text-paper font-semibold rounded-lg py-2 disabled:opacity-60">
              {busy ? t('transactionDetail.recording') : t('transactionDetail.markPaymentInitiated')}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

const RECEIPTABLE_STATUSES = ['COMPLETED', 'PAYMENT_RECEIVED', 'DELIVERED']

// Priority 9 -- UI for the receipt + SHA-256 integrity backend that
// already existed (POST/GET /receipts/transaction/{id}, GET /receipts/
// {id}/verify, GET /receipts/{id}/download). This panel only calls those
// endpoints; it never computes or displays a hash it generated itself --
// "verified" always means the backend recomputed and compared it.
function ReceiptPanel({ txnId, status }) {
  const { t } = useI18n()
  const [receipt, setReceipt] = useState(undefined) // undefined = loading, null = none yet
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [verification, setVerification] = useState(null) // {valid, ...} | null

  const load = useCallback(() => {
    api.receiptForTransaction(txnId).then(setReceipt).catch(() => setReceipt(null))
  }, [txnId])

  useEffect(() => { load() }, [load])

  async function generate() {
    setBusy(true); setError(''); setVerification(null)
    try {
      const r = await api.generateReceipt(txnId)
      setReceipt(r)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function download() {
    if (!receipt) return
    setBusy(true); setError('')
    try {
      const text = await api.downloadReceipt(receipt.receipt_id)
      const blob = new Blob([text], { type: 'text/plain' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${receipt.receipt_id}.txt`
      document.body.appendChild(a)
      a.click()
      a.remove()
      URL.revokeObjectURL(url)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  async function verify() {
    if (!receipt) return
    setBusy(true); setError('')
    try {
      const result = await api.verifyReceipt(receipt.receipt_id)
      setVerification(result)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }

  if (receipt === undefined) return <div className="text-xs text-ink/50">{t('common.loading')}</div>

  if (!RECEIPTABLE_STATUSES.includes(status) && !receipt) {
    return <p className="text-sm text-ink/50 dark:text-paper/50">{t('transactionDetail.receiptNotYetEligible')}</p>
  }

  return (
    <div className="space-y-3">
      {error && <div className="text-xs text-red-600">{error}</div>}
      {receipt ? (
        <div className="space-y-2">
          <div className="text-xs font-mono-data text-ink/70 dark:text-paper/70">{t('transactionDetail.receiptId')}: {receipt.receipt_id}</div>
          <div className="text-xs text-ink/50 dark:text-paper/50">{t('transactionDetail.generatedAt')}: {fmt(receipt.generated_at)}</div>
          <div className="text-[11px] font-mono-data break-all text-ink/40 dark:text-paper/40">
            SHA-256: {receipt.hash_value}
          </div>
          <div className="flex gap-2 flex-wrap">
            <button onClick={download} disabled={busy}
              className="text-sm bg-forest text-paper font-semibold rounded-lg py-2 px-3 disabled:opacity-60">
              {t('transactionDetail.downloadReceipt')}
            </button>
            <button onClick={verify} disabled={busy}
              className="text-sm border border-black/10 dark:border-white/15 font-semibold rounded-lg py-2 px-3 disabled:opacity-60">
              {busy ? t('transactionDetail.verifying') : t('transactionDetail.verifyIntegrity')}
            </button>
          </div>
          {verification && (
            verification.integrity_verified ? (
              <div className="text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 rounded px-2 py-1.5">
                ✅ {t('transactionDetail.receiptVerified')}
              </div>
            ) : (
              <div className="text-xs text-red-600 bg-red-50 dark:bg-red-950/30 rounded px-2 py-1.5">
                ❌ {t('transactionDetail.receiptMismatch')}
              </div>
            )
          )}
          <p className="text-[11px] text-ink/40 dark:text-paper/40">{receipt.note}</p>
        </div>
      ) : (
        <div className="space-y-2">
          <p className="text-sm text-ink/50 dark:text-paper/50">{t('transactionDetail.noReceiptYet')}</p>
          <button onClick={generate} disabled={busy}
            className="w-full text-sm bg-forest text-paper font-semibold rounded-lg py-2 disabled:opacity-60">
            {busy ? t('transactionDetail.generating') : t('transactionDetail.generateReceipt')}
          </button>
        </div>
      )}
    </div>
  )
}

function GrievancePanel({ txnId, role }) {
  const { t } = useI18n()
  const [grievances, setGrievances] = useState(null)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ category: 'PAYMENT', description: '', priority: 'MEDIUM' })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  const CATEGORIES = ['PAYMENT', 'QUALITY', 'QUANTITY', 'PRICE', 'DELIVERY', 'LOGISTICS', 'OTHER']
  const PRIORITIES = ['LOW', 'MEDIUM', 'HIGH']
  const STATUS_TONE_G = { OPEN: 'warning', UNDER_REVIEW: 'info', WAITING_FOR_EVIDENCE: 'warning', RESOLVED: 'success', REJECTED: 'neutral', CLOSED: 'neutral' }

  useEffect(() => {
    api.myGrievances().then(all => {
      setGrievances(all.filter(g => g.transaction_id === txnId))
    }).catch(() => setGrievances([]))
  }, [txnId])

  async function submit(e) {
    e.preventDefault()
    if (!form.description.trim()) { setError(t('transactionDetail.pleaseDescribeIssue')); return }
    setSubmitting(true); setError('')
    try {
      await api.raiseGrievance({
        transaction_id: txnId,
        category: form.category,
        description: form.description,
        priority: form.priority,
      })
      setSuccess(t('transactionDetail.grievanceRaised'))
      setShowForm(false)
      const all = await api.myGrievances()
      setGrievances(all.filter(g => g.transaction_id === txnId))
    } catch (e) { setError(e.message) } finally { setSubmitting(false) }
  }

  return (
    <div className="space-y-3">
      {success && <div className="text-xs text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 rounded px-2 py-1">{success}</div>}
      {error && <div className="text-xs text-red-600">{error}</div>}

      {grievances === null ? (
        <div className="text-xs text-ink/50">{t('common.loading')}</div>
      ) : grievances.length > 0 ? (
        <div className="space-y-2">
          {grievances.map(g => (
            <div key={g.id} className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-xs">
              <div className="flex items-center justify-between mb-1">
                <span className="font-semibold">{t(`grievance.category.${g.category}`)}</span>
                <Badge tone={STATUS_TONE_G[g.status] || 'neutral'}>{t(`grievance.status.${g.status}`)}</Badge>
              </div>
              <p className="text-ink/60 dark:text-paper/60">{g.description}</p>
              {g.resolution && (
                <div className="mt-1 text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/30 rounded px-1.5 py-0.5">
                  {t('transactionDetail.resolution', { resolution: g.resolution })}
                </div>
              )}
              <div className="text-ink/40 mt-1">{fmt(g.created_at)}</div>
            </div>
          ))}
        </div>
      ) : (
        <p className="text-xs text-ink/50 dark:text-paper/50">{t('transactionDetail.noGrievances')}</p>
      )}

      {!showForm ? (
        <button onClick={() => setShowForm(true)}
          className="w-full text-sm border border-red-300 dark:border-red-800 text-red-600 dark:text-red-400 font-semibold rounded-lg py-2 hover:bg-red-50 dark:hover:bg-red-950/30">
          {t('transactionDetail.raiseDispute')}
        </button>
      ) : (
        <form onSubmit={submit} className="space-y-2 border border-red-200 dark:border-red-900 rounded-lg p-3">
          <div className="flex gap-2">
            <select value={form.category} onChange={e => setForm(f => ({ ...f, category: e.target.value }))}
              className="flex-1 border border-black/10 dark:border-white/15 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-white/5 dark:text-paper">
              {CATEGORIES.map(c => <option key={c} value={c}>{t(`grievance.category.${c}`)}</option>)}
            </select>
            <select value={form.priority} onChange={e => setForm(f => ({ ...f, priority: e.target.value }))}
              className="border border-black/10 dark:border-white/15 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-white/5 dark:text-paper">
              {PRIORITIES.map(p => <option key={p} value={p}>{t(`grievance.priority.${p}`)}</option>)}
            </select>
          </div>
          <textarea value={form.description} onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
            rows={3} required placeholder={t('transactionDetail.describeIssuePlaceholder')}
            className="w-full border border-black/10 dark:border-white/15 rounded-lg px-2 py-1.5 text-sm bg-white dark:bg-white/5 dark:text-paper resize-none" />
          <div className="flex gap-2">
            <button type="submit" disabled={submitting}
              className="text-xs bg-red-500 text-white font-semibold rounded-lg px-3 py-1.5 disabled:opacity-60">
              {submitting ? t('transactionDetail.submittingGrievance') : t('transactionDetail.submitGrievance')}
            </button>
            <button type="button" onClick={() => setShowForm(false)} className="text-xs text-ink/50 hover:underline">{t('cancel')}</button>
          </div>
        </form>
      )}
    </div>
  )
}

export default function TransactionDetail() {
  const { id } = useParams()
  const { role } = useAuth()
  const { t } = useI18n()
  const [txn, setTxn] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [advancing, setAdvancing] = useState(false)
  const [error, setError] = useState('')
  const [toast, setToast] = useState('')

  const load = useCallback(async () => {
    try {
      const [txnData, tl] = await Promise.all([
        api.getTransaction(Number(id)),
        api.getTransactionTimeline(Number(id)),
      ])
      setTxn(txnData)
      setTimeline(tl)
    } catch (e) {
      setError(e.message)
    }
  }, [id])

  useEffect(() => { load() }, [load])

  async function advanceStatus(newStatus) {
    setAdvancing(true); setError('')
    try {
      await api.updateTransactionStatus(Number(id), newStatus)
      setToast(t('transactionDetail.statusUpdated', { status: t(`transaction.status.${newStatus}`) }))
      load()
    } catch (e) { setError(e.message) } finally { setAdvancing(false) }
  }

  if (error) return (
    <div className="space-y-3">
      <div className="text-red-600">{error}</div>
      <Link to="/transactions" className="text-sm text-forest underline">{t('transactionDetail.backToTransactions')}</Link>
    </div>
  )
  if (!txn) return <LoadingSpinner label={t('transactionDetail.loadingTransaction')} />

  const nextFarmer = FARMER_NEXT[txn.status]
  const nextBuyer = BUYER_NEXT[txn.status]
  const nextAction = role === 'farmer' ? nextFarmer : role === 'buyer' ? nextBuyer : null
  const canRaiseDispute = !['OFFER_CREATED', 'CANCELLED'].includes(txn.status)

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center gap-3 flex-wrap">
        <Link to="/transactions" className="text-sm text-forest hover:underline">{t('transactionDetail.backToTransactions')}</Link>
        <span className="text-ink/30">/</span>
        <span className="text-sm font-mono-data text-ink/60 dark:text-paper/60">{t('transactionDetail.txnHash', { id: txn.id })}</span>
      </div>

      {toast && (
        <div className="bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 text-emerald-700 dark:text-emerald-300 text-sm rounded-lg px-3 py-2">
          {toast} <button onClick={() => setToast('')} className="ml-2 underline text-xs">{t('ui.dismiss')}</button>
        </div>
      )}

      {/* Transaction overview */}
      <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-6">
        <div className="flex items-start justify-between mb-4 flex-wrap gap-2">
          <div>
            <h1 className="font-display font-bold text-xl">{t('transactions.transactionHash', { id: txn.id })}</h1>
            <div className="text-xs text-ink/50 dark:text-paper/50 mt-0.5">{fmt(txn.created_at)}</div>
          </div>
          <Badge tone={STATUS_TONE[txn.status] || 'neutral'}>{t(`transaction.status.${txn.status}`)}</Badge>
        </div>
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-sm">
          <div>
            <div className="text-xs text-ink/40 dark:text-paper/40">{t('transactionDetail.totalValue')}</div>
            <div className="font-mono-data font-bold text-lg">₹{txn.total_amount.toLocaleString('en-IN')}</div>
          </div>
          <div>
            <div className="text-xs text-ink/40 dark:text-paper/40">{t('ui.price')}</div>
            <div className="font-semibold">₹{txn.final_price_per_kg}/kg</div>
          </div>
          <div>
            <div className="text-xs text-ink/40 dark:text-paper/40">{t('sellingJourney.quantity')}</div>
            <div className="font-semibold">{txn.quantity_kg.toLocaleString()} kg</div>
          </div>
          <div>
            <div className="text-xs text-ink/40 dark:text-paper/40">{t('ui.market')}</div>
            <div className="font-semibold">{txn.market_used || '—'}</div>
          </div>
        </div>

        {role === 'farmer' && txn.status === 'ORDER_CONFIRMED' && (
          <div className="mt-4 pt-4 border-t border-black/5 dark:border-white/10">
            {/* Real action: create an actual transport request linked to this
                transaction (backend then moves it to LOGISTICS_PENDING once
                the request exists), rather than just flipping the status label. */}
            <Link
              to={`/transport?transaction_id=${txn.id}&lot_id=${txn.lot_id || ''}&pickup_location=${encodeURIComponent(txn.market_used || '')}`}
              className="inline-block bg-forest text-paper font-semibold rounded-lg px-5 py-2 text-sm"
            >
              {t('transactionDetail.requestTransport')}
            </Link>
          </div>
        )}

        {nextAction && (
          <div className="mt-4 pt-4 border-t border-black/5 dark:border-white/10">
            <button
              onClick={() => advanceStatus(nextAction)}
              disabled={advancing}
              className="bg-forest text-paper font-semibold rounded-lg px-5 py-2 text-sm disabled:opacity-60"
            >
              {advancing ? t('transactionDetail.updating') : t(`transaction.next.${nextAction}`)}
            </button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Timeline */}
        <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
          <h2 className="font-display font-semibold text-base mb-4">{t('transactionDetail.timeline')}</h2>
          {timeline ? (
            timeline.timeline.length > 0
              ? <Timeline events={timeline.timeline} currentStatus={txn.status} />
              : <p className="text-xs text-ink/50">{t('transactionDetail.noEventsYet')}</p>
          ) : <div className="text-xs text-ink/50">{t('common.loading')}</div>}
        </div>

        <div className="space-y-6">
          {/* Payment */}
          <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
            <h2 className="font-display font-semibold text-base mb-4">{t('transactionDetail.payment')}</h2>
            <PaymentPanel txnId={txn.id} role={role} txnAmount={txn.total_amount} onUpdated={load} />
          </div>

          {/* Receipt */}
          {(RECEIPTABLE_STATUSES.includes(txn.status)) && (
            <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
              <h2 className="font-display font-semibold text-base mb-4">{t('transactionDetail.receipt')}</h2>
              <ReceiptPanel txnId={txn.id} status={txn.status} />
            </div>
          )}

          {/* Grievance */}
          {canRaiseDispute && (
            <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-5">
              <h2 className="font-display font-semibold text-base mb-4">{t('transactionDetail.disputes')}</h2>
              <GrievancePanel txnId={txn.id} role={role} />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
