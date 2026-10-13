import React, { useEffect, useState, useCallback } from 'react'
import { BarChart3, ShieldCheck, Users, Tractor, Package, ArrowUpRight, Clock3, CheckCircle2, CircleAlert, UserRoundCheck, TrendingUp, Truck, LogIn, Wallet, Search, LockKeyhole } from 'lucide-react'
import { api } from '../api/client'
import StatCard from '../components/StatCard'
import LoadingSpinner from '../components/LoadingSpinner'
import Badge from '../components/Badge'
import Avatar from '../components/Avatar'
import { useI18n } from '../i18n/I18nContext'

function AdminLogin({ onSuccess }) {
  const { t } = useI18n()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function submit(e) {
    e.preventDefault()
    setLoading(true)
    setError('')
    try {
      const data = await api.adminLogin(username, password)
      localStorage.setItem('cropretain_admin_token', data.access_token)
      onSuccess(data.access_token)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-sm mx-auto mt-16">
      <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-6">
        <div className="flex items-center gap-2 mb-1 text-forest"><LockKeyhole size={18} /><h1 className="font-display text-xl font-bold">{t('adminDashboard.adminAccess')}</h1></div>
        <p className="text-sm text-ink/60 dark:text-paper/60 mb-4">{t('adminDashboard.adminAccessDesc')}</p>
        {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2 mb-4">{error}</div>}
        <form onSubmit={submit} className="space-y-3">
          <input value={username} onChange={e => setUsername(e.target.value)} placeholder={t('ui.adminUsername')} autoComplete="username" className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper" />
          <input type="password" value={password} onChange={e => setPassword(e.target.value)} placeholder={t('ui.adminPassword')} autoComplete="current-password" className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm bg-white dark:bg-white/5 dark:text-paper" />
          <button disabled={loading} className="w-full bg-forest text-paper font-semibold rounded-lg py-2.5 disabled:opacity-60">
            {loading ? t('auth.loggingIn') : t('login')}
          </button>
        </form>
        {/*
          No credentials are ever shown here, hard-coded, or shipped in the
          frontend bundle. This form only forwards whatever you type to
          POST /auth/admin/login -- the backend checks it against
          ADMIN_USERNAME / ADMIN_PASSWORD, which live in the server
          environment only. If you don't know the credentials for this
          deployment, check that deployment's environment variables (or
          backend/.env locally) -- never this page's source.
        */}
        <p className="text-xs text-ink/40 dark:text-paper/40 mt-4">{t('adminDashboard.noAccessHint')}</p>
      </div>
    </div>
  )
}

function fmtDateTime(iso, neverLabel) {
  if (!iso) return neverLabel
  return new Date(iso).toLocaleString()
}

export default function AdminDashboard() {
  const { t } = useI18n()
  const [token, setToken] = useState(() => localStorage.getItem('cropretain_admin_token'))
  const [impact, setImpact] = useState(null)
  const [activity, setActivity] = useState(null)
  const [recent, setRecent] = useState(null)
  const [users, setUsers] = useState(null)
  const [userSearch, setUserSearch] = useState('')
  const [error, setError] = useState('')

  const LOGIN_STATUS_KEY = {
    never_logged_in: 'adminDashboard.loginStatus.neverLoggedIn',
    active_today: 'adminDashboard.loginStatus.activeToday',
    active_this_week: 'adminDashboard.loginStatus.activeThisWeek',
    inactive: 'adminDashboard.loginStatus.inactive',
  }
  const LOGIN_STATUS_TONE = {
    never_logged_in: 'neutral',
    active_today: 'success',
    active_this_week: 'info',
    inactive: 'warning',
  }
  const ROLE_KEY = { farmer: 'auth.farmer', buyer: 'auth.buyer', admin: 'role.admin' }

  const handleAuthFailure = useCallback(() => {
    localStorage.removeItem('cropretain_admin_token')
    setToken(null)
  }, [])

  useEffect(() => {
    if (!token) return
    Promise.all([
      api.getImpact(token),
      api.getUserActivity(token),
      api.getRecentActivity(token, 20),
      api.getAdminUsers(token),
    ])
      .then(([impactData, activityData, recentData, usersData]) => {
        setImpact(impactData)
        setActivity(activityData)
        setRecent(recentData)
        setUsers(usersData)
      })
      .catch((err) => {
        setError(err.message)
        handleAuthFailure()
      })
  }, [token, handleAuthFailure])

  // Re-query just the user list when the admin searches by name/email --
  // no need to re-fetch impact/activity/recent-activity for that.
  useEffect(() => {
    if (!token) return
    const timeoutId = setTimeout(() => {
      api.getAdminUsers(token, { q: userSearch || undefined }).then(setUsers).catch(() => {})
    }, 250)
    return () => clearTimeout(timeoutId)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [userSearch])

  if (!token) return <AdminLogin onSuccess={(tok) => { setToken(tok); setError('') }} />
  if (!impact || !activity || !recent || !users) return <LoadingSpinner label={t('adminDashboard.loadingDashboard')} />

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <div className="flex items-center gap-2">
          <BarChart3 size={22} className="text-forest" />
          <h1 className="font-display text-3xl font-bold">{t('navImpactDashboard')}</h1>
        </div>
        <button
          onClick={() => { localStorage.removeItem('cropretain_admin_token'); setToken(null) }}
          className="text-sm text-ink/50 dark:text-paper/50 hover:underline"
        >
          {t('logout')}
        </button>
      </div>
      <p className="text-ink/60 dark:text-paper/60 mb-6">{t('adminDashboard.subtitle')}</p>
      {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2 mb-4">{error}</div>}

      <div className="bg-forest text-paper rounded-2xl p-6 mb-6">
        <div className="text-xs uppercase tracking-wide text-marigold-light font-semibold mb-1">{t('adminDashboard.additionalIncome')}</div>
        <div className="font-mono-data text-4xl font-bold">₹{impact.estimated_additional_farmer_income.toLocaleString()}</div>
        <p className="text-paper/70 text-sm mt-2">{t('adminDashboard.additionalIncomeDesc')}</p>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
        <StatCard label={t('adminDashboard.farmersConnected')} value={impact.farmers_connected} icon={<Tractor size={16} />} />
        <StatCard label={t('adminDashboard.buyersConnected')} value={impact.buyers_connected} icon={<Users size={16} />} />
        <StatCard label={t('adminDashboard.produceListed')} value={`${impact.total_produce_listed_kg.toLocaleString()} kg`} icon={<Package size={16} />} />
        <StatCard label={t('adminDashboard.activeListings')} value={impact.active_listings} icon={<Package size={16} />} />
        <StatCard label={t('adminDashboard.successfulTransactions')} value={impact.successful_transactions} icon={<CheckCircle2 size={16} />} />
        <StatCard label={t('adminDashboard.transactionsInProgress')} value={impact.total_transactions_initiated - impact.successful_transactions} icon={<Clock3 size={16} />} />
        <StatCard label={t('adminDashboard.totalTransactionValue')} value={`₹${impact.total_transaction_value.toLocaleString()}`} icon={<Wallet size={16} />} />
        <StatCard label={t('adminDashboard.avgPriceImprovement')} value={`${impact.average_price_improvement_pct}%`} icon={<ArrowUpRight size={16} />} />
        <StatCard label={t('adminDashboard.transportSavings')} value={`₹${impact.estimated_transport_savings.toLocaleString()}`} icon={<Truck size={16} />} />
      </div>

      {/* ---------------- USER ACTIVITY ---------------- */}
      <div className="flex items-baseline justify-between mb-1">
        <div className="flex items-center gap-2">
          <UserRoundCheck size={20} className="text-forest" />
          <h2 className="font-display text-2xl font-bold">{t('adminDashboard.userActivity')}</h2>
        </div>
        <span className="text-xs text-ink/40 dark:text-paper/40 font-mono-data">{t('adminDashboard.asOfUtc', { datetime: fmtDateTime(activity.as_of, t('adminDashboard.never')) })}</span>
      </div>
      <p className="text-ink/60 dark:text-paper/60 mb-4 text-sm">{t('adminDashboard.userActivityDesc')}</p>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
        <StatCard label={t('adminDashboard.totalRegisteredFarmers')} value={activity.total_registered_farmers} icon={<Tractor size={16} />} />
        <StatCard label={t('adminDashboard.totalRegisteredBuyers')} value={activity.total_registered_buyers} icon={<Users size={16} />} />
        <StatCard label={t('adminDashboard.registrationsToday')} value={activity.registrations_today} icon={<TrendingUp size={16} />} />
        <StatCard label={t('adminDashboard.registrationsThisWeek')} value={activity.registrations_this_week} icon={<BarChart3 size={16} />} />
        <StatCard label={t('adminDashboard.uniqueUsersToday')} value={activity.unique_users_logged_in_today} icon={<CheckCircle2 size={16} />} tone="marigold" />
        <StatCard label={t('adminDashboard.uniqueUsersThisWeek')} value={activity.unique_users_logged_in_this_week} icon={<CheckCircle2 size={16} />} />
        <StatCard label={t('adminDashboard.successfulLoginsToday')} value={activity.successful_login_events_today} icon={<LogIn size={16} />} />
        <StatCard label={t('adminDashboard.successfulLoginsThisMonth')} value={activity.successful_login_events_this_month} icon={<LogIn size={16} />} />
        <StatCard label={t('adminDashboard.failedLoginsToday')} value={activity.failed_login_attempts_today} icon={<CircleAlert size={16} />} />
      </div>

      {/* ---------------- RECENT ACTIVITY ---------------- */}
      <div className="flex items-center gap-2 mb-1">
        <Clock3 size={20} className="text-forest" />
        <h2 className="font-display text-2xl font-bold">{t('adminDashboard.recentActivity')}</h2>
      </div>
      <p className="text-ink/60 dark:text-paper/60 mb-4 text-sm">{t('adminDashboard.recentActivityDesc')}</p>
      <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 overflow-x-auto mb-10">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-forest/60 border-b border-black/5 dark:border-white/10">
              <th className="px-4 py-3">{t('adminDashboard.colUser')}</th>
              <th className="px-4 py-3">{t('adminDashboard.colRole')}</th>
              <th className="px-4 py-3">{t('adminDashboard.colLoginTime')}</th>
              <th className="px-4 py-3">{t('adminDashboard.colStatus')}</th>
            </tr>
          </thead>
          <tbody>
            {recent.events.length === 0 && (
              <tr><td colSpan={4} className="px-4 py-6 text-center text-ink/40 dark:text-paper/40">{t('adminDashboard.noLoginActivity')}</td></tr>
            )}
            {recent.events.map((e, i) => (
              <tr key={i} className="border-b border-black/5 dark:border-white/5 last:border-0">
                <td className="px-4 py-3">
                  <div className="font-semibold">{e.name || t('adminDashboard.unknown')}</div>
                  {e.email && <div className="text-xs text-ink/50 dark:text-paper/50">{e.email}</div>}
                </td>
                <td className="px-4 py-3">{t(ROLE_KEY[e.role] || 'role.admin')}</td>
                <td className="px-4 py-3 font-mono-data text-xs">{fmtDateTime(e.login_time, t('adminDashboard.never'))}</td>
                <td className="px-4 py-3">
                  <Badge tone={e.success ? 'success' : 'warning'}>{e.success ? t('adminDashboard.success') : t('adminDashboard.failed')}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* ---------------- REGISTERED USERS & LOGIN STATUS ---------------- */}
      <div className="flex items-center justify-between mb-1 gap-4 flex-wrap">
        <div className="flex items-center gap-2">
          <Search size={18} className="text-forest" />
          <h2 className="font-display text-2xl font-bold">{t('adminDashboard.registeredUsers')}</h2>
        </div>
        <input
          value={userSearch}
          onChange={e => setUserSearch(e.target.value)}
          placeholder={t('adminDashboard.searchByNameEmail')}
          className="border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-sm bg-white dark:bg-white/5 dark:text-paper w-64"
        />
      </div>
      <p className="text-ink/60 dark:text-paper/60 mb-4 text-sm">{t('adminDashboard.registeredUsersDesc')}</p>
      <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs uppercase tracking-wide text-forest/60 border-b border-black/5 dark:border-white/10">
              <th className="px-4 py-3">{t('adminDashboard.colUser')}</th>
              <th className="px-4 py-3">{t('adminDashboard.colRole')}</th>
              <th className="px-4 py-3">{t('adminDashboard.colRegistered')}</th>
              <th className="px-4 py-3">{t('adminDashboard.colLastLogin')}</th>
              <th className="px-4 py-3">{t('adminDashboard.colLoginStatus')}</th>
            </tr>
          </thead>
          <tbody>
            {users.users.length === 0 && (
              <tr><td colSpan={5} className="px-4 py-6 text-center text-ink/40 dark:text-paper/40">{t('adminDashboard.noMatchingUsers')}</td></tr>
            )}
            {users.users.map((u) => (
              <tr key={`${u.role}-${u.id}`} className="border-b border-black/5 dark:border-white/5 last:border-0">
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <Avatar role={u.role} name={u.name} size="sm" />
                    <div>
                      <div className="font-semibold">{u.name}</div>
                      <div className="text-xs text-ink/50 dark:text-paper/50">{u.email}</div>
                    </div>
                  </div>
                </td>
                <td className="px-4 py-3">{t(ROLE_KEY[u.role] || 'role.admin')}</td>
                <td className="px-4 py-3 font-mono-data text-xs">{fmtDateTime(u.registered_at, t('adminDashboard.never'))}</td>
                <td className="px-4 py-3 font-mono-data text-xs">{fmtDateTime(u.last_login, t('adminDashboard.never'))}</td>
                <td className="px-4 py-3">
                  <Badge tone={LOGIN_STATUS_TONE[u.login_status] || 'neutral'}>{t(LOGIN_STATUS_KEY[u.login_status] || 'adminDashboard.loginStatus.inactive')}</Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
