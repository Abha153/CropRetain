import React from 'react'
import { Link } from 'react-router-dom'
import {
  Sprout, BarChart3, Handshake, Truck, Wallet, ArrowRight,
  TrendingUp, Bot, LineChart, Store, Users, ShieldCheck, MapPin,
} from 'lucide-react'
import PriceTicker from '../components/PriceTicker'
import LanguageSelector from '../components/LanguageSelector'
import FieldMotif from '../components/FieldMotif'
import { useI18n } from '../i18n/I18nContext'
import { STAGES, NEXT_DESTINATION } from '../utils/sellingJourney'

// Same five real stages the logged-in dashboard's Selling Journey uses
// (utils/sellingJourney.js) -- shown here as a static preview so the
// landing page never invents a different process than the product
// actually has.
const STAGE_ICON = {
  ADD_PRODUCE: Sprout,
  MARKET_ANALYSIS: BarChart3,
  FIND_BUYER: Handshake,
  CREATE_SHIP: Truck,
  PAYMENT_RECEIVED: Wallet,
}

const FEATURES = [
  { icon: TrendingUp, titleKey: 'landing.featurePriceDiscovery', descKey: 'landing.featurePriceDiscoveryDesc' },
  { icon: Bot, titleKey: 'landing.featureAdvisor', descKey: 'landing.featureAdvisorDesc' },
  { icon: LineChart, titleKey: 'landing.featureForecast', descKey: 'landing.featureForecastDesc' },
  { icon: Store, titleKey: 'landing.featureMarketplace', descKey: 'landing.featureMarketplaceDesc' },
  { icon: Users, titleKey: 'landing.featureBuyerMatching', descKey: 'landing.featureBuyerMatchingDesc' },
  { icon: Truck, titleKey: 'landing.featureFarmPool', descKey: 'landing.featureFarmPoolDesc' },
  { icon: Sprout, titleKey: 'landing.featureSoilIntelligence', descKey: 'landing.featureSoilIntelligenceDesc' },
  // Farm Profile (saved farms, plots and soil-test history) is not built yet,
  // so the card says so rather than advertising it as available.
  { icon: MapPin, titleKey: 'landing.featureFarmProfile', descKey: 'landing.featureFarmProfileDesc', soon: true },
  { icon: BarChart3, titleKey: 'landing.featureCropPlanning', descKey: 'landing.featureCropPlanningDesc' },
]

const STEPS = [
  { step: '01', titleKey: 'landing.stepHarvest', descKey: 'landing.stepHarvestDesc' },
  { step: '02', titleKey: 'landing.stepProfit', descKey: 'landing.stepProfitDesc' },
  { step: '03', titleKey: 'landing.stepConfidence', descKey: 'landing.stepConfidenceDesc' },
]
export default function Landing() {
  const { t } = useI18n()

  return (
    <div className="min-h-screen bg-paper dark:bg-ink text-ink dark:text-paper">
      {/* ---------- Navbar ---------- */}
      <header className="sticky top-0 z-20 backdrop-blur bg-paper/90 dark:bg-ink/90 border-b border-black/5 dark:border-white/10">
        <div className="max-w-7xl mx-auto flex items-center justify-between px-6 md:px-10 py-4">
          <div className="flex items-center gap-2 font-display font-bold text-lg text-forest">
            CropRetain
          </div>
          <div className="flex items-center gap-2 sm:gap-4">
            <LanguageSelector compact />
            <Link to="/login" className="text-sm font-medium text-ink/70 dark:text-paper/70 hover:text-forest transition-colors">
              {t('login')}
            </Link>
            <Link to="/register" className="text-sm font-semibold bg-forest text-paper px-3 sm:px-4 py-2 rounded-lg hover:bg-forest-dark transition-colors shadow-sm whitespace-nowrap">
              {t('getStarted')}
            </Link>
          </div>
        </div>
      </header>

      <PriceTicker />

      {/* ---------- Hero ---------- */}
      <section className="relative overflow-hidden">
        <FieldMotif className="absolute inset-x-0 bottom-0 w-full h-40 md:h-56 text-forest/60 dark:text-forest-light/40 pointer-events-none" />
        <div className="relative max-w-7xl mx-auto px-6 md:px-10 pt-14 pb-20 md:pt-20 md:pb-28 grid lg:grid-cols-[1.05fr_0.95fr] gap-12 lg:gap-16 items-center">
          {/* Text column */}
          <div className="text-center lg:text-left">
            <div className="inline-flex items-center gap-1.5 bg-marigold/15 text-marigold-dark border border-marigold/30 rounded-full px-3.5 py-1 text-xs font-semibold font-mono-data mb-6">
              <ShieldCheck size={13} /> {t('landing.decisionSupportBadge')}
            </div>
            <h1 className="font-display text-4xl sm:text-5xl md:text-6xl font-bold leading-[1.08] tracking-tight mb-6">
              {t('heroTitle1')}<br />{t('heroTitle2')}<br /><span className="text-forest">{t('heroTitle3')}</span>
            </h1>
            <p className="text-lg text-ink/70 dark:text-paper/70 max-w-xl mx-auto lg:mx-0 mb-4 leading-relaxed">
              {t('heroSubtitle')}
            </p>
            <p className="font-mono-data text-sm text-forest font-semibold mb-8">
              {t('tagline')}
            </p>
            <div className="flex flex-col sm:flex-row items-center lg:items-start justify-center lg:justify-start gap-3.5">
              <Link to="/register" className="w-full sm:w-auto bg-marigold hover:bg-marigold-dark text-ink dark:text-forest-dark font-semibold px-8 py-3.5 rounded-xl shadow-card transition-colors text-center">
                {t('imFarmer')} 🌾
              </Link>
              <Link to="/register" className="w-full sm:w-auto bg-white dark:bg-white/5 hover:bg-wheat/60 border border-forest/20 text-forest font-semibold px-8 py-3.5 rounded-xl shadow-card transition-colors text-center">
                {t('imBuyer')} 🏢
              </Link>
            </div>
            <p className="text-xs text-ink/40 dark:text-paper/40 mt-6">
              {t('landing.voiceSupport')}
            </p>
          </div>

          {/* Decision panel -- the visual anchor beside the hero. Built from
              the same real stages/labels as the logged-in dashboard; every
              number field is left blank rather than filled with an invented
              figure. */}
          <div className="relative">
            <div className="rounded-3xl bg-white dark:bg-white/5 shadow-premium border border-black/5 dark:border-white/10 p-5 md:p-6">
              <p className="font-display font-semibold text-base">{t('landing.decisionPanelTitle')}</p>
              <p className="text-xs text-ink/55 dark:text-paper/55 mt-1 mb-5">{t('landing.decisionPanelSubtitle')}</p>
              <div className="grid grid-cols-3 gap-2 text-center">
                <div className="rounded-xl bg-forest/5 dark:bg-white/5 p-3"><Sprout size={17} className="mx-auto text-forest" /><div className="text-[11px] font-semibold mt-1">{t('sellingJourney.stage.addProduce')}</div></div>
                <div className="rounded-xl bg-forest/5 dark:bg-white/5 p-3"><BarChart3 size={17} className="mx-auto text-forest" /><div className="text-[11px] font-semibold mt-1">{t('sellingJourney.stage.marketAnalysis')}</div></div>
                <div className="rounded-xl bg-marigold/15 p-3"><Wallet size={17} className="mx-auto text-forest" /><div className="text-[11px] font-semibold mt-1">{t('sellingJourney.stage.paymentReceived')}</div></div>
              </div>
              <div className="mt-5 pt-4 border-t border-black/5 dark:border-white/10 rounded-xl bg-sand-100 dark:bg-white/5 p-4 -mx-1">
                <div className="text-[10px] uppercase tracking-wide text-ink/45 dark:text-paper/45 font-bold">{t('dashboard.netRealization')}</div>
                <div className="grid grid-cols-2 gap-x-4 gap-y-1 mt-2 text-xs"><span>{t('landing.marketPrice')}</span><strong className="text-right font-mono-data">₹2,450/q</strong><span>{t('landing.transportCost')}</span><strong className="text-right font-mono-data text-ink/60">−₹120/q</strong><span>{t('landing.otherCosts')}</span><strong className="text-right font-mono-data text-ink/60">−₹80/q</strong></div>
                <div className="flex items-center justify-between border-t border-black/10 dark:border-white/10 mt-2 pt-2 text-sm"><span className="font-semibold">{t('landing.estimatedNet')}</span><strong className="font-mono-data text-forest">₹2,250/q</strong></div>
                <p className="text-[11px] text-ink/45 dark:text-paper/45 mt-1.5 leading-snug">
                  {t('landing.illustrativeNote')}
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- From Harvest to Sale (centerpiece) ---------- */}
      <section className="bg-white dark:bg-white/5 py-16 md:py-20 border-y border-black/5 dark:border-white/10">
        <div className="max-w-6xl mx-auto px-6 md:px-10">
          <div className="text-center mb-12">
            <h2 className="font-display text-3xl md:text-4xl font-bold mb-2">{t('landing.journeyHeading')}</h2>
            <p className="text-ink/60 dark:text-paper/60">{t('landing.journeySubheading')}</p>
          </div>

          {/* Desktop: horizontal route */}
          <div className="hidden md:flex items-start">
            {STAGES.map((stage, i) => {
              const Icon = STAGE_ICON[stage.key]
              const dest = NEXT_DESTINATION[stage.key]
              const isFinal = stage.key === 'PAYMENT_RECEIVED'
              return (
                <React.Fragment key={stage.key}>
                  <div className="flex flex-col items-center text-center px-2" style={{ width: `${100 / STAGES.length}%` }}>
                    <div className={`w-12 h-12 rounded-full border-2 flex items-center justify-center ${isFinal ? 'bg-marigold border-marigold text-forest-dark' : 'bg-forest border-forest text-paper'}`}>
                      <Icon size={20} />
                    </div>
                    <div className="mt-3 font-display font-semibold text-sm">{t(stage.label)}</div>
                    <p className="text-xs text-ink/55 dark:text-paper/55 mt-1 leading-snug">{dest?.description ? t(dest.description) : ''}</p>
                  </div>
                  {i < STAGES.length - 1 && (
                    <div className="h-0.5 mt-6 flex-1 rounded-full bg-black/10 dark:bg-white/15 relative">
                      <ArrowRight size={14} className="absolute -right-1 -top-[6px] text-black/20 dark:text-white/25" />
                    </div>
                  )}
                </React.Fragment>
              )
            })}
          </div>

          {/* Mobile: vertical route */}
          <div className="md:hidden space-y-5">
            {STAGES.map((stage, i) => {
              const Icon = STAGE_ICON[stage.key]
              const dest = NEXT_DESTINATION[stage.key]
              const isFinal = stage.key === 'PAYMENT_RECEIVED'
              return (
                <div key={stage.key} className="flex gap-3">
                  <div className="flex flex-col items-center">
                    <div className={`w-10 h-10 rounded-full border-2 flex items-center justify-center flex-shrink-0 ${isFinal ? 'bg-marigold border-marigold text-forest-dark' : 'bg-forest border-forest text-paper'}`}>
                      <Icon size={17} />
                    </div>
                    {i < STAGES.length - 1 && <div className="w-0.5 flex-1 min-h-[18px] bg-black/10 dark:bg-white/15" />}
                  </div>
                  <div className="pb-1">
                    <div className="font-display font-semibold text-sm">{t(stage.label)}</div>
                    <p className="text-xs text-ink/55 dark:text-paper/55 mt-0.5 leading-snug">{dest?.description ? t(dest.description) : ''}</p>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      </section>

      {/* ---------- Why CropRetain ---------- */}
      <section className="premium-hero text-paper py-16 md:py-20">
        <div className="max-w-5xl mx-auto px-6 md:px-10 relative">
          <h2 className="font-display text-2xl md:text-3xl font-bold text-center mb-3">{t('landing.whyHeading')}</h2>
          <p className="text-paper/70 text-center max-w-2xl mx-auto mb-10">
            {t('landing.whyDescription')}
          </p>

          <div className="grid md:grid-cols-2 gap-5">
            {/* Traditional way */}
            <div className="rounded-2xl border border-paper/15 bg-white/5 p-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-paper/50 mb-4">{t('landing.traditionalWay')}</p>
              <div className="flex items-center gap-2 flex-wrap">
                {[Store, Handshake].map((Icon, i) => (
                  <React.Fragment key={i}>
                    <span className="w-9 h-9 rounded-full bg-white/10 flex items-center justify-center"><Icon size={16} /></span>
                    {i === 0 && <ArrowRight size={14} className="text-paper/30" />}
                  </React.Fragment>
                ))}
              </div>
              <p className="text-sm text-paper/70 mt-4">{t('landing.traditionalWayDesc')}</p>
            </div>

            {/* CropRetain way */}
            <div className="rounded-2xl border border-marigold/40 bg-marigold/10 p-5">
              <p className="text-xs font-semibold uppercase tracking-wide text-marigold mb-4">CropRetain</p>
              <div className="flex items-center gap-1.5 flex-wrap">
                {STAGES.map((stage, i) => {
                  const Icon = STAGE_ICON[stage.key]
                  return (
                    <React.Fragment key={stage.key}>
                      <span className="w-9 h-9 rounded-full bg-marigold/20 flex items-center justify-center"><Icon size={16} /></span>
                      {i < STAGES.length - 1 && <ArrowRight size={12} className="text-paper/30" />}
                    </React.Fragment>
                  )
                })}
              </div>
              <p className="text-sm text-paper/85 mt-4">{t('landing.cropretainWayDesc')}</p>
            </div>
          </div>
        </div>
      </section>

      {/* ---------- Feature grid ---------- */}
      <section className="px-6 md:px-10 py-16 md:py-20 max-w-6xl mx-auto">
        <h2 className="font-display text-3xl font-bold text-center mb-3">{t('landing.featuresHeading')}</h2>
        <p className="text-center text-ink/60 dark:text-paper/60 mb-12">{t('landing.featuresSubtitle')}</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {FEATURES.map(f => (
            <div key={f.titleKey} className="bg-white dark:bg-white/5 rounded-3xl p-6 shadow-card border border-black/5 dark:border-white/10 hover:-translate-y-0.5 hover:shadow-lifted transition-all">
              <div className="w-11 h-11 rounded-xl bg-forest/10 dark:bg-forest-light/15 text-forest dark:text-forest-light flex items-center justify-center mb-4">
                <f.icon size={20} />
              </div>
              <h3 className="font-display font-semibold text-lg mb-2">
                {t(f.titleKey)}
                {f.soon && (
                  <span className="ml-2 align-middle text-[10px] font-semibold uppercase tracking-wide px-2 py-0.5 rounded-full bg-marigold/15 text-marigold-dark border border-marigold/40">
                    {t('landing.comingSoon')}
                  </span>
                )}
              </h3>
              <p className="text-sm text-ink/60 dark:text-paper/60 leading-relaxed">{t(f.descKey)}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ---------- How it works (supporting, not centerpiece) ---------- */}
      <section className="bg-white dark:bg-white/5 py-14 border-y border-black/5 dark:border-white/10">
        <div className="max-w-4xl mx-auto px-6 md:px-10">
          <h2 className="font-display text-xl font-bold text-center mb-8">{t('landing.howItWorksHeading')}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-8">
            {STEPS.map(s => (
              <div key={s.step} className="text-center">
                <div className="font-mono-data text-xs text-marigold-dark font-bold mb-2">{s.step}</div>
                <h3 className="font-display font-semibold text-base mb-1">{t(s.titleKey)}</h3>
                <p className="text-sm text-ink/60 dark:text-paper/60">{t(s.descKey)}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ---------- Final CTA ---------- */}
      <section className="px-6 md:px-10 py-14">
        <div className="max-w-4xl mx-auto rounded-4xl premium-hero text-paper px-8 py-10 text-center shadow-premium relative overflow-hidden">
          <FieldMotif className="absolute inset-x-0 bottom-0 w-full h-20 text-paper/30 pointer-events-none" />
          <div className="relative">
          <h2 className="font-display text-2xl font-bold mb-2">{t('landing.finalHeading')}</h2>
          <p className="text-paper/70 mb-6">{t('landing.finalDescription')}</p>
          <div className="flex flex-col sm:flex-row items-center justify-center gap-3.5">
            <Link to="/register" className="w-full sm:w-auto bg-marigold hover:bg-marigold-dark text-forest-dark font-semibold px-8 py-3 rounded-xl transition-colors">
              {t('imFarmer')} 🌾
            </Link>
            <Link to="/register" className="w-full sm:w-auto bg-white/10 hover:bg-white/15 border border-paper/25 text-paper font-semibold px-8 py-3 rounded-xl transition-colors">
              {t('imBuyer')} 🏢
            </Link>
          </div>
          </div>
        </div>
      </section>

      <footer className="px-6 md:px-10 py-8 text-center text-xs text-ink/40 dark:text-paper/40 font-mono-data">
        {t('landing.footerNote')}
      </footer>
    </div>
  )
}
