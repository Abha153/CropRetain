import React from 'react'

// Shared location-default + browser-geolocation helper.
//
// CropRetain is a pan-India platform. This constant is only the fallback used
// when a page has no better signal (no saved profile location, no granted
// GPS permission) -- it mirrors the backend's Settings.default_demo_state
// ("Maharashtra", see backend/app/config.py) so the demo experience is
// consistent, but it is a configurable demo default, not a hardcoded
// restriction: any farmer/buyer/market anywhere in India still works once a
// real location is known.
export const DEFAULT_DEMO_LOCATION = 'Nashik'

// Precedence used everywhere a page needs a starting location:
//   1. an explicit value already chosen on this page (not this helper's job)
//   2. the signed-in user's saved profile location
//   3. the pan-India demo default above
export function resolveDefaultLocation(user) {
  return (user && user.location) || DEFAULT_DEMO_LOCATION
}

// Requests browser geolocation permission, resolves it to the nearest known
// CropRetain market via the backend (pan-India, not restricted to the demo
// region), and returns { market, state, distance_km } on success.
// Never forces permission -- the caller decides what UI to show while this
// is pending/denied, and can catch the rejection.
export function requestGeolocatedMarket(api) {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(Object.assign(new Error('Geolocation is not supported by this browser.'), { state: 'UNSUPPORTED' }))
      return
    }
    navigator.geolocation.getCurrentPosition(
      async (position) => {
        try {
          const { latitude, longitude } = position.coords
          const result = await api.nearestMarket(latitude, longitude)
          // Additive fields (existing sole caller destructures market/state/
          // distance_km only, so this changes nothing for it) -- exposes the
          // raw coordinates the browser already gave us so other features
          // (e.g. weather) can use the farmer's ACTUAL GPS position rather
          // than re-deriving it from the resolved market's coordinates.
          resolve({ ...result, latitude, longitude })
        } catch (err) {
          // The backend lookup itself failed (network/5xx), not geolocation
          // -- distinct from the browser-level PositionError codes below.
          reject(Object.assign(err, { state: 'UNAVAILABLE' }))
        }
      },
      (err) => {
        // Map the three real navigator.geolocation.PositionError codes to
        // distinct, user-facing states -- MDN: PERMISSION_DENIED=1,
        // POSITION_UNAVAILABLE=2, TIMEOUT=3. Caller falls back to
        // resolveDefaultLocation() / whatever manual location is already
        // selected in every case -- this never blocks the page, it only
        // adds the ability to tell the farmer WHY it didn't work.
        const state = err.code === 1 ? 'PERMISSION_DENIED' : err.code === 3 ? 'TIMEOUT' : 'UNAVAILABLE'
        reject(Object.assign(err, { state }))
      },
      { enableHighAccuracy: false, timeout: 8000, maximumAge: 10 * 60 * 1000 }
    )
  })
}

// Farmer-facing message KEY for each GPS outcome -- centralized so every page
// that offers "Use my location" shows the same message via the shared i18n
// system, instead of each hardcoding (and duplicating) its own English copy.
// `state` matches exactly what requestGeolocatedMarket() above attaches to
// its rejection. Callers translate the key themselves (this file isn't a
// component, so it can't call the t() hook) -- e.g. t(geo.messageKey).
export const LOCATION_STATE_MESSAGE_KEYS = {
  DETECTING: 'location.detecting',
  PERMISSION_DENIED: 'location.permissionDenied',
  TIMEOUT: 'location.timeout',
  UNAVAILABLE: 'location.unavailable',
  UNSUPPORTED: 'location.unsupported',
}

/**
 * A small reusable GPS state machine (IDLE / DETECTING / SUCCESS /
 * PERMISSION_DENIED / TIMEOUT / UNAVAILABLE / UNSUPPORTED) so every page
 * offering "Use my location" behaves identically instead of each having
 * its own bespoke try/catch. Never overwrites the caller's existing manual
 * selection on failure -- `onSuccess` is the only thing that changes
 * location state, and it's only called when GPS genuinely succeeded.
 *
 * Usage:
 *   const { state, messageKey, detect } = useGeolocatedMarket(api, (result) => setLocation(result.market))
 *   <button onClick={detect}>{state === 'DETECTING' ? t('location.detecting') : t('location.useMyLocation')}</button>
 *   {messageKey && <p>{t(messageKey)}</p>}
 */
export function useGeolocatedMarket(api, onSuccess) {
  const [state, setState] = React.useState('IDLE')
  const [result, setResult] = React.useState(null)

  const detect = React.useCallback(async () => {
    setState('DETECTING')
    try {
      const r = await requestGeolocatedMarket(api)
      setResult(r)
      setState('SUCCESS')
      onSuccess(r)
    } catch (err) {
      // Manual/previous location is left completely untouched here --
      // this only updates the message shown next to the button.
      setState(err.state || 'UNAVAILABLE')
    }
  }, [api, onSuccess])

  const reset = React.useCallback(() => setState('IDLE'), [])

  return {
    state,
    result,
    detect,
    reset,
    messageKey: LOCATION_STATE_MESSAGE_KEYS[state] || null,
    isDetecting: state === 'DETECTING',
    isFailure: ['PERMISSION_DENIED', 'TIMEOUT', 'UNAVAILABLE', 'UNSUPPORTED'].includes(state),
  }
}
