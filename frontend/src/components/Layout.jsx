import React, { useState } from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import {
  Home, Target, BarChart3, Package, TrendingUp, Store, ShoppingCart, Boxes,
  Briefcase, Calculator, Truck, Users, Warehouse, Handshake, Bot,
  MessageCircle, Bell, User, ShieldCheck, LogOut, Sun, Moon, Sprout,
} from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { useTheme } from '../context/ThemeContext'
import { useI18n } from '../i18n/I18nContext'
import LanguageSelector from './LanguageSelector'
import Avatar from './Avatar'

// Grouped sidebar -- every route below already existed in App.jsx before
// this reorganization; nothing added or removed, only grouped and given a
// consistent icon system in place of the previous emoji.
function useNavGroups(role, t) {
  if (role === 'transporter') {
    return [
      {
        heading: t('navOverview'),
        links: [
          { to: '/transporter/dashboard', label: t('navDashboard'), Icon: Home },
        ],
      },
      {
        heading: t('navAccount'),
        links: [
          { to: '/profile', label: t('navProfile'), Icon: User },
        ],
      },
    ]
  }
  if (role === 'buyer') {
    return [
      {
        heading: t('navOverview'),
        links: [
          { to: '/buyer/dashboard', label: t('navDashboard'), Icon: Home },
          { to: '/market-intelligence', label: t('navMarket'), Icon: BarChart3 },
          { to: '/arrivals', label: t('navArrival'), Icon: Package },
        ],
      },
      {
        heading: t('navBuying'),
        links: [
          { to: '/buyer-demands', label: t('navBuyerDemands'), Icon: ShoppingCart },
          { to: '/marketplace', label: t('navMarketplace'), Icon: Store },
          { to: '/lots', label: t('navLots'), Icon: Boxes },
          { to: '/transactions', label: t('navTransactions'), Icon: Briefcase },
          { to: '/buyer-verification', label: t('navVerification'), Icon: ShieldCheck },
        ],
      },
      {
        heading: t('navAi'),
        links: [
          { to: '/ask', label: t('navAsk'), Icon: MessageCircle },
        ],
      },
      {
        heading: t('navAccount'),
        links: [
          { to: '/profile', label: t('navProfile'), Icon: User },
        ],
      },
    ]
  }
  return [
    {
      heading: t('navOverview'),
      links: [
        { to: '/farmer/dashboard', label: t('navDashboard'), Icon: Home },
        { to: '/market-intelligence', label: t('navMarket'), Icon: BarChart3 },
        { to: '/forecast', label: t('navForecast'), Icon: TrendingUp },
        { to: '/arrivals', label: t('navArrival'), Icon: Package },
      ],
    },
    {
      heading: t('navSelling'),
      links: [
        { to: '/best-option', label: t('navBestOption'), Icon: Target },
        { to: '/marketplace', label: t('navMarketplace'), Icon: Store },
        { to: '/buyer-demands', label: t('navBuyerDemands'), Icon: ShoppingCart },
        { to: '/lots', label: t('navLots'), Icon: Boxes },
        { to: '/transactions', label: t('navTransactions'), Icon: Briefcase },
      ],
    },
    {
      heading: t('navDecisionTools'),
      links: [
        { to: '/soil-advisor', label: t('navSoil'), Icon: Sprout },
        { to: '/profit-calculator', label: t('navProfit'), Icon: Calculator },
        { to: '/transport', label: t('navTransport'), Icon: Truck },
        { to: '/farmpool', label: t('navFarmPool'), Icon: Users },
        { to: '/storage', label: t('navStorage'), Icon: Warehouse },
        { to: '/group-selling', label: t('navGroup'), Icon: Handshake },
      ],
    },
    {
      heading: t('navAi'),
      links: [
        { to: '/advisor', label: t('navAdvisor'), Icon: Bot },
        { to: '/ask', label: t('navAsk'), Icon: MessageCircle },
      ],
    },
    {
      heading: t('navAccount'),
      links: [
        { to: '/notifications', label: t('navAlerts'), Icon: Bell },
        { to: '/profile', label: t('navProfile'), Icon: User },
      ],
    },
  ]
}

export default function Layout({ children }) {
  const { role, user, logout } = useAuth()
  const { t } = useI18n()
  const { theme, toggleTheme } = useTheme()
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const groups = useNavGroups(role, t)

  function handleLogout() {
    logout()
    navigate('/')
  }

  return (
    <div className="min-h-screen dashboard-shell flex">
      <aside className={`fixed md:static z-30 inset-y-0 left-0 w-64 md:w-16 lg:w-64 bg-[var(--sidebar-bg)] text-paper flex flex-col transition-all duration-200 shadow-[0_0_30px_rgba(14,20,70,0.22)] ${open ? 'translate-x-0' : '-translate-x-full'} md:translate-x-0`}>
        <div className="px-5 py-5 border-b border-white/10 md:px-2 md:py-4 lg:px-5 lg:py-5 flex items-center gap-2.5 md:justify-center lg:justify-start">
          <img
            src="/apple-touch-icon.png"
            alt="CropRetain"
            className="w-8 h-8 rounded-full object-cover flex-shrink-0 ring-2 ring-white/10"
          />
          <div className="md:hidden lg:block">
            <div className="font-display font-bold text-xl tracking-tight leading-none">CropRetain</div>
            <div className="text-[11px] text-marigold-light font-mono-data mt-0.5">{t('tagline')}</div>
          </div>
        </div>
        <nav className="flex-1 overflow-y-auto py-4 px-3 md:px-2 lg:px-3 space-y-5">
          {groups.map(group => (
            <div key={group.heading}>
              <div className="hidden lg:block px-3 mb-1.5 text-[10px] font-bold uppercase tracking-[0.15em] text-paper/40">
                {group.heading}
              </div>
              <div className="space-y-1.5">
                {group.links.map(link => (
                  <NavLink
                    key={link.to}
                    to={link.to}
                    onClick={() => setOpen(false)}
                    title={link.label}
                    className={({ isActive }) =>
                      `relative flex items-center gap-3 md:justify-center lg:justify-start px-3 md:px-2 lg:px-3 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                        isActive
                          ? 'bg-white/12 text-paper before:content-[""] before:absolute before:left-0 before:top-2 before:bottom-2 before:w-[3px] before:rounded-full before:bg-marigold'
                          : 'text-paper/75 hover:bg-white/8 hover:text-paper'
                      }`
                    }
                  >
                    <link.Icon size={17} strokeWidth={2} className="flex-shrink-0" />
                    <span className="md:hidden lg:inline">{link.label}</span>
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>
        <div className="px-4 py-4 border-t border-white/10 md:px-2 lg:px-4">
          <div className="flex items-center gap-2.5 mb-3 md:justify-center lg:justify-start">
            <Avatar role={role} name={role === 'buyer' ? user?.company_name : user?.name} size="sm" />
            <div className="min-w-0 md:hidden lg:block">
              <div className="text-sm font-semibold truncate">{role === 'buyer' ? user?.company_name : user?.name}</div>
              <div className="text-xs text-paper/50 truncate">{user?.email}</div>
            </div>
          </div>
          <button onClick={handleLogout} title={t('logout')} className="w-full flex items-center justify-center gap-2 text-sm bg-white/9 hover:bg-white/14 rounded-xl py-2.5 transition-colors border border-white/10">
            <LogOut size={15} />
            <span className="md:hidden lg:inline">{t('logout')}</span>
          </button>
        </div>
      </aside>

      {open && <div className="fixed inset-0 bg-black/40 z-20 md:hidden" onClick={() => setOpen(false)} />}

      <div className="flex-1 flex flex-col min-w-0">
        <header className="flex items-center justify-between bg-[rgba(255,255,255,0.86)] backdrop-blur-xl border-b border-black/5 px-4 py-3 sticky top-0 z-10 md:px-8 md:py-4">
          <div className="flex items-center gap-2 md:hidden">
            <button onClick={() => setOpen(true)} className="text-2xl leading-none text-forest" aria-label={t('layout.openNavMenu')}>☰</button>
            <img src="/apple-touch-icon.png" alt="CropRetain" className="w-7 h-7 rounded-full object-cover" />
          </div>
          <div className="hidden md:block" />
          <div className="flex items-center gap-3">
            <button
              onClick={toggleTheme}
              className="text-sm px-3 py-1.5 rounded-lg border border-forest/10 hover:bg-forest/5 transition-colors flex items-center justify-center text-forest"
              aria-label={t('layout.toggleDarkMode')}
              title={theme === 'dark' ? t('layout.switchToLightMode') : t('layout.switchToDarkMode')}
            >
              {theme === 'dark' ? <Sun size={16} /> : <Moon size={16} />}
            </button>
            <LanguageSelector />
            <Avatar role={role} name={role === 'buyer' ? user?.company_name : user?.name} size="sm" />
          </div>
        </header>
        <main className="flex-1 p-4 pb-24 md:p-8 md:pb-8 max-w-[1500px] w-full mx-auto text-ink">
          {children}
        </main>
      </div>
      <nav className="md:hidden fixed bottom-0 inset-x-0 z-20 bg-white/95 backdrop-blur border-t border-black/8 grid grid-cols-5 px-2 py-2 pb-[calc(0.5rem+env(safe-area-inset-bottom))]" aria-label={t('layout.mobileNavigation')}>
        {(role === 'buyer'
          ? [
              { to: '/buyer/dashboard', label: t('navDashboard'), Icon: Home },
              { to: '/marketplace', label: t('navMarketplace'), Icon: Store },
              { to: '/buyer-demands', label: t('navBuyerDemands'), Icon: ShoppingCart },
              { to: '/ask', label: t('navAsk'), Icon: MessageCircle },
              { to: '/profile', label: t('navProfile'), Icon: User },
            ]
          : [
              { to: '/farmer/dashboard', label: t('navDashboard'), Icon: Home },
              { to: '/market-intelligence', label: t('navMarket'), Icon: BarChart3 },
              { to: '/best-option', label: t('navBestOption'), Icon: Target },
              { to: '/ask', label: t('navAsk'), Icon: MessageCircle },
              { to: '/profile', label: t('navProfile'), Icon: User },
            ]
        ).map(({ to, label, Icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) => `flex flex-col items-center gap-1 py-1 text-[10px] font-semibold ${isActive ? 'text-forest dark:text-marigold' : 'text-ink/50 dark:text-paper/50'}`}
          >
            {({ isActive }) => (
              <>
                <Icon size={18} strokeWidth={isActive ? 2.5 : 2} />
                <span>{label}</span>
              </>
            )}
          </NavLink>
        ))}
      </nav>
    </div>
  )
}
