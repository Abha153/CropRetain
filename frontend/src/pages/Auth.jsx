import React, { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Leaf, Sprout, Building2, Truck, ShieldCheck, ArrowRight } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import { useI18n } from '../i18n/I18nContext'
import { DEFAULT_DEMO_LOCATION } from '../utils/location'

const CROP_OPTIONS = [
  { value: 'Tomato', key: 'auth.crop.tomato' },
  { value: 'Paddy (Rice)', key: 'auth.crop.paddyRice' },
  { value: 'Wheat', key: 'auth.crop.wheat' },
  { value: 'Potato', key: 'auth.crop.potato' },
  { value: 'Onion', key: 'auth.crop.onion' },
  { value: 'Soybean', key: 'auth.crop.soybean' },
  { value: 'Maize', key: 'auth.crop.maize' },
  { value: 'Chana (Gram)', key: 'auth.crop.chanaGram' },
  { value: 'Groundnut', key: 'auth.crop.groundnut' },
  { value: 'Sugarcane', key: 'auth.crop.sugarcane' },
]

const VEHICLE_TYPE_OPTIONS = [
  { value: 'mini-truck', key: 'auth.vehicleType.miniTruck' },
  { value: 'truck', key: 'auth.vehicleType.truck' },
  { value: 'tempo', key: 'auth.vehicleType.tempo' },
  { value: 'tractor-trolley', key: 'auth.vehicleType.tractorTrolley' },
]

function getDemoAccounts(t) {
  return [
    { label: t('auth.demoAccountRamesh'), email: 'ramesh@cropwise.demo', role: 'farmer' },
    { label: t('auth.demoAccountSunita'), email: 'sunita@cropwise.demo', role: 'farmer' },
    { label: t('auth.demoAccountFreshFoods'), email: 'freshfoods@cropwise.demo', role: 'buyer' },
    { label: t('auth.demoAccountGreenBasket'), email: 'greenbasket@cropwise.demo', role: 'buyer' },
  ]
}

export default function Auth({ mode = 'login' }) {
  const [tab, setTab] = useState(mode)
  const [userType, setUserType] = useState('farmer')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const { loginFarmer, registerFarmer, registerBuyer, registerTransporter } = useAuth()
  const { code: uiLanguage, t } = useI18n()
  const demoAccounts = getDemoAccounts(t)
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [location, setLocation] = useState(DEFAULT_DEMO_LOCATION)
  const [phone, setPhone] = useState('')
  const [crops, setCrops] = useState([])
  const [buyerType, setBuyerType] = useState('wholesaler')
  const [serviceArea, setServiceArea] = useState('')
  const [vehicleTypes, setVehicleTypes] = useState([])

  async function afterLogin(role) {
    navigate(role === 'buyer' ? '/buyer/dashboard' : role === 'transporter' ? '/transporter/dashboard' : '/farmer/dashboard')
  }

  async function handleLogin(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      const data = await loginFarmer(email, password) // login endpoint handles both roles
      await afterLogin(data.role)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function handleRegister(e) {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      if (userType === 'farmer') {
        const data = await registerFarmer({ name, email, password, location, phone, crops, preferred_language: uiLanguage })
        await afterLogin(data.role)
      } else if (userType === 'transporter') {
        const data = await registerTransporter({ name, email, password, phone, service_area: serviceArea, vehicle_types: vehicleTypes, preferred_language: uiLanguage })
        await afterLogin(data.role)
      } else {
        const data = await registerBuyer({ company_name: name, email, password, location, phone, buyer_type: buyerType, crops_of_interest: crops, preferred_language: uiLanguage })
        await afterLogin(data.role)
      }
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  function toggleCrop(c) {
    setCrops(prev => prev.includes(c) ? prev.filter(x => x !== c) : [...prev, c])
  }

  function getVehicleTypeLabel(value) {
    return t(VEHICLE_TYPE_OPTIONS.find(option => option.value === value)?.key || 'auth.vehicleType.truck')
  }

  async function quickDemoLogin(demoEmail) {
    setError('')
    setLoading(true)
    try {
      const data = await loginFarmer(demoEmail, 'demo1234')
      await afterLogin(data.role)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-[#f4f7f4] flex flex-col lg:flex-row">
      <div className="hidden lg:flex lg:w-1/2 xl:w-3/5 bg-[#161E57] text-paper flex-col justify-between p-10 xl:p-16 relative overflow-hidden">
        <div className="absolute -right-24 -bottom-24 w-96 h-96 bg-marigold/10 rounded-full blur-3xl" aria-hidden="true" />
        <div className="absolute -left-16 -top-16 w-72 h-72 bg-white/5 rounded-full blur-3xl" aria-hidden="true" />

        <Link to="/" className="relative z-10 flex items-center gap-2 font-display font-bold text-2xl">
          <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-white/10 border border-white/10">
            <Leaf size={18} />
          </span>
          CropRetain
        </Link>

        <div className="relative z-10 max-w-lg">
          <div className="inline-flex items-center gap-2 rounded-full border border-white/15 bg-white/5 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.12em] text-marigold-light mb-5">
            <ShieldCheck size={14} /> {t('auth.trustedAgriIntelligence')}
          </div>
          <h1 className="font-display text-4xl xl:text-5xl font-bold leading-tight mb-5">
            {t('heroTitle1')}<br />{t('heroTitle2')}<br /><span className="text-marigold-light">{t('heroTitle3')}</span>
          </h1>
          <p className="text-paper/70 text-lg leading-relaxed">
            {t('heroSubtitle')}
          </p>
        </div>

        <div className="relative z-10 flex items-center gap-4 text-sm text-paper/75">
          <div className="flex items-center gap-2"><Sprout size={16} className="text-marigold-light" /> {t('auth.farmers')}</div>
          <div className="flex items-center gap-2"><Building2 size={16} className="text-marigold-light" /> {t('auth.buyers')}</div>
        </div>
      </div>

      <div className="flex-1 flex items-center justify-center p-4 sm:p-6 lg:p-10 xl:p-16">
        <div className="w-full max-w-md">
          <Link to="/" className="lg:hidden font-display font-bold text-2xl text-forest flex items-center justify-center gap-2 mb-8">
            <span className="inline-flex h-9 w-9 items-center justify-center rounded-lg bg-forest/8 border border-forest/10">
              <Leaf size={18} />
            </span>
            CropRetain
          </Link>

          <div className="bg-white rounded-3xl shadow-card border border-black/5 p-6 sm:p-8">
          <div className="flex bg-mist rounded-xl p-1 mb-6">
            <button onClick={() => setTab('login')} className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors ${tab === 'login' ? 'bg-forest text-paper' : 'text-forest/70'}`}>{t('login')}</button>
            <button onClick={() => setTab('register')} className={`flex-1 py-2 rounded-lg text-sm font-semibold transition-colors ${tab === 'register' ? 'bg-forest text-paper' : 'text-forest/70'}`}>{t('register')}</button>
          </div>

          {tab === 'register' && (
            <div className="flex gap-2 mb-5">
              <button onClick={() => setUserType('farmer')} className={`flex-1 py-2 rounded-lg text-sm font-medium border ${userType === 'farmer' ? 'border-marigold bg-marigold/10 text-marigold-dark' : 'border-black/10 text-ink/60'}`}>
                <span className="inline-flex items-center gap-2"><Sprout size={14} />{t('auth.farmer')}</span>
              </button>
              <button onClick={() => setUserType('buyer')} className={`flex-1 py-2 rounded-lg text-sm font-medium border ${userType === 'buyer' ? 'border-rain bg-rain/10 text-rain' : 'border-black/10 text-ink/60'}`}>
                <span className="inline-flex items-center gap-2"><Building2 size={14} />{t('auth.buyer')}</span>
              </button>
              <button onClick={() => setUserType('transporter')} className={`flex-1 py-2 rounded-lg text-sm font-medium border ${userType === 'transporter' ? 'border-forest bg-forest/10 text-forest' : 'border-black/10 text-ink/60'}`}>
                <span className="inline-flex items-center gap-2"><Truck size={14} />{t('auth.transporter')}</span>
              </button>
            </div>
          )}

          {error && <div className="bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 text-red-700 dark:text-red-300 text-sm rounded-lg px-3 py-2 mb-4">{error}</div>}

          {tab === 'login' ? (
            <form onSubmit={handleLogin} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('auth.email')}</label>
                <input type="email" required value={email} onChange={e => setEmail(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper" placeholder={t('auth.emailPlaceholder')} />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('auth.password')}</label>
                <input type="password" required value={password} onChange={e => setPassword(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper" placeholder="••••••••" />
              </div>
              <button disabled={loading} type="submit" className="w-full bg-marigold hover:bg-marigold-dark text-ink dark:text-paper font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-60">
                {loading ? t('auth.loggingIn') : t('login')}
              </button>
            </form>
          ) : (
            <form onSubmit={handleRegister} className="space-y-4">
              <div>
                <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{userType === 'farmer' ? t('auth.fullName') : userType === 'transporter' ? t('auth.fullName') : t('auth.companyName')}</label>
                <input required value={name} onChange={e => setName(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper" />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('auth.email')}</label>
                <input type="email" required value={email} onChange={e => setEmail(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper" />
              </div>
              <div>
                <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('auth.password')}</label>
                <input type="password" required minLength={6} value={password} onChange={e => setPassword(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper" />
              </div>
              {userType === 'transporter' ? (
                <>
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('auth.serviceArea')}</label>
                      <input value={serviceArea} onChange={e => setServiceArea(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper" placeholder={t('auth.serviceAreaPlaceholder')} />
                    </div>
                    <div>
                      <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('auth.phone')}</label>
                      <input value={phone} onChange={e => setPhone(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper" placeholder={t('auth.phonePlaceholder')} />
                    </div>
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('auth.vehicleTypes')}</label>
                    <div className="flex flex-wrap gap-1.5">
                      {VEHICLE_TYPE_OPTIONS.map(option => (
                        <button type="button" key={option.value} onClick={() => setVehicleTypes(prev => prev.includes(option.value) ? prev.filter(x => x !== option.value) : [...prev, option.value])} className={`text-xs px-2.5 py-1.5 rounded-full border ${vehicleTypes.includes(option.value) ? 'bg-forest text-paper border-forest' : 'border-black/10 dark:border-white/15 text-ink/60 dark:text-paper/60'}`}>
                          {t(option.key)}
                        </button>
                      ))}
                    </div>
                  </div>
                </>
              ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('common.location')}</label>
                    <input required value={location} onChange={e => setLocation(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper" placeholder={t('auth.locationPlaceholder')} />
                  </div>
                  <div>
                    <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('auth.phone')}</label>
                    <input value={phone} onChange={e => setPhone(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper" placeholder={t('auth.phonePlaceholder')} />
                  </div>
                </div>
              )}
              {userType === 'buyer' && (
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{t('auth.buyerType')}</label>
                  <select value={buyerType} onChange={e => setBuyerType(e.target.value)} className="w-full border border-black/10 dark:border-white/15 rounded-lg px-3 py-2.5 text-sm focus:outline-none focus:ring-2 focus:ring-forest/30 bg-white dark:bg-white/5 dark:text-paper">
                    <option value="wholesaler">{t('auth.wholesaler')}</option>
                    <option value="retailer">{t('auth.retailer')}</option>
                    <option value="processor">{t('auth.foodProcessor')}</option>
                    <option value="exporter">{t('auth.exporter')}</option>
                    <option value="fpo">{t('auth.fpoCooperative')}</option>
                  </select>
                </div>
              )}
              {userType !== 'transporter' && (
                <div>
                  <label className="text-xs font-semibold text-ink/60 dark:text-paper/60 block mb-1">{userType === 'farmer' ? t('auth.cropsYouGrow') : t('auth.cropsYouBuy')}</label>
                  <div className="flex flex-wrap gap-1.5">
                    {CROP_OPTIONS.map(option => (
                      <button type="button" key={option.value} onClick={() => toggleCrop(option.value)} className={`text-xs px-2.5 py-1.5 rounded-full border ${crops.includes(option.value) ? 'bg-forest text-paper border-forest' : 'border-black/10 dark:border-white/15 text-ink/60 dark:text-paper/60'}`}>
                        {t(option.key)}
                      </button>
                    ))}
                  </div>
                </div>
              )}
              <button disabled={loading} type="submit" className="w-full bg-marigold hover:bg-marigold-dark text-ink dark:text-paper font-semibold py-2.5 rounded-lg transition-colors disabled:opacity-60">
                {loading ? t('auth.creatingAccount') : t('auth.createAccount')}
              </button>
            </form>
          )}

          <div className="mt-6 pt-5 border-t border-black/5 dark:border-white/10">
            <p className="text-xs font-semibold text-ink/50 dark:text-paper/50 mb-2">{t('auth.demoAccountHint')}</p>
            <div className="grid grid-cols-1 gap-1.5">
              {demoAccounts.map(d => (
                <button key={d.email} onClick={() => quickDemoLogin(d.email)} className="text-left text-xs bg-wheat dark:bg-white/5 hover:bg-marigold/20 rounded-lg px-3 py-2 transition-colors">
                  {d.label}
                </button>
              ))}
            </div>
          </div>
          </div>
        </div>
      </div>
    </div>
  )
}
