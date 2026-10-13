import React, { useEffect, useRef, useState } from 'react'
import { ArrowRight, BarChart3, Check, CheckCircle2, ChevronRight, CircleHelp, Database, MapPin, Mic, Package, RefreshCw, Sprout, Truck, Users, Volume2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useAuth } from '../context/AuthContext'
import { useI18n } from '../i18n/I18nContext'
import { getSpeechProvider, isSpeechSupportedAtAll, isVoiceInputSupportedForLanguage, VOICE_INPUT_SUPPORTED_LANGUAGES } from '../i18n/speech'
import { getTTSProvider, subscribeToVoicesChanged } from '../i18n/tts'
import { FULLY_SUPPORTED } from '../i18n/languages'
import LanguageSelector from '../components/LanguageSelector'

const EXAMPLES_BY_LANG = {
  en: ['Where should I sell my tomatoes from Bilaspur?', 'I have 20 quintals of soybean in Raipur'],
  hi: ['à¤®à¥‡à¤°à¥‡ à¤ªà¤¾à¤¸ 10 à¤•à¥à¤µà¤¿à¤‚à¤Ÿà¤² à¤§à¤¾à¤¨ à¤¹à¥ˆ à¤¬à¤¿à¤²à¤¾à¤¸à¤ªà¥à¤° à¤®à¥‡à¤‚, à¤•à¤¹à¤¾à¤ à¤¬à¥‡à¤šà¥‚à¤‚?'],
  mr: ['à¤®à¤¾à¤à¥à¤¯à¤¾à¤•à¤¡à¥‡ à¥¨à¥¦ à¤•à¥à¤µà¤¿à¤‚à¤Ÿà¤² à¤¸à¥‹à¤¯à¤¾à¤¬à¥€à¤¨ à¤†à¤¹à¥‡ à¤°à¤¾à¤¯à¤ªà¥à¤° à¤®à¤§à¥à¤¯à¥‡, à¤®à¤²à¤¾ à¤•à¥à¤ à¥‡ à¤µà¤¿à¤•à¤²à¥à¤¯à¤¾à¤¸ à¤œà¤¾à¤¸à¥à¤¤ à¤«à¤¾à¤¯à¤¦à¤¾ à¤¹à¥‹à¤ˆà¤²?'],
  bn: ['à¦†à¦®à¦¾à¦° à¦•à¦¾à¦›à§‡ à§« à¦•à§à¦‡à¦¨à§à¦Ÿà¦¾à¦² à¦ªà§‡à¦à¦¯à¦¼à¦¾à¦œ à¦†à¦›à§‡ à¦¦à§à¦°à§à¦—-à¦'],
  ta: ['à®Žà®©à®•à¯à®•à¯ à®ªà®¿à®²à®¾à®¸à¯à®ªà¯‚à®°à®¿à®²à¯ à®‡à®°à¯à®¨à¯à®¤à¯ 5 à®•à¯à®µà®¿à®£à¯à®Ÿà®²à¯ à®¤à®•à¯à®•à®¾à®³à®¿ à®µà®¿à®±à¯à®• à®µà¯‡à®£à¯à®Ÿà¯à®®à¯'],
}

function AssistantWorkspace({
  t, langInfo, languageSelector, messages, question, setQuestion, loading,
  listening, pendingTranscript, micError, speechSupported, voiceReplies,
  setVoiceReplies, startListening, stopListening, confirmTranscript,
  editTranscript, retryListening, submit, speak,
}) {
  const latest = [...messages].reverse().find(message => message.role === 'assistant' && message.meta)
  const meta = latest?.meta
  const extracted = [
    { label: t('assistant.crop'), value: meta?.crop, Icon: Sprout },
    { label: t('assistant.quantity'), value: meta?.quantity_kg ? `${Number(meta.quantity_kg).toLocaleString()} kg` : null, Icon: Package },
    { label: t('assistant.location'), value: meta?.location, Icon: MapPin },
  ]
  const marketOptions = meta?.market_options || []
  const prompts = [
    t('assistant.quickSell'), t('assistant.quickCompare'),
    t('assistant.quickEarn'), t('assistant.quickBuyers'),
  ]

  function askPrompt(prompt) {
    setQuestion(prompt)
  }

  return (
    <div className="max-w-5xl mx-auto space-y-5">
      <header className="relative overflow-hidden rounded-3xl bg-[#E6EAFB] dark:bg-forest/45 border border-forest/10 dark:border-white/10 px-6 py-7 md:px-9 md:py-8">
        <div className="absolute -right-12 -top-20 w-64 h-64 rounded-full border border-forest/10 dark:border-white/10" />
        <div className="relative flex flex-col md:flex-row md:items-center justify-between gap-5">
          <div className="flex items-start gap-4"><div className="w-14 h-14 rounded-2xl bg-white/80 dark:bg-white/10 p-1.5 shadow-card"><img src="/apple-touch-icon.png" alt="CropRetain" className="w-full h-full rounded-xl object-cover" /></div><div><div className="flex items-center gap-2 text-forest dark:text-marigold text-xs uppercase tracking-[0.18em] font-bold"><Sprout size={15} /> {t('assistant.heroEyebrow')}</div><h1 className="font-display text-3xl md:text-4xl font-bold mt-2">{t('assistant.heroTitle')}</h1><p className="text-ink/60 dark:text-paper/65 mt-2 max-w-xl">{t('assistant.heroSubtitle')}</p></div></div>
          {languageSelector}
        </div>
      </header>

      <div className="flex items-center justify-center gap-2 text-[10px] uppercase tracking-[0.15em] font-bold text-ink/45 dark:text-paper/45"><span className="flex items-center gap-1 text-forest dark:text-marigold"><CheckCircle2 size={14} /> {t('assistant.stepAsk')}</span><ArrowRight size={12} /><span className={meta ? 'text-forest dark:text-marigold' : ''}>{t('assistant.stepUnderstand')}</span><ArrowRight size={12} /><span className={marketOptions.length ? 'text-forest dark:text-marigold' : ''}>{t('assistant.stepCompare')}</span><ArrowRight size={12} /><span>{t('assistant.stepDecide')}</span></div>

      <section className="bg-white dark:bg-white/5 rounded-3xl border border-black/5 dark:border-white/10 shadow-card p-5 md:p-7">
        <div className="flex items-center justify-between gap-3 mb-4"><div><p className="text-[10px] uppercase tracking-[0.18em] text-forest/60 dark:text-paper/45 font-bold">{t('assistant.contextEyebrow')}</p><h2 className="font-display text-xl md:text-2xl font-bold mt-1">{t('assistant.contextTitle')}</h2></div><div className="text-xs text-ink/45 dark:text-paper/45 flex items-center gap-1"><Database size={13} /> {langInfo.native}</div></div>
        <form onSubmit={e => { e.preventDefault(); submit() }}>
          <div className={`relative border-2 rounded-2xl p-3 transition-colors ${listening ? 'border-marigold bg-marigold/5' : 'border-forest/15 dark:border-white/15'}`}>
            <textarea value={question} onChange={e => setQuestion(e.target.value)} rows={3} dir={langInfo.rtl ? 'rtl' : 'ltr'} placeholder={t('assistant.contextPlaceholder')} className="w-full resize-none bg-transparent outline-none text-base md:text-lg text-ink dark:text-paper placeholder:text-ink/35 dark:placeholder:text-paper/35" />
            <div className="flex flex-wrap items-center justify-between gap-3 mt-2"><div className="flex flex-wrap gap-1.5">{extracted.map(item => <span key={item.label} className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] ${item.value ? 'bg-forest/10 text-forest dark:bg-white/10 dark:text-paper' : 'bg-black/5 text-ink/40 dark:bg-white/5 dark:text-paper/40'}`}><item.Icon size={12} />{item.value || item.label}</span>)}</div><div className="flex items-center gap-2"><button type="button" onClick={listening ? stopListening : startListening} disabled={!speechSupported} className={`inline-flex items-center gap-2 rounded-xl px-3 py-2 text-xs font-semibold transition-colors ${listening ? 'bg-red-500 text-white animate-pulse' : 'bg-wheat dark:bg-white/10 text-forest dark:text-paper disabled:opacity-40'}`} title={listening ? t('listening') : t('assistant.tapToSpeak')}><Mic size={16} />{listening ? t('assistant.listening') : t('assistant.tapToSpeak')}</button><button disabled={loading || !question.trim()} className="inline-flex items-center gap-2 bg-marigold text-ink font-semibold rounded-xl px-4 py-2 text-xs disabled:opacity-50">{loading ? <RefreshCw size={14} className="animate-spin" /> : <ArrowRight size={14} />}{loading ? t('assistant.understanding') : t('assistant.askButton')}</button></div></div>
          </div>
        </form>
        {pendingTranscript && <div className="mt-3 rounded-2xl bg-wheat dark:bg-white/5 p-4"><div className="text-[10px] uppercase tracking-wide text-ink/45 dark:text-paper/45 font-bold">{t('assistant.iHeard')}</div><p className="font-medium mt-1">â€œ{pendingTranscript}â€</p><div className="flex flex-wrap gap-2 mt-3"><button onClick={confirmTranscript} className="text-xs bg-forest text-paper rounded-lg px-3 py-2 font-semibold">{t('assistant.confirm')}</button><button onClick={editTranscript} className="text-xs border border-black/10 dark:border-white/15 rounded-lg px-3 py-2">{t('assistant.edit')}</button><button onClick={retryListening} className="text-xs border border-black/10 dark:border-white/15 rounded-lg px-3 py-2">{t('assistant.speakAgain')}</button></div></div>}
        {micError && <div className="mt-3 text-xs text-amber-800 bg-amber-50 dark:bg-amber-950/30 rounded-xl px-3 py-2">{micError}</div>}
      </section>

      {!messages.length && !meta && <section className="bg-[#F1F3FB] dark:bg-white/5 rounded-3xl border border-[#E4E7F5] dark:border-white/10 p-6 text-center"><div className="w-12 h-12 rounded-full bg-forest text-paper mx-auto flex items-center justify-center"><Sprout size={22} /></div><h2 className="font-display text-xl font-bold mt-3">{t('assistant.emptyTitle')}</h2><p className="text-sm text-ink/60 dark:text-paper/60 mt-1 max-w-md mx-auto">{t('assistant.emptyDescription')}</p></section>}

      <section><div className="flex items-center gap-2 mb-3"><CircleHelp size={16} className="text-marigold-dark" /><h2 className="font-display font-semibold">{t('assistant.tryAsking')}</h2></div><div className="grid sm:grid-cols-2 gap-2">{prompts.map(prompt => <button key={prompt} onClick={() => askPrompt(prompt)} className="text-left bg-white dark:bg-white/5 border border-black/5 dark:border-white/10 rounded-xl px-4 py-3 text-sm hover:border-marigold transition-colors">{prompt}<ArrowRight size={14} className="inline ml-2 text-forest" /></button>)}</div></section>

      {meta && <section className="grid lg:grid-cols-[0.8fr_1.2fr] gap-5"><div className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 shadow-card p-5"><div className="flex items-center justify-between"><h2 className="font-display font-semibold">{t('assistant.yourRequest')}</h2><button onClick={() => setQuestion('')} className="text-xs text-forest font-semibold">{t('assistant.change')}</button></div><div className="space-y-3 mt-4">{extracted.map(item => item.value && <div key={item.label} className="flex items-center gap-3"><div className="w-8 h-8 rounded-full bg-forest/10 text-forest flex items-center justify-center"><item.Icon size={15} /></div><div><div className="text-[10px] uppercase tracking-wide text-ink/45 dark:text-paper/45">{item.label}</div><div className="font-semibold text-sm">{item.value}</div></div></div>)}</div><Link to="/market-intelligence" className="mt-5 inline-flex items-center gap-2 text-xs font-semibold text-forest">{t('assistant.compareMarkets')} <ArrowRight size={14} /></Link></div><div className="bg-forest text-paper rounded-2xl p-5"><div className="flex items-center gap-2 text-marigold text-[10px] uppercase tracking-[0.16em] font-bold"><CheckCircle2 size={14} /> {t('assistant.latestAnswer')}</div><p className="text-sm leading-relaxed mt-3">{latest?.text || t('assistant.noAnswer')}</p><div className="flex flex-wrap gap-2 mt-4"><span className="text-[11px] text-paper/65">{t('assistant.ruleBasedNotice')}</span>{latest?.meta?.quantity_assumed && <span className="text-[11px] text-marigold">{t('assistant.quantityAssumed')}</span>}</div></div></section>}

      {marketOptions.length > 0 && <section className="bg-white dark:bg-white/5 rounded-2xl border border-black/5 dark:border-white/10 shadow-card overflow-hidden"><div className="px-5 py-4 border-b border-black/5 dark:border-white/10"><p className="text-[10px] uppercase tracking-[0.16em] text-forest/60 dark:text-paper/45 font-bold">{t('assistant.marketOptionsTitle')}</p><h2 className="font-display text-xl font-bold mt-1">{t('assistant.compareAndDecide')}</h2></div><div className="divide-y divide-black/5 dark:divide-white/10">{marketOptions.map((option, index) => <div key={option.market} className={`grid grid-cols-[1fr_auto] sm:grid-cols-[1.4fr_0.8fr_0.8fr_0.9fr] gap-3 items-center px-5 py-4 ${index === 0 ? 'bg-marigold/10' : ''}`}><div><div className="font-semibold flex items-center gap-2">{index === 0 && <CheckCircle2 size={15} className="text-forest" />}{option.market}</div><div className="text-[11px] text-ink/45 dark:text-paper/45">{option.data_source === 'live' ? t('assistant.liveData') : t('assistant.demoData')}</div></div><div className="text-right sm:text-left"><div className="text-[10px] text-ink/45 dark:text-paper/45">{t('assistant.price')}</div><div className="font-mono-data text-sm">â‚¹{option.modal_price_per_kg}/kg</div></div><div className="text-right sm:text-left"><div className="text-[10px] text-ink/45 dark:text-paper/45">{t('assistant.transport')}</div><div className="font-mono-data text-sm">â‚¹{Number(option.transport_cost).toLocaleString()}</div></div><div className="col-span-2 sm:col-span-1 text-right sm:text-left"><div className="text-[10px] text-ink/45 dark:text-paper/45">{t('assistant.netRealization')}</div><div className="font-mono-data font-bold text-sm">â‚¹{Number(option.net_profit).toLocaleString()}</div></div></div>)}</div><div className="flex flex-wrap gap-2 p-5"><Link to="/market-intelligence" className="inline-flex items-center gap-2 bg-forest text-paper rounded-lg px-3 py-2 text-xs font-semibold"><BarChart3 size={14} />{t('assistant.viewMarket')}</Link><Link to="/marketplace" className="inline-flex items-center gap-2 border border-forest/20 text-forest rounded-lg px-3 py-2 text-xs font-semibold"><Users size={14} />{t('assistant.findBuyers')}</Link><button onClick={() => { setQuestion(''); }} className="inline-flex items-center gap-2 border border-black/10 dark:border-white/15 rounded-lg px-3 py-2 text-xs font-semibold"><RefreshCw size={14} />{t('assistant.askAnother')}</button></div></section>}

      {messages.length > 0 && <section className="space-y-2">{messages.slice(-4).map((message, index) => <div key={`${message.role}-${index}`} className={`rounded-2xl px-4 py-3 text-sm ${message.role === 'user' ? 'ml-auto max-w-[88%] bg-marigold/20' : message.error ? 'bg-red-50 text-red-700' : 'bg-forest text-paper max-w-[92%]'}`}><div className="text-[10px] uppercase tracking-wide opacity-60 mb-1">{message.role === 'user' ? t('assistant.you') : t('assistant.cropretain')}</div>{message.text}{message.role === 'assistant' && !message.error && <button onClick={() => speak(message.text)} className="block mt-2 text-xs text-paper/70"><Volume2 size={13} className="inline mr-1" />{t('listenBtn')}</button>}</div>)}</section>}

      <section className="flex flex-wrap items-center justify-between gap-3 text-xs text-ink/50 dark:text-paper/50 border-t border-black/5 dark:border-white/10 pt-4"><div className="flex items-center gap-2"><Volume2 size={14} />{t('assistant.voiceResponses')}<input type="checkbox" checked={voiceReplies} onChange={e => setVoiceReplies(e.target.checked)} /></div><div className="flex items-center gap-2"><CircleHelp size={14} />{t('assistant.howItWorks')}</div></section>
    </div>
  )
}

export default function AskAssistant() {
  const { user } = useAuth()
  const { code, t, languages, setLanguage } = useI18n()
  const langInfo = languages.find(l => l.code === code) || languages[0]

  const [messages, setMessages] = useState([]) // {role, text, language}
  const [question, setQuestion] = useState('')
  const [loading, setLoading] = useState(false)
  const [listening, setListening] = useState(false)
  const [micError, setMicError] = useState('')
  const [voiceReplies, setVoiceReplies] = useState(true)
  const [voicesTick, setVoicesTick] = useState(0) // bumped whenever the device's voice list changes
  // Voice recognition confirmation step: never auto-execute a recognized
  // command silently -- always show what was heard first.
  const [pendingTranscript, setPendingTranscript] = useState(null)
  const recognitionRef = useRef(null)
  const knownRef = useRef({ crop: null, quantity_kg: null, location: null })
  const scrollRef = useRef(null)

  const speechApiSupported = isSpeechSupportedAtAll()
  const voiceOfferedForLanguage = isVoiceInputSupportedForLanguage(code)
  const speechSupported = speechApiSupported && voiceOfferedForLanguage
  const nativeAI = FULLY_SUPPORTED.includes(code)

  useEffect(() => {
    // Some languages' voices register with the browser later than common
    // ones -- keep listening for changes rather than checking once, and
    // also poll a few times as a safety net for browsers that never fire
    // the `voiceschanged` event at all.
    const recompute = () => setVoicesTick(v => v + 1)
    const unsubscribe = subscribeToVoicesChanged(recompute)
    const timers = [0, 150, 500, 1200, 2500].map(ms => setTimeout(recompute, ms))
    return () => { unsubscribe(); timers.forEach(clearTimeout) }
  }, [])
  useEffect(() => { scrollRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [messages])
  useEffect(() => { setPendingTranscript(null); setMicError('') }, [code])

  const ttsProvider = getTTSProvider('browser')
  // eslint-disable-next-line no-unused-vars -- voicesTick forces this to recompute live
  const ttsAvailable = voicesTick >= 0 && ttsProvider.isAvailable(code)

  function startListening() {
    setMicError('')
    setPendingTranscript(null)
    const provider = getSpeechProvider('browser')
    const rec = provider.listen({
      languageCode: code,
      onStart: () => setListening(true),
      onEnd: () => setListening(false),
      onResult: (transcript) => {
        // Never auto-execute -- show what was heard and let the farmer
        // confirm, edit, or re-record before it's sent anywhere.
        setPendingTranscript(transcript)
      },
      onError: (err) => {
        setListening(false)
        setMicError(err.message)
      },
    })
    recognitionRef.current = rec
  }

  function stopListening() {
    recognitionRef.current?.stop?.()
    setListening(false)
  }

  function confirmTranscript() {
    const text = pendingTranscript
    setPendingTranscript(null)
    submit(text)
  }

  function editTranscript() {
    setQuestion(pendingTranscript)
    setPendingTranscript(null)
  }

  function retryListening() {
    setPendingTranscript(null)
    startListening()
  }

  async function submit(overrideText) {
    const text = (overrideText ?? question).trim()
    if (!text) return
    setQuestion('')
    setMessages(m => [...m, { role: 'user', text, language: code }])
    setLoading(true)
    try {
      const res = await api.askAssistant({
        question: text, language: code,
        known_crop: knownRef.current.crop,
        known_quantity_kg: knownRef.current.quantity_kg,
        known_location: knownRef.current.location,
      })
      knownRef.current = {
        crop: res.crop ?? knownRef.current.crop,
        quantity_kg: res.quantity_kg ?? knownRef.current.quantity_kg,
        location: res.location ?? knownRef.current.location,
      }
      setMessages(m => [...m, {
        role: 'assistant', text: res.answer, language: code,
        native: res.native_response, meta: res,
      }])
      if (voiceReplies && ttsProvider.isAvailable(code)) {
        ttsProvider.speak(res.answer, code, {})
      }
    } catch (err) {
      setMessages(m => [...m, { role: 'assistant', text: `âš ï¸ ${err.message}`, language: code, error: true }])
    } finally {
      setLoading(false)
    }
  }

  function speak(text) {
    ttsProvider.speak(text, code, {
      onError: (e) => setMicError(e.message),
    })
  }

  const examples = EXAMPLES_BY_LANG[code] || EXAMPLES_BY_LANG.en
  const voiceLangNames = VOICE_INPUT_SUPPORTED_LANGUAGES.map(c => languages.find(l => l.code === c)?.native || c).join(' & ')

  return <AssistantWorkspace
    code={code}
    t={t}
    langInfo={langInfo}
    languageSelector={<LanguageSelector compact />}
    messages={messages}
    question={question}
    setQuestion={setQuestion}
    loading={loading}
    listening={listening}
    pendingTranscript={pendingTranscript}
    micError={micError}
    speechSupported={speechSupported}
    voiceReplies={voiceReplies}
    setVoiceReplies={setVoiceReplies}
    startListening={startListening}
    stopListening={stopListening}
    confirmTranscript={confirmTranscript}
    editTranscript={editTranscript}
    retryListening={retryListening}
    submit={submit}
    speak={speak}
  />

  return (
    <div className="max-w-2xl">
      <div className="flex items-center justify-between mb-1 gap-3 flex-wrap">
        <h1 className="font-display text-3xl font-bold">{t('assistant.title')}</h1>
        <LanguageSelector compact />
      </div>
      <p className="text-ink/60 dark:text-paper/60 mb-1">{t('assistant.speakOrType', { language: langInfo.native })}</p>
      <p className="text-xs text-ink/40 dark:text-paper/40 mb-1">{t('assistant.poweredByNotice')}</p>
      <p className="text-xs text-ink/40 dark:text-paper/40 mb-4">{t('assistant.voiceSupportNotice', { languages: voiceLangNames })}</p>

      {/* Live capability status -- honest, never fake */}
      <div className="flex flex-wrap gap-2 mb-2">
        <span className={`text-xs px-2.5 py-1 rounded-full border ${nativeAI ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-900' : 'bg-amber-50 dark:bg-amber-950/40 text-amber-700 border-amber-200 dark:border-amber-900'}`}>
          ðŸ§  {t('assistant.aiUnderstanding')}: {nativeAI ? t('assistant.nativeLanguage', { language: langInfo.native }) : t('assistant.englishFallback')}
        </span>
        <span className={`text-xs px-2.5 py-1 rounded-full border ${speechSupported ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-900' : 'bg-stone-100 dark:bg-white/10 text-stone-500 dark:text-stone-400 border-stone-200 dark:border-white/10'}`}>
          ðŸŽ¤ {t('assistant.voiceInput')}: {!speechApiSupported ? t('assistant.notSupportedBrowser') : voiceOfferedForLanguage ? t('assistant.availableDeviceDependent') : t('assistant.notOfferedFor', { language: langInfo.native })}
        </span>
        <span className={`text-xs px-2.5 py-1 rounded-full border ${ttsAvailable ? 'bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-200 dark:border-emerald-900' : 'bg-stone-100 dark:bg-white/10 text-stone-500 dark:text-stone-400 border-stone-200 dark:border-white/10'}`}>
          ðŸ”Š {t('assistant.voiceOutput')}: {ttsAvailable ? t('assistant.availableOnDevice') : t('assistant.noVoiceInstalled')}
        </span>
      </div>
      {speechApiSupported && !voiceOfferedForLanguage && (
        <div className="bg-sky-50 dark:bg-sky-950/40 border border-sky-200 dark:border-sky-900 text-sky-800 dark:text-sky-300 text-xs rounded-lg px-3 py-2 mb-3 flex items-center justify-between gap-2 flex-wrap">
          <span>{t('assistant.voiceInputLimitedNotice', { languages: voiceLangNames, language: langInfo.native })}</span>
          <button onClick={() => setLanguage('en')} className="shrink-0 text-xs font-semibold bg-sky-600 text-white rounded-full px-3 py-1">{t('assistant.switchToEnglish')}</button>
        </div>
      )}
      {!ttsAvailable && (
        <p className="text-xs text-ink/40 dark:text-paper/40 mb-4">
          {t('assistant.noTtsVoiceNotice', { language: langInfo.native })}
        </p>
      )}

      <div className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-4 mb-4 h-96 overflow-y-auto flex flex-col gap-3">
        {messages.length === 0 && !pendingTranscript && (
          <div className="text-sm text-ink/40 dark:text-paper/40 m-auto text-center px-6">
            {t('speakNow')}
            <div className="flex flex-wrap gap-2 justify-center mt-3">
              {examples.map(ex => (
                <button key={ex} onClick={() => { setQuestion(ex); submit(ex) }} className="text-xs bg-wheat dark:bg-white/5 hover:bg-marigold/20 rounded-full px-3 py-1.5 transition-colors">
                  {ex}
                </button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`max-w-[85%] rounded-2xl px-4 py-2.5 text-sm ${m.role === 'user' ? 'self-end bg-marigold/20 text-ink dark:text-paper' : m.error ? 'self-start bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300' : 'self-start bg-forest text-paper'}`}>
            <p>{m.text}</p>
            {m.role === 'assistant' && !m.error && (
              <div className="flex items-center gap-2 mt-2">
                <button onClick={() => speak(m.text)} className="text-xs bg-white/15 hover:bg-white/25 rounded-full px-2.5 py-1 transition-colors" aria-label={`${t('listenBtn')}: ${m.text}`}>
                  ðŸ”Š {t('listenBtn')}
                </button>
                {m.meta?.clarification_needed && (
                  <span className="text-xs text-paper/60">{t('assistant.waitingFor', { field: m.meta.clarification_needed })}</span>
                )}
                {!m.native && <span className="text-xs text-paper/60">({t('assistant.englishFallback')})</span>}
              </div>
            )}
          </div>
        ))}
        {loading && <div className="self-start text-xs text-ink/40 dark:text-paper/40">â€¦</div>}

        {/* Recognized-speech confirmation -- never auto-execute a voice command */}
        {pendingTranscript && (
          <div className="self-center w-full max-w-sm bg-wheat dark:bg-white/5 rounded-2xl p-4 text-center">
            <div className="text-xs text-ink/50 dark:text-paper/50 mb-1">{t('assistant.iHeard')}</div>
            <p className="font-medium mb-3">"{pendingTranscript}"</p>
            <div className="flex flex-wrap gap-2 justify-center">
              <button onClick={confirmTranscript} className="text-xs bg-forest text-paper font-semibold rounded-full px-3 py-1.5">{t('assistant.confirm')}</button>
              <button onClick={editTranscript} className="text-xs bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 font-semibold rounded-full px-3 py-1.5">{t('assistant.edit')}</button>
              <button onClick={retryListening} className="text-xs bg-white dark:bg-white/5 border border-black/10 dark:border-white/15 font-semibold rounded-full px-3 py-1.5">{t('assistant.speakAgain')}</button>
            </div>
          </div>
        )}
        <div ref={scrollRef} />
      </div>

      {micError && (
        <div className="bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-900 text-amber-800 dark:text-amber-300 text-sm rounded-lg px-3 py-2 mb-3 flex items-center justify-between gap-2">
          <span>{micError}</span>
          <button onClick={() => setMicError('')} className="text-xs underline shrink-0">{t('assistant.dismiss')}</button>
        </div>
      )}

      <form onSubmit={(e) => { e.preventDefault(); submit() }} className="bg-white dark:bg-white/5 rounded-2xl shadow-card border border-black/5 dark:border-white/10 p-3">
        <div className="flex items-center gap-2">
          <input
            value={question}
            onChange={e => setQuestion(e.target.value)}
            placeholder={t('askPlaceholder')}
            className="flex-1 border border-black/10 dark:border-white/15 rounded-lg px-3 py-3 text-sm bg-white dark:bg-white/5 dark:text-paper"
            dir={langInfo.rtl ? 'rtl' : 'ltr'}
          />
          {speechSupported && (
            <button
              type="button"
              onClick={listening ? stopListening : startListening}
              className={`w-11 h-11 rounded-lg flex items-center justify-center text-lg transition-colors shrink-0 ${listening ? 'bg-red-500 text-white animate-pulse' : 'bg-wheat dark:bg-white/5 hover:bg-marigold/20'}`}
              title={listening ? t('listening') : t('speakNow')}
              aria-label={listening ? t('listening') : t('speakNow')}
              aria-pressed={listening}
            >
              ðŸŽ¤
            </button>
          )}
          <button disabled={loading} className="bg-marigold hover:bg-marigold-dark text-ink dark:text-paper font-semibold rounded-lg px-5 py-3 transition-colors disabled:opacity-60 shrink-0">
            {loading ? '...' : t('askButton')}
          </button>
        </div>
        <label className="flex items-center gap-2 mt-2 text-xs text-ink/50 dark:text-paper/50">
          <input type="checkbox" checked={voiceReplies} onChange={e => setVoiceReplies(e.target.checked)} />
          {t('assistant.autoSpeakReplies')}
        </label>
        {!speechApiSupported && <p className="text-xs text-ink/40 dark:text-paper/40 mt-1">{t('voiceNotAvailable')}</p>}
      </form>
    </div>
  )
}
