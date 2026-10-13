/**
 * Shared timestamp formatting for CropRetain.
 *
 * All important workflow events (reviews, payments, transport status
 * changes, market-data fetches) carry SERVER-generated timestamps. The
 * backend stores them as machine-readable ISO/UTC; this module is the
 * single place that turns them into the Indian-friendly display format
 * used across the UI:
 *
 *     15 Sep 2026, 3:15 PM
 *
 * Never generate a display timestamp from the browser clock for an event
 * the server owns -- if the server did not supply one, show nothing
 * rather than inventing a plausible-looking time.
 */

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']

/**
 * @param {string|Date|null|undefined} value - ISO string or Date from the server.
 * @returns {string|null} "15 Sep 2026, 3:15 PM", or null when the source
 *   provided no timestamp (callers should render nothing in that case).
 */
export function formatTimestamp(value) {
  if (!value) return null
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return null

  const day = d.getDate()
  const month = MONTHS[d.getMonth()]
  const year = d.getFullYear()

  let hours = d.getHours()
  const minutes = String(d.getMinutes()).padStart(2, '0')
  const suffix = hours >= 12 ? 'PM' : 'AM'
  hours = hours % 12
  if (hours === 0) hours = 12

  return `${day} ${month} ${year}, ${hours}:${minutes} ${suffix}`
}

/**
 * Date only, for contexts where the time of day adds no information.
 * @returns {string|null} "15 Sep 2026", or null when absent.
 */
export function formatDate(value) {
  if (!value) return null
  const d = value instanceof Date ? value : new Date(value)
  if (Number.isNaN(d.getTime())) return null
  return `${d.getDate()} ${MONTHS[d.getMonth()]} ${d.getFullYear()}`
}
