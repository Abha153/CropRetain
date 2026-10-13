import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ShoppingCart, Clock3, BriefcaseBusiness, ShieldCheck, ArrowRight, Package, FileCheck2, Building2, MapPin } from 'lucide-react'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import StatCard from '../components/StatCard'
import Badge from '../components/Badge'
import OfferNegotiation from '../components/OfferNegotiation'
import LoadingSpinner from '../components/LoadingSpinner'
import { useI18n } from '../i18n/I18nContext'

const TXN_STATUS_TONE = {
  OFFER_ACCEPTED: 'info', ORDER_CONFIRMED: 'info', IN_TRANSIT: 'marigold',
  DELIVERED: 'success', PAYMENT_PENDING: 'warning', PAYMENT_INITIATED: 'info',
  PAYMENT_RECEIVED: 'success', COMPLETED: 'forest', completed: 'forest',
}
const VERIF_TIER = {
  PLATFORM_VERIFIED: { key: 'buyerDashboard.tier.platformVerified', tone: 'success' },
  DOCUMENT_VERIFIED: { key: 'buyerDashboard.tier.documentVerified', tone: 'info' },
  SELF_DECLARED: { key: 'buyerDashboard.tier.selfDeclared', tone: 'neutral' },
  PENDING: { key: 'buyerDashboard.tier.pending', tone: 'neutral' },
}

export default function BuyerDashboard() {
  const { user } = useAuth()
  const { t } = useI18n()
  const [myOffers, setMyOffers] = useState(null)
  const [openThread, setOpenThread] = useState(null)
  const [demands, setDemands] = useState(null)
  const [transactions, setTransactions] = useState(null)
  const [verification, setVerification] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    Promise.all([
      api.myOffers(),
      api.myDemands(),
      api.myTransactions(),
      api.myVerification().catch(() => null),
    ])
      .then(([o, d, txns, v]) => { setMyOffers(o); setDemands(d); setTransactions(txns); setVerification(v) })
      .catch(e => setError(e.message))
  }, [])

  if (error) return <div className="text-red-600">{error}</div>
  if (!myOffers) return <LoadingSpinner label={t('dashboard.loadingDashboard')} />

  const pendingOffers = myOffers.filter(o => o.status === 'pending')
  const activeDemands = (demands || []).filter(d => d.status === 'ACTIVE')
  const pendingTxns = (transactions || []).filter(txn => !['COMPLETED', 'completed'].includes(txn.status))

  const tier = VERIF_TIER[verification?.verification_method || 'PENDING']

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-forest/60">{t('buyerDashboard.title')}</p>
          <h1 className="font-display text-3xl font-bold mt-2">{t('buyerDashboard.welcome', { name: user?.company_name })}</h1>
        </div>
        <div className="flex items-center gap-2 rounded-full bg-white border border-black/5 px-3 py-2 text-sm text-ink/65 shadow-soft">
          <MapPin size={14} className="text-forest" /> {user?.location || t('buyerDashboard.yourLocation')}
        </div>
      </div>

      {(!verification || verification.verification_status !== 'VERIFIED') && (
        <div className="bg-amber-50 border border-amber-200 rounded-2xl px-4 py-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="text-sm">
            <span className="font-semibold">{t('buyerDashboard.notVerified')}</span>
            {' '}{t('buyerDashboard.notVerifiedDesc')}
          </div>
          <Link to="/buyer-verification" className="inline-flex items-center gap-2 text-sm bg-amber-400 text-ink font-semibold rounded-xl px-3 py-1.5 hover:bg-amber-300">
            {t('buyerDashboard.verifyNow')} <ArrowRight size={14} />
          </Link>
        </div>
      )}

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <StatCard label={t('buyerDashboard.activeDemands')} value={activeDemands.length} icon={<ShoppingCart size={16} />} tone="marigold" />
        <StatCard label={t('buyerDashboard.pendingOffers')} value={pendingOffers.length} icon={<Clock3 size={16} />} />
        <StatCard label={t('dashboard.activeTransactions')} value={pendingTxns.length} icon={<BriefcaseBusiness size={16} />} />
        <StatCard label={t('ui.verified')} value={t(tier.key)} icon={<ShieldCheck size={16} />} />
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <Link to="/buyer-demands" className="bg-forest text-paper rounded-2xl p-4 hover:opacity-95 transition-all shadow-soft">
          <div className="mb-2 inline-flex h-9 w-9 items-center justify-center rounded-xl bg-white/10"><ShoppingCart size={18} /></div>
          <div className="font-semibold text-sm">{t('buyerDashboard.myDemands')}</div>
          <div className="text-xs text-paper/70 mt-0.5">{t('buyerDashboard.myDemandsDesc')}</div>
        </Link>
        <Link to="/lots" className="bg-white border border-black/5 rounded-2xl p-4 hover:-translate-y-0.5 transition-transform shadow-soft">
          <div className="mb-2 inline-flex h-9 w-9 items-center justify-center rounded-xl bg-forest/5 text-forest"><Package size={18} /></div>
          <div className="font-semibold text-sm">{t('buyerDashboard.browseLots')}</div>
          <div className="text-xs text-ink/50 mt-0.5">{t('buyerDashboard.browseLotsDesc')}</div>
        </Link>
        <Link to="/transactions" className="bg-white border border-black/5 rounded-2xl p-4 hover:-translate-y-0.5 transition-transform shadow-soft">
          <div className="mb-2 inline-flex h-9 w-9 items-center justify-center rounded-xl bg-forest/5 text-forest"><BriefcaseBusiness size={18} /></div>
          <div className="font-semibold text-sm">{t('navTransactions')}</div>
          <div className="text-xs text-ink/50 mt-0.5">{t('buyerDashboard.transactionsDesc')}</div>
        </Link>
        <Link to="/buyer-verification" className="bg-white border border-black/5 rounded-2xl p-4 hover:-translate-y-0.5 transition-transform shadow-soft">
          <div className="mb-2 inline-flex h-9 w-9 items-center justify-center rounded-xl bg-forest/5 text-forest"><Building2 size={18} /></div>
          <div className="font-semibold text-sm">{t('navVerification')}</div>
          <div className="text-xs text-ink/50 mt-0.5">{t('buyerDashboard.verificationDesc')}</div>
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Active transactions */}
        <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-lg">{t('dashboard.activeTransactions')}</h2>
            <Link to="/transactions" className="text-sm text-forest font-semibold hover:underline">{t('dashboard.viewAll')} →</Link>
          </div>
          {pendingTxns.length === 0 ? (
            <p className="text-sm text-ink/50 dark:text-paper/50">{t('dashboard.noActiveTransactions')}</p>
          ) : (
            <div className="space-y-2">
              {pendingTxns.slice(0, 4).map(txn => (
                <Link key={txn.id} to={`/transactions/${txn.id}`} className="flex items-center justify-between border border-black/5 dark:border-white/10 rounded-xl px-4 py-3 hover:bg-wheat/30 dark:hover:bg-white/5 transition-colors">
                  <div>
                    <div className="font-medium text-sm">{t('transactions.transactionHash', { id: txn.id })}</div>
                    <div className="text-xs text-ink/50 dark:text-paper/50">₹{txn.total_amount.toLocaleString('en-IN')} · {txn.quantity_kg.toLocaleString()} kg</div>
                  </div>
                  <Badge tone={TXN_STATUS_TONE[txn.status] || 'neutral'} className="text-xs">{t(`transaction.status.${txn.status}`)}</Badge>
                </Link>
              ))}
            </div>
          )}
        </div>

        {/* My demands */}
        <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="font-display font-semibold text-lg">{t('buyerDashboard.myActiveDemands')}</h2>
            <Link to="/buyer-demands" className="text-sm text-forest font-semibold hover:underline">{t('dashboard.viewAll')} →</Link>
          </div>
          {activeDemands.length === 0 ? (
            <p className="text-sm text-ink/50 dark:text-paper/50">{t('ui.noActiveDemands')} <Link to="/buyer-demands" className="text-forest underline">{t('buyerDashboard.postOne')} →</Link></p>
          ) : (
            <div className="space-y-2">
              {activeDemands.slice(0, 4).map(d => (
                <div key={d.id} className="border border-black/5 dark:border-white/10 rounded-xl px-4 py-3">
                  <div className="flex items-center justify-between">
                    <div className="font-medium text-sm">{d.crop}</div>
                    <span className="text-xs font-mono-data text-forest">
                      {d.target_price_per_kg ? `₹${(d.target_price_per_kg * 100).toFixed(0)}/q` : t('buyerDashboard.openPrice')}
                    </span>
                  </div>
                  <div className="text-xs text-ink/50 dark:text-paper/50">
                    {d.required_quantity_kg.toLocaleString()} kg{d.quality_grade ? ` · ${t('buyerDashboard.gradeLabel', { grade: d.quality_grade })}` : ''}
                    {d.delivery_location ? ` · ${d.delivery_location}` : ''}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Recent offers */}
      <div className="mt-6 bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-6">
        <h2 className="font-display font-semibold text-lg mb-4">{t('buyerDashboard.recentOffers')}</h2>
        {myOffers.length === 0 ? (
          <p className="text-sm text-ink/50 dark:text-paper/50">{t('ui.noOffers')} {t('buyerDashboard.browseListingsHint')}</p>
        ) : (
          <div className="space-y-2">
            {myOffers.slice(0, 5).map(o => (
              <div key={o.id} className="text-sm border-b border-black/5 dark:border-white/10 pb-2 space-y-2">
                <div className="flex items-center justify-between gap-2">
                  <span>{o.lot_id ? t('buyerDashboard.lotHash', { id: o.lot_id }) : t('buyerDashboard.listingHash', { id: o.listing_id })} · ₹{o.offered_price_per_kg}/kg · {o.quantity_kg.toLocaleString()} kg</span>
                  <span className="flex items-center gap-2">
                    {o.status === 'pending' && o.awaiting_role === 'buyer' && <Badge tone="warning">{t('negotiation.awaitingYou')}</Badge>}
                    <Badge tone={o.status === 'accepted' ? 'success' : o.status === 'rejected' ? 'warning' : 'neutral'}>{t(`offer.status.${o.status}`)}</Badge>
                  </span>
                </div>
                <button onClick={() => setOpenThread(openThread === o.id ? null : o.id)} className="text-xs text-forest font-semibold hover:underline">
                  {openThread === o.id ? t('negotiation.hide') : t('negotiation.open')}
                </button>
                {openThread === o.id && <OfferNegotiation offerId={o.id} onChanged={() => api.myOffers().then(setMyOffers).catch(() => {})} />}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
