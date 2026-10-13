import React, { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'
import { useI18n } from '../i18n/I18nContext'
import TripReviewSection from '../components/TripReviewSection'
import TransportQuoteSection from '../components/TransportQuoteSection'
import { formatTimestamp } from '../utils/datetime'

const STATUS_COLORS = {
  REQUESTED: 'blue',
  MATCHED: 'purple',
  CONFIRMED: 'green',
  PICKED_UP: 'orange',
  IN_TRANSIT: 'orange',
  DELIVERED: 'green',
  CANCELLED: 'red',
}

const STATUS_FLOW = ['REQUESTED', 'MATCHED', 'CONFIRMED', 'PICKED_UP', 'IN_TRANSIT', 'DELIVERED']

const NEXT_STATUS = {
  REQUESTED: 'MATCHED',
  MATCHED: 'CONFIRMED',
  CONFIRMED: 'PICKED_UP',
  PICKED_UP: 'IN_TRANSIT',
  IN_TRANSIT: 'DELIVERED',
}

export default function Transport() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [searchParams] = useSearchParams()
  const linkedTransactionId = searchParams.get('transaction_id') || ''
  const [requests, setRequests] = useState([])
  const [vehicles, setVehicles] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(Boolean(linkedTransactionId))
  const [form, setForm] = useState({
    pickup_location: searchParams.get('pickup_location') || '',
    destination: '',
    pickup_date: '',
    pickup_time: '',
    vehicle_type: '',
    quantity_kg: '',
    shared_transport: false,
    lot_id: searchParams.get('lot_id') || '',
    transaction_id: linkedTransactionId,
  })
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  useEffect(() => {
    loadRequests()
    api.getVehicleOptions().then(setVehicles).catch(() => {})
    if (user?.location && !form.pickup_location) setForm(f => ({ ...f, pickup_location: user.location }))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user])

  async function loadRequests() {
    setLoading(true)
    try {
      const data = await api.myTransportRequests()
      setRequests(data)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  async function submitRequest(e) {
    e.preventDefault()
    setSubmitting(true)
    setError('')
    try {
      await api.createTransportRequest({
        ...form,
        quantity_kg: form.quantity_kg ? parseFloat(form.quantity_kg) : null,
        lot_id: form.lot_id ? parseInt(form.lot_id) : null,
        transaction_id: form.transaction_id ? parseInt(form.transaction_id) : null,
      })
      setSuccess(form.transaction_id
        ? t('transport.linkedRequestCreated', { id: form.transaction_id })
        : t('transport.requestCreated'))
      setShowForm(false)
      setForm({ pickup_location: user?.location || '', destination: '', pickup_date: '', pickup_time: '', vehicle_type: '', quantity_kg: '', shared_transport: false, lot_id: '', transaction_id: '' })
      loadRequests()
    } catch (e) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  async function advanceStatus(req) {
    const next = NEXT_STATUS[req.status]
    if (!next) return
    try {
      await api.updateTransportStatus(req.id, next)
      loadRequests()
    } catch (e) {
      setError(e.message)
    }
  }

  async function cancelRequest(id) {
    if (!window.confirm(t('transport.cancelConfirm'))) return
    try {
      await api.cancelTransportRequest(id)
      loadRequests()
    } catch (e) {
      setError(e.message)
    }
  }

  return (
    <div>
      <h1 className="font-display text-3xl font-bold mb-1">{t('transport.title')}</h1>
      <p className="text-ink/60 dark:text-paper/60 mb-6">{t('transport.subtitle')}</p>

      {error && <div className="mb-4 p-3 bg-red-50 dark:bg-red-900/20 border border-red-200 text-red-600 text-sm rounded-lg">{error}</div>}
      {success && <div className="mb-4 p-3 bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 text-emerald-700 text-sm rounded-lg">{success}</div>}

      <div className="flex items-center justify-between mb-6">
        <h2 className="font-semibold text-lg">{t('transport.myRequests')}</h2>
        <button onClick={() => setShowForm(true)}
          className="bg-forest text-paper px-4 py-2 rounded-lg text-sm font-semibold hover:bg-forest/90">
          + {t('transport.newRequest')}
        </button>
      </div>

      {/* Vehicle Reference */}
      {vehicles.length > 0 && (
        <div className="bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-xl p-4 mb-6">
          <h3 className="text-sm font-semibold text-blue-800 dark:text-blue-300 mb-2">{t('transport.availableVehicles')}</h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
            {vehicles.map((v, i) => (
              <div key={i} className="text-xs bg-white dark:bg-white/10 rounded-lg p-2">
                <p className="font-semibold text-ink dark:text-paper">{v.vehicle}</p>
                <p className="text-ink/50 dark:text-paper/50">{t('transport.capacity')}: {v.capacity_kg} kg</p>
                <p className="text-ink/50 dark:text-paper/50">₹{v.cost_per_km}/km</p>
              </div>
            ))}
          </div>
        </div>
      )}

      {loading ? <LoadingSpinner /> : requests.length === 0 ? (
        <div className="text-center py-12 text-ink/40 dark:text-paper/40">
          <p className="text-4xl mb-3"> </p>
          <p className="font-medium">{t('transport.noRequests')}</p>
          <button onClick={() => setShowForm(true)} className="mt-3 text-forest font-semibold text-sm">
            {t('transport.createFirst')} →
          </button>
        </div>
      ) : (
        <div className="space-y-4">
          {requests.map(r => (
            <div key={r.id} className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 p-5">
              <div className="flex items-start justify-between mb-3">
                <div>
                  <p className="font-bold">{r.pickup_location} → {r.destination}</p>
                  <p className="text-xs text-ink/50 dark:text-paper/50 mt-0.5">
                    {r.pickup_date && `${t('transport.pickup')}: ${r.pickup_date}`}
                    {r.pickup_time && ` ${t('transport.at')} ${r.pickup_time}`}
                    {r.quantity_kg && ` • ${r.quantity_kg} kg`}
                  </p>
                </div>
                <Badge color={STATUS_COLORS[r.status] || 'gray'} size="sm">{t(`transport.statusLabel.${r.status}`)}</Badge>
              </div>

              {/* Progress bar */}
              <div className="flex items-center gap-0 mb-3">
                {STATUS_FLOW.map((s, i) => (
                  <React.Fragment key={s}>
                    <div className={`flex-shrink-0 w-3 h-3 rounded-full border-2 ${
                      STATUS_FLOW.indexOf(r.status) >= i
                        ? 'bg-forest border-forest'
                        : 'bg-white dark:bg-gray-800 border-black/20 dark:border-white/20'
                    }`} />
                    {i < STATUS_FLOW.length - 1 && (
                      <div className={`flex-1 h-0.5 ${
                        STATUS_FLOW.indexOf(r.status) > i ? 'bg-forest' : 'bg-black/10 dark:bg-white/10'
                      }`} />
                    )}
                  </React.Fragment>
                ))}
              </div>

              {/* Real server timestamps for the two physical trip events that
                  have one -- planned pickup_date/pickup_time above are what
                  the farmer entered, these are what actually happened. */}
              {(formatTimestamp(r.picked_up_at) || formatTimestamp(r.delivered_at)) && (
                <p className="text-[11px] text-ink/40 dark:text-paper/40 -mt-2 mb-3">
                  {formatTimestamp(r.picked_up_at) && `${t('transport.quote.pickedUpAt')} · ${formatTimestamp(r.picked_up_at)}`}
                  {formatTimestamp(r.picked_up_at) && formatTimestamp(r.delivered_at) && '  ·  '}
                  {formatTimestamp(r.delivered_at) && `${t('transport.quote.deliveredAt')} · ${formatTimestamp(r.delivered_at)}`}
                </p>
              )}

              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-sm mb-3">
                {r.vehicle_type && <div><p className="text-xs text-ink/50 dark:text-paper/50">{t('transport.vehicle')}</p><p className="font-semibold">{r.vehicle_type}</p></div>}
                {r.driver_name && <div><p className="text-xs text-ink/50 dark:text-paper/50">{t('transport.driver')}</p><p className="font-semibold">{r.driver_name}</p></div>}
                {r.driver_contact && <div><p className="text-xs text-ink/50 dark:text-paper/50">{t('transport.contact')}</p><p className="font-semibold">{r.driver_contact}</p></div>}
                {r.shared_transport && <div><Badge color="blue" size="sm">{t('transport.shared')}</Badge></div>}
                {r.lot_id && <div><p className="text-xs text-ink/50 dark:text-paper/50">{t('transport.lotId')}</p><p className="font-semibold">#{r.lot_id}</p></div>}
                {r.transaction_id && <div><p className="text-xs text-ink/50 dark:text-paper/50">{t('transport.transaction')}</p><p className="font-semibold">#{r.transaction_id}</p></div>}
              </div>

              <div className="flex gap-2">
                {NEXT_STATUS[r.status] && (
                  <button onClick={() => advanceStatus(r)}
                    className="bg-forest text-paper px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-forest/90">
                    {t(`transport.next.${r.status}`)}
                  </button>
                )}
                {!['DELIVERED', 'CANCELLED'].includes(r.status) && (
                  <button onClick={() => cancelRequest(r.id)}
                    className="border border-red-200 text-red-500 px-3 py-1.5 rounded-lg text-xs font-semibold hover:bg-red-50">
                    {t('cancel')}
                  </button>
                )}
              </div>

              {/* Estimate -> transporter quote -> agreed price. */}
              <TransportQuoteSection
                trip={r}
                onUpdated={(updated) => setRequests(reqs => reqs.map(x => x.id === updated.id ? updated : x))}
              />

              {/* Post-trip trust layer. Renders only for DELIVERED trips;
                  the component itself returns null otherwise. */}
              <TripReviewSection trip={r} />
            </div>
          ))}
        </div>
      )}

      {/* Create form modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white dark:bg-gray-900 rounded-2xl p-6 max-w-lg w-full shadow-2xl max-h-[90vh] overflow-y-auto">
            <h3 className="font-bold text-xl mb-4">{t('transport.newRequest')}</h3>
            {form.transaction_id && (
              <div className="mb-4 p-3 bg-blue-50 dark:bg-blue-900/20 border border-blue-100 dark:border-blue-800 rounded-lg text-xs text-blue-800 dark:text-blue-300">
                {t('transport.linkedToTransaction', { id: form.transaction_id })} <strong>{t('transport.logisticsPending')}</strong>.
              </div>
            )}
            <form onSubmit={submitRequest} className="space-y-4">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('transport.pickupLocation')} *</label>
                  <input value={form.pickup_location} onChange={e => setForm(f => ({ ...f, pickup_location: e.target.value }))}
                    required className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('transport.destination')} *</label>
                  <input value={form.destination} onChange={e => setForm(f => ({ ...f, destination: e.target.value }))}
                    required className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('transport.pickupDate')}</label>
                  <input type="date" value={form.pickup_date} onChange={e => setForm(f => ({ ...f, pickup_date: e.target.value }))}
                    className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
                </div>
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('transport.pickupTime')}</label>
                  <input type="time" value={form.pickup_time} onChange={e => setForm(f => ({ ...f, pickup_time: e.target.value }))}
                    className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('transport.vehicleType')}</label>
                  <select value={form.vehicle_type} onChange={e => setForm(f => ({ ...f, vehicle_type: e.target.value }))}
                    className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper">
                    <option value="">{t('transport.selectVehicle')}</option>
                    {vehicles.map((v, i) => <option key={i} value={v.vehicle}>{v.vehicle} ({v.capacity_kg} kg)</option>)}
                  </select>
                </div>
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.quantityKg')}</label>
                  <input type="number" value={form.quantity_kg} onChange={e => setForm(f => ({ ...f, quantity_kg: e.target.value }))}
                    className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
                </div>
              </div>
              <div>
                <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('transport.lotIdOptional')}</label>
                <input type="number" value={form.lot_id} onChange={e => setForm(f => ({ ...f, lot_id: e.target.value }))}
                  placeholder={t('transport.linkToLot')}
                  className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper" />
              </div>
              <label className="flex items-center gap-2 cursor-pointer">
                <input type="checkbox" checked={form.shared_transport}
                  onChange={e => setForm(f => ({ ...f, shared_transport: e.target.checked }))}
                  className="rounded" />
                <span className="text-sm text-ink/80 dark:text-paper/80">{t('transport.sharedRequest')}</span>
              </label>
              <div className="flex gap-3 pt-2">
                <button type="button" onClick={() => setShowForm(false)}
                  className="flex-1 border border-black/10 dark:border-white/15 py-2 rounded-lg text-sm font-semibold">
                  {t('cancel')}
                </button>
                <button type="submit" disabled={submitting}
                  className="flex-1 bg-forest text-paper py-2 rounded-lg text-sm font-semibold disabled:opacity-60">
                  {submitting ? t('transport.submitting') : t('transport.submit')}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  )
}
