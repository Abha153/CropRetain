import React, { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { ReceiptText, ArrowUpRight } from 'lucide-react'
import { api } from '../api/client'
import Badge from '../components/Badge'
import LoadingSpinner from '../components/LoadingSpinner'
import { useI18n } from '../i18n/I18nContext'

const STATUS_TONE = {
  OFFER_CREATED: 'neutral', OFFER_ACCEPTED: 'info', ORDER_CONFIRMED: 'info',
  LOGISTICS_PENDING: 'warning', LOGISTICS_CONFIRMED: 'info', PICKED_UP: 'marigold',
  IN_TRANSIT: 'marigold', DELIVERED: 'success', PAYMENT_PENDING: 'warning',
  PAYMENT_INITIATED: 'info', PAYMENT_RECEIVED: 'success', COMPLETED: 'forest',
  // Legacy
  completed: 'forest',
}

function fmt(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' })
}

export default function Transactions() {
  const { t } = useI18n()
  const [txns, setTxns] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.myTransactions()
      .then(setTxns)
      .catch(e => { setError(e.message); setTxns([]) })
  }, [])

  if (error) return <div className="text-red-600 text-sm">{error}</div>
  if (!txns) return <LoadingSpinner label={t('transactions.loading')} />

  return (
    <div className="space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-forest/60">{t('transactions.orders')}</p>
        <h1 className="font-display text-3xl font-bold mt-2 inline-flex items-center gap-2"><ReceiptText size={22} className="text-forest" /> {t('navTransactions')}</h1>
      </div>
      <p className="text-ink/60 dark:text-paper/60 text-sm -mt-2">{t('transactions.subtitle')}</p>

      {txns.length === 0 ? (
        <p className="text-sm text-ink/50 dark:text-paper/50">{t('ui.noTransactions')}</p>
      ) : (
        <div className="space-y-3">
          {txns.map(txn => (
            <Link
              key={txn.id}
              to={`/transactions/${txn.id}`}
              className="block bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 px-5 py-4 hover:-translate-y-0.5 transition-transform"
            >
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div>
                  <div className="font-semibold">{t('transactions.transactionHash', { id: txn.id })}</div>
                  <div className="text-xs text-ink/50 dark:text-paper/50">
                    ₹{txn.final_price_per_kg}/kg · {txn.quantity_kg.toLocaleString()} kg · {txn.market_used}
                  </div>
                  <div className="text-xs text-ink/40 dark:text-paper/40">{fmt(txn.created_at)}</div>
                </div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div className="font-mono-data font-bold text-forest">₹{txn.total_amount.toLocaleString('en-IN')}</div>
                  </div>
                  <div className="flex items-center gap-2">
                    <Badge tone={STATUS_TONE[txn.status] || 'neutral'}>{t(`transaction.status.${txn.status}`)}</Badge>
                    <ArrowUpRight size={16} className="text-forest/60" />
                  </div>
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  )
}
