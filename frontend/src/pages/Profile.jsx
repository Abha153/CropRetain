import React, { useState } from 'react'
import { Mail, MapPin, Sprout, BriefcaseBusiness, Star, PencilLine, Save } from 'lucide-react'
import { useAuth } from '../context/AuthContext'
import { api } from '../api/client'
import Badge from '../components/Badge'
import Avatar from '../components/Avatar'
import { useI18n } from '../i18n/I18nContext'

export default function Profile() {
  const { user, role, setUser } = useAuth()
  const { t } = useI18n()
  const [name, setName] = useState(user?.name || '')
  const [location, setLocation] = useState(user?.location || '')
  const [phone, setPhone] = useState(user?.phone || '')
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState('')

  async function save(e) {
    e.preventDefault()
    setSaving(true)
    setMessage('')
    try {
      const updated = await api.updateFarmerProfile({ name, location, phone })
      setUser(updated)
      localStorage.setItem('cropretain_user', JSON.stringify(updated))
      setMessage(t('profile.updated'))
    } catch (e) {
      setMessage(e.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <p className="text-xs font-semibold uppercase tracking-[0.16em] text-forest/60">{t('profile.account')}</p>
        <h1 className="font-display text-3xl font-bold mt-2">{t('navProfile')}</h1>
      </div>

      <div className="bg-white rounded-3xl shadow-card border border-black/5 p-6">
        <div className="flex items-center gap-3 mb-4">
          <Avatar role={role} name={role === 'buyer' ? user?.company_name : user?.name} size="lg" />
          <div>
            <div className="font-display font-semibold text-lg">{role === 'buyer' ? user?.company_name : user?.name}</div>
            <Badge tone={role === 'buyer' ? 'forest' : 'marigold'}>{role === 'buyer' ? user?.buyer_type : t('profile.farmer')}</Badge>
          </div>
        </div>
        <div className="space-y-2 text-sm text-ink/60">
          <div className="flex items-center gap-2"><Mail size={14} className="text-forest" /> {user?.email}</div>
          <div className="flex items-center gap-2"><MapPin size={14} className="text-forest" /> {user?.location}</div>
          {role === 'farmer' && user?.crops?.length > 0 && <div className="flex items-center gap-2"><Sprout size={14} className="text-forest" /> {t('profile.growing')}: {user.crops.join(', ')}</div>}
          {role === 'farmer' && user?.fpo_group && <div className="flex items-center gap-2"><BriefcaseBusiness size={14} className="text-forest" /> {t('profile.fpo')}: {user.fpo_group}</div>}
          {role === 'farmer' && <div className="flex items-center gap-2"><Star size={14} className="text-forest" /> {t('profile.rating')}: {user?.rating}/5</div>}
          {role === 'buyer' && <div className="flex items-center gap-2"><Star size={14} className="text-forest" /> {t('profile.reliability')}: {user?.reliability_score}/100</div>}
        </div>
      </div>

      {role === 'farmer' && (
        <form onSubmit={save} className="bg-white rounded-3xl shadow-card border border-black/5 p-6 space-y-4">
          <div className="flex items-center gap-2 text-forest font-semibold">
            <PencilLine size={16} /> {t('profile.editDetails')}
          </div>
          {message && <div className="text-sm bg-marigold/10 text-marigold-dark rounded-xl px-3 py-2">{message}</div>}
          <div>
            <label className="text-xs font-semibold text-ink/60 block mb-1">{t('profile.name')}</label>
            <input value={name} onChange={e => setName(e.target.value)} className="w-full border border-black/10 rounded-xl px-3 py-2.5 text-sm bg-white" />
          </div>
          <div>
            <label className="text-xs font-semibold text-ink/60 block mb-1">{t('common.location')}</label>
            <input value={location} onChange={e => setLocation(e.target.value)} className="w-full border border-black/10 rounded-xl px-3 py-2.5 text-sm bg-white" />
          </div>
          <div>
            <label className="text-xs font-semibold text-ink/60 block mb-1">{t('auth.phone')}</label>
            <input value={phone} onChange={e => setPhone(e.target.value)} className="w-full border border-black/10 rounded-xl px-3 py-2.5 text-sm bg-white" />
          </div>
          <button disabled={saving} className="inline-flex items-center gap-2 bg-forest text-paper font-semibold rounded-xl px-5 py-2.5 transition-colors disabled:opacity-60">
            <Save size={16} /> {saving ? t('profile.saving') : t('profile.saveChanges')}
          </button>
        </form>
      )}
    </div>
  )
}
