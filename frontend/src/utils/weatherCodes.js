import { Sun, CloudSun, Cloud, CloudFog, CloudDrizzle, CloudRain, CloudSnow, CloudLightning } from 'lucide-react'

// Centralized WMO weather_code -> icon mapping (per weather_service.py's
// own comment: "do not duplicate this mapping across components" -- this
// is the ONE place in the frontend that owns it). The backend never sends
// icon names, only the raw WMO code + a resolved `condition` string, so
// backend and frontend can't drift out of sync on icon choice.
export function iconForWeatherCode(code) {
  if (code === 0) return Sun
  if (code === 1) return CloudSun
  if (code === 2 || code === 3) return Cloud
  if (code === 45 || code === 48) return CloudFog
  if ([51, 53, 55, 56, 57].includes(code)) return CloudDrizzle
  if ([61, 63, 65, 66, 67, 80, 81, 82].includes(code)) return CloudRain
  if ([71, 73, 75, 77, 85, 86].includes(code)) return CloudSnow
  if ([95, 96, 99].includes(code)) return CloudLightning
  return Cloud
}
