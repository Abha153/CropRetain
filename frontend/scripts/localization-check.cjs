const fs = require('fs')
const path = require('path')

const root = path.resolve(__dirname, '..')
const srcRoot = path.join(root, 'src')
const translationsRoot = path.join(srcRoot, 'i18n', 'translations')
const supportedLocales = ['en', 'hi', 'mr']
const keepEnglish = new Set([
  'CropRetain',
  'AgriAdvisor',
  'AgriMarket',
  'FarmPool',
  'AI',
  'Ask AgriAdvisor',
  'Ask CropRetain',
  'Market Intelligence',
  'Best Selling Option',
  'Arrival Intelligence',
  'Profit Calculator',
  'Group Selling',
  'Password',
  'Email',
  'Phone',
  'FPO',
  'ML',
  'API',
  'B2B',
  'URL',
  'ID',
  'USD',
  'INR',
  '₹',
  'kg',
  'q',
  'm',
  'cm',
  'C',
  'F',
  'K',
])

function readJson(filePath) {
  return JSON.parse(fs.readFileSync(filePath, 'utf8'))
}

function listFiles(dir) {
  const out = []
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === 'dist') continue
      out.push(...listFiles(full))
    } else if (/\.(js|jsx)$/.test(entry.name)) {
      out.push(full)
    }
  }
  return out
}

function looksLikelyText(value) {
  if (!value || typeof value !== 'string') return false
  const s = value.trim()
  if (!s || s.length < 2) return false
  if (/^https?:\/\//i.test(s) || /^\w+[\w.]*:\s*\w/.test(s)) return false
  if (/^[A-Za-z0-9_./@-]+$/.test(s)) return false
  if (/\{\{|\$\{|\b(className|className=|import|export|const|let|var|return|if|for|switch)\b/i.test(s)) return false
  if (/^[A-Za-z]+$/.test(s) && s.length < 3) return false
  if (keepEnglish.has(s)) return false
  return /[A-Za-z]/.test(s)
}

function stripComments(code) {
  return code
    .replace(/\/\*[\s\S]*?\*\//g, ' ')
    .replace(/\/\/.*$/gm, ' ')
}

function findUserTextCandidates(filePath) {
  const code = fs.readFileSync(filePath, 'utf8')
  const withoutComments = stripComments(code)
  const hits = []

  const jsxTextRegex = />\s*([^<>]*[A-Za-z][^<>]*)\s*</g
  for (const match of withoutComments.matchAll(jsxTextRegex)) {
    const value = match[1].trim()
    if (looksLikelyText(value)) hits.push({ filePath, value, kind: 'jsxText' })
  }

  const attrRegex = /(title|placeholder|aria-label|label|helperText|caption|subtitle|description|error|emptyState)\s*:\s*["'`]([^"'`]+)["'`]|(title|placeholder|aria-label|label|helperText|caption|subtitle|description|error|emptyState)\s*=\s*["'`]([^"'`]+)["'`]/g
  for (const match of withoutComments.matchAll(attrRegex)) {
    const value = (match[2] || match[3] || '').trim()
    if (looksLikelyText(value)) hits.push({ filePath, value, kind: 'attr' })
  }

  return hits
}

function dedupeByValue(items) {
  const seen = new Set()
  const out = []
  for (const item of items) {
    const key = `${item.filePath}:${item.value}`
    if (!seen.has(key)) {
      seen.add(key)
      out.push(item)
    }
  }
  return out
}

function checkLocaleCompleteness() {
  const english = readJson(path.join(translationsRoot, 'en.json'))
  const results = []

  for (const locale of supportedLocales.filter(code => code !== 'en')) {
    const dict = readJson(path.join(translationsRoot, `${locale}.json`))
    const missing = Object.keys(english).filter(key => !(key in dict))
    const identical = Object.entries(english)
      .filter(([key, value]) => key in dict && dict[key] === value && !/^auth\.(crop|vehicleType)\./.test(key))
      .map(([key]) => key)

    results.push({ locale, missing, identical })
  }

  return results
}

const files = listFiles(srcRoot)
const candidates = dedupeByValue(files.flatMap(findUserTextCandidates))
const localeResults = checkLocaleCompleteness()

const filtered = candidates.filter(({ value }) => {
  const compact = value.replace(/\s+/g, ' ').trim()
  if (compact.length < 3) return false
  if (compact.includes('http') || compact.includes('@')) return false
  if (/^\d+(?:[.,]\d+)?\s*(?:kg|q|%)?$/.test(compact)) return false
  if (compact === 'CropRetain' || compact === 'AgriAdvisor' || compact === 'AgriMarket' || compact === 'FarmPool') return false
  return true
})

const failCounts = localeResults.map(r => ({ locale: r.locale, missing: r.missing.length, identical: r.identical.length }))
console.log('Locale completeness:')
for (const item of failCounts) {
  console.log(`- ${item.locale}: missing=${item.missing}, identical-to-English=${item.identical}`)
}

if (filtered.length) {
  console.log('\nUser-facing raw literals found:')
  for (const item of filtered) {
    const rel = path.relative(root, item.filePath).replace(/\\/g, '/')
    console.log(`- ${rel}: ${JSON.stringify(item.value)}`)
  }
  process.exitCode = 1
} else {
  console.log('\nUser-facing raw literals: none found by the current validator.')
}

const localeIssues = localeResults.some(r => r.missing.length > 0 || r.identical.length > 0)
if (localeIssues) {
  console.log('\nLocale completeness check: FAIL')
  process.exitCode = 1
} else {
  console.log('\nLocale completeness check: PASS')
}

if (process.exitCode !== 1 && filtered.length === 0 && !localeIssues) {
  console.log('\nLocalization validator: PASS')
}
