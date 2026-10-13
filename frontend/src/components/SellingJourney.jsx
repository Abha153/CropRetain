import React from 'react'
import { Link } from 'react-router-dom'
import { Sprout, BarChart3, Handshake, Truck, Wallet, CircleCheck, ArrowRight, MapPin } from 'lucide-react'
import { STAGES, NEXT_DESTINATION } from '../utils/sellingJourney'
import { useI18n } from '../i18n/I18nContext'
import FieldMotif from './FieldMotif'

// Lucide icons, one coherent family -- no emoji anywhere in this component.
// CircleCheck is reserved for the "completed" checkmark overlay on ANY
// stage; each stage also has its own default icon for its
// current/upcoming state so Payment doesn't look like a generic checkmark
// before it's actually been received.
const STAGE_ICON = {
  ADD_PRODUCE: Sprout,
  MARKET_ANALYSIS: BarChart3,
  FIND_BUYER: Handshake,
  CREATE_SHIP: Truck,
  PAYMENT_RECEIVED: Wallet,
}

const STAGE_COUNT = STAGES.length

function nodeClasses(status, isFinal) {
  if (status === 'completed') {
    return isFinal
      ? 'bg-forest text-paper border-forest ring-4 ring-forest/20'
      : 'bg-forest text-paper border-forest'
  }
  if (status === 'current') {
    return isFinal
      ? 'bg-marigold text-forest-dark border-marigold ring-4 ring-marigold/30'
      : 'bg-forest text-paper border-marigold ring-4 ring-marigold/30'
  }
  return 'bg-white dark:bg-white/5 text-ink/30 dark:text-paper/30 border-black/10 dark:border-white/15'
}

function connectorClasses(fromStatus) {
  return fromStatus === 'completed' ? 'bg-forest' : 'bg-black/10 dark:bg-white/15'
}

/**
 * The Selling Journey -- a destination progression, never a game (no
 * points/XP/badges). Business state comes entirely from
 * utils/sellingJourney.js (deriveJourneyForLot / selectFocusJourney),
 * unchanged by this redesign -- only the visual presentation below is new.
 *
 * Structure follows the "start -> current destination -> next destination
 * -> final destination" model: a route of five nodes, then a dedicated
 * CURRENT DESTINATION panel (the visual anchor) and a lighter NEXT
 * DESTINATION panel beneath it, so a farmer glancing at the dashboard
 * immediately sees both "where am I" and "what do I do next" without
 * having to read the whole route.
 *
 * `dark`: renders on a dark-forest hero surface instead of the standard
 * white card -- independent of the app's light/dark theme toggle.
 */
export default function SellingJourney({ journey, dark = false }) {
  const { t } = useI18n()
  const { stageStatus, currentStageKey, lot, transaction, isFullyComplete } = journey
  const currentStage = STAGES.find(s => s.key === currentStageKey)
  const currentIndex = STAGES.findIndex(s => s.key === currentStageKey)
  const nextStage = STAGES[currentIndex + 1]
  const destination = NEXT_DESTINATION[currentStageKey]
  const ctaTo = destination?.ctaTo || (transaction ? `/transactions/${transaction.id}` : '/lots')
  const nextDestinationMeta = nextStage ? NEXT_DESTINATION[nextStage.key] : null
  // Real, state-derived progress -- never hard-coded. currentStage.order is
  // 1-5 from utils/sellingJourney.js's own STAGES definition.
  const progressPercent = currentStage ? Math.round((currentStage.order / STAGE_COUNT) * 100) : 0

  const surface = dark
    ? 'bg-forest-dark text-paper'
    : 'bg-white dark:bg-white/5 shadow-card border border-black/5 dark:border-white/10 text-ink dark:text-paper'
  const mutedText = dark ? 'text-paper/50' : 'text-ink/50 dark:text-paper/50'
  const bodyText = dark ? 'text-paper/70' : 'text-ink/70 dark:text-paper/70'
  const panelSurface = dark ? 'bg-white/5 border-white/10' : 'bg-wheat/30 dark:bg-white/5 border-black/5 dark:border-white/10'

  return (
    <div className={`relative rounded-2xl p-5 md:p-6 overflow-hidden ${surface}`}>
      {dark && <FieldMotif className="absolute inset-x-0 bottom-0 w-full h-24 md:h-32 text-paper pointer-events-none" />}
      <div className="relative">
        <div className="flex items-center justify-between mb-5 flex-wrap gap-2">
          <div>
            <h2 className="font-display font-semibold text-lg">{t('sellingJourney.title')}</h2>
            <p className={`text-xs mt-0.5 ${mutedText}`}>{t('sellingJourney.subtitle')}</p>
          </div>
          {lot && (
            <span className={`text-xs ${mutedText}`}>
              {lot.crop} · {lot.quantity_kg?.toLocaleString()} kg{lot.lot_number ? ` · ${lot.lot_number}` : ''}
            </span>
          )}
        </div>

        {!lot ? (
          <div className="text-center py-6">
            <p className={`text-sm mb-4 ${bodyText}`}>{t('sellingJourney.noProduceYet')}</p>
            <Link to="/lots" className={`inline-block font-semibold rounded-lg px-5 py-2.5 text-sm ${dark ? 'bg-marigold text-forest-dark' : 'bg-forest text-paper'}`}>
              {t('sellingJourney.addProduce')} <ArrowRight size={14} className="inline -mt-0.5" />
            </Link>
          </div>
        ) : (
          <>
            {/* Desktop: route of destination nodes */}
            <div className="hidden md:flex items-start" role="list" aria-label={t('sellingJourney.title')}>
              {STAGES.map((stage, i) => {
                const Icon = STAGE_ICON[stage.key]
                const status = stageStatus[stage.key]
                const isFinal = stage.key === 'PAYMENT_RECEIVED'
                const statusLabel = status === 'completed' ? t('sellingJourney.completed')
                  : status === 'current' ? t('sellingJourney.currentStage') : t('sellingJourney.upcoming')
                return (
                  <React.Fragment key={stage.key}>
                    <Link
                      to={NEXT_DESTINATION[stage.key]?.ctaTo || '/lots'}
                      role="listitem"
                      aria-current={status === 'current' ? 'step' : undefined}
                      aria-label={`${t(stage.label)} -- ${statusLabel}`}
                      className="flex flex-col items-center text-center group focus:outline-none"
                      style={{ width: `${100 / STAGE_COUNT}%` }}
                    >
                      <div
                        className={`w-11 h-11 rounded-full border-2 flex items-center justify-center transition-transform group-hover:scale-105 group-focus-visible:ring-2 group-focus-visible:ring-marigold ${nodeClasses(status, isFinal)} ${status === 'current' ? 'animate-pulse motion-reduce:animate-none' : ''}`}
                      >
                        {status === 'completed' ? <CircleCheck size={20} /> : <Icon size={18} />}
                      </div>
                      <div className={`mt-2 text-xs font-semibold ${status === 'upcoming' ? mutedText : (dark ? 'text-paper' : 'text-ink dark:text-paper')}`}>
                        {t(stage.label)}
                      </div>
                      <div className={`text-[10px] mt-0.5 ${status === 'current' ? (dark ? 'text-marigold' : 'text-marigold-dark') : mutedText}`}>
                        {isFinal && status !== 'completed' ? t('sellingJourney.finalDestination') : statusLabel}
                      </div>
                    </Link>
                    {i < STAGES.length - 1 && (
                      <div className={`h-0.5 mt-[22px] flex-1 rounded-full transition-colors ${connectorClasses(stageStatus[stage.key])}`} />
                    )}
                  </React.Fragment>
                )
              })}
            </div>

            {/* Mobile: vertical destination timeline with reference-style cards */}
            <div className="md:hidden relative space-y-3 pl-3" role="list" aria-label={t('sellingJourney.title')}>
              {STAGES.map((stage, i) => {
                const status = stageStatus[stage.key]
                const isCurrent = stage.key === currentStageKey
                const isFinal = stage.key === 'PAYMENT_RECEIVED'
                const Icon = STAGE_ICON[stage.key]
                const statusLabel = status === 'completed' ? t('sellingJourney.completed')
                  : status === 'current' ? t('sellingJourney.currentStage') : t('sellingJourney.upcoming')
                return (
                  <div key={stage.key} role="listitem" aria-current={isCurrent ? 'step' : undefined} className="relative flex gap-3">
                    <div className="relative z-10 flex flex-col items-center">
                      <div className={`w-10 h-10 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${nodeClasses(status, isFinal)} ${isCurrent ? 'animate-pulse motion-reduce:animate-none' : ''}`}>
                        {status === 'completed' ? <CircleCheck size={16} /> : <Icon size={15} />}
                      </div>
                      {i < STAGES.length - 1 && <div className={`w-0.5 flex-1 min-h-[86px] ${connectorClasses(status)}`} />}
                    </div>
                    <div className={`flex-1 rounded-2xl border p-4 mb-1 transition-colors ${isCurrent ? (dark ? 'border-marigold/70 bg-marigold/10' : 'border-marigold bg-[#fffaf0] dark:bg-marigold/10') : (dark ? 'border-white/10 bg-white/5' : 'border-black/5 bg-white/80 dark:bg-white/5')} ${status === 'upcoming' ? 'opacity-75' : ''}`}>
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className={`text-[10px] font-bold uppercase tracking-wider ${isCurrent ? (dark ? 'text-marigold' : 'text-marigold-dark') : mutedText}`}>
                            {String(i + 1).padStart(2, '0')} · {statusLabel}
                          </div>
                          <div className={`text-base font-display font-semibold mt-1 ${status === 'upcoming' ? mutedText : (dark ? 'text-paper' : 'text-ink dark:text-paper')}`}>
                            {t(stage.label)}
                          </div>
                        </div>
                        <ArrowRight size={18} className={mutedText} aria-hidden="true" />
                      </div>
                      <p className={`text-sm mt-1.5 ${bodyText}`}>{t(NEXT_DESTINATION[stage.key]?.description)}</p>
                      {isCurrent && destination && (
                        <>
                          <div className={`text-[11px] font-mono-data mt-3 ${mutedText}`}>{currentStage.order} / {STAGE_COUNT} · {progressPercent}% {t('sellingJourney.complete')}</div>
                          <div className="mt-2 h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                            <div className="h-full rounded-full bg-marigold" style={{ width: `${progressPercent}%` }} />
                          </div>
                          <Link to={ctaTo} className={`w-full justify-center inline-flex items-center gap-1.5 text-sm font-semibold rounded-xl px-4 py-2.5 mt-4 ${dark ? 'bg-marigold text-forest-dark' : 'bg-forest text-paper'}`}>
                            {t(destination.ctaLabel)} <ArrowRight size={14} />
                          </Link>
                        </>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>

            {/* Current Destination / Next Destination / Final Destination panels */}
            <div className={`mt-6 pt-5 border-t ${dark ? 'border-white/10' : 'border-black/5 dark:border-white/10'}`}>
              {isFullyComplete ? (
                <div>
                  <div className="flex items-center gap-2 mb-3">
                    <CircleCheck size={18} className={dark ? 'text-marigold' : 'text-forest'} />
                    <p className={`text-xs font-semibold uppercase tracking-wide ${dark ? 'text-marigold' : 'text-forest'}`}>
                      {t('sellingJourney.finalDestinationReached')}
                    </p>
                  </div>
                  <div className={`rounded-xl border p-4 ${panelSurface}`}>
                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
                      <div>
                        <div className={`text-[10px] uppercase ${mutedText}`}>{t('common.crop')}</div>
                        <div className="font-semibold">{lot.crop}</div>
                      </div>
                      <div>
                        <div className={`text-[10px] uppercase ${mutedText}`}>{t('sellingJourney.quantity')}</div>
                        <div className="font-semibold">{(transaction?.quantity_kg ?? lot.quantity_kg)?.toLocaleString()} kg</div>
                      </div>
                      {transaction?.market_used && (
                        <div>
                          <div className={`text-[10px] uppercase ${mutedText}`}>{t('ui.market')}</div>
                          <div className="font-semibold">{transaction.market_used}</div>
                        </div>
                      )}
                      {transaction?.total_amount != null && (
                        <div>
                          <div className={`text-[10px] uppercase ${mutedText}`}>{t('sellingJourney.amountReceived')}</div>
                          <div className="font-semibold font-mono-data">₹{transaction.total_amount.toLocaleString()}</div>
                        </div>
                      )}
                    </div>
                    <p className={`text-sm mt-3 ${bodyText}`}>{t('sellingJourney.paymentReceivedForLot')}</p>
                    <div className="flex items-center gap-4 mt-3">
                      {transaction && (
                        <Link to={`/transactions/${transaction.id}`} className={`text-sm font-semibold hover:underline ${dark ? 'text-marigold' : 'text-forest'}`}>
                          {t('sellingJourney.viewTransaction')} →
                        </Link>
                      )}
                      <Link to="/lots" className={`text-sm font-semibold hover:underline ${mutedText}`}>
                        {t('sellingJourney.sellMoreProduce')} →
                      </Link>
                    </div>
                  </div>
                </div>
              ) : (
                <div className="grid md:grid-cols-5 gap-4">
                  {/* Current destination -- the visual anchor, larger and bolder */}
                  <div className={`md:col-span-3 rounded-xl border p-4 ${panelSurface}`}>
                    <p className={`text-[10px] font-semibold uppercase tracking-wide flex items-center gap-1.5 ${dark ? 'text-marigold' : 'text-marigold-dark dark:text-marigold'}`}>
                      <MapPin size={12} /> {t('sellingJourney.current')}
                    </p>
                    <p className="font-display font-semibold text-base mt-1">
                      {t(currentStage?.label)}
                    </p>
                    <p className={`text-sm mt-1.5 ${bodyText}`}>{t(destination?.description)}</p>
                    <div className="flex items-center justify-between mt-3">
                      <div className={`text-xs font-mono-data ${mutedText}`}>
                        {currentStage?.order} / {STAGE_COUNT} · {progressPercent}% {t('sellingJourney.complete')}
                      </div>
                    </div>
                    <div className="mt-2 h-1.5 rounded-full bg-black/10 dark:bg-white/10 overflow-hidden">
                      <div
                        className="h-full bg-marigold rounded-full transition-all duration-700 motion-reduce:transition-none"
                        style={{ width: `${progressPercent}%` }}
                      />
                    </div>
                    <Link
                      to={ctaTo}
                      className={`inline-flex items-center gap-1.5 font-semibold rounded-lg px-4 py-2 text-sm mt-4 transition-opacity hover:opacity-90 ${dark ? 'bg-marigold text-forest-dark' : 'bg-forest text-paper'}`}
                    >
                      {t(destination?.ctaLabel)} <ArrowRight size={14} />
                    </Link>
                  </div>

                  {/* Next destination -- lighter weight, secondary */}
                  {nextStage && nextDestinationMeta ? (
                    <div className={`md:col-span-2 rounded-xl border p-4 ${dark ? 'border-white/10' : 'border-black/5 dark:border-white/10'}`}>
                      <p className={`text-[10px] font-semibold uppercase tracking-wide ${mutedText}`}>{t('sellingJourney.next')}</p>
                      <p className="font-display font-semibold text-sm mt-1">
                        {t(nextStage.label)}
                        {nextStage.key === 'PAYMENT_RECEIVED' && (
                          <span className={`ml-2 text-[9px] font-bold uppercase tracking-wide align-middle ${dark ? 'text-marigold' : 'text-marigold-dark'}`}>
                            {t('sellingJourney.finalDestination')}
                          </span>
                        )}
                      </p>
                      <p className={`text-xs mt-1.5 ${mutedText}`}>{t(nextDestinationMeta.description)}</p>
                    </div>
                  ) : (
                    <div className={`md:col-span-2 rounded-xl border p-4 flex items-center ${dark ? 'border-white/10' : 'border-black/5 dark:border-white/10'}`}>
                      <p className={`text-xs ${mutedText}`}>
                        <Wallet size={14} className="inline mr-1 -mt-0.5" /> {t('sellingJourney.finalDestination')}: {t('sellingJourney.paymentReceived')}
                      </p>
                    </div>
                  )}
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  )
}
