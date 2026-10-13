import fs from 'fs';
import path from 'path';

const root = process.cwd();
const srcDir = path.join(root, 'src');
const localeDir = path.join(srcDir, 'i18n', 'translations');
const files = fs.readdirSync(localeDir).filter(f => f.endsWith('.json')).sort();
const enFile = path.join(localeDir, 'en.json');
const english = JSON.parse(fs.readFileSync(enFile, 'utf8'));
const localeCodes = files.map(f => f.replace(/\.json$/, ''));

const allowlist = new Set([
  'weather.demoDisclaimer',
  'dashboard.sourceDemo',
  'dashboard.sourceGovt',
  'market.sourceDemoData',
  'market.sourceGovernmentMandi',
  'market.sourceDistrictReference',
  'market.demoDataSummary',
  'market.mixedDataNote',
  'auth.crop.tomato',
  'auth.crop.onion',
  'auth.crop.potato',
  'auth.crop.wheat',
  'auth.crop.paddyRice',
  'auth.crop.maize',
  'auth.crop.soybean',
  'auth.crop.chanaGram',
  'auth.crop.groundnut',
  'auth.crop.mustard',
  'auth.crop.sugarcane',
  'ui.market',
]);

const issues = [];

for (const file of files) {
  const code = file.replace(/\.json$/, '');
  const data = JSON.parse(fs.readFileSync(path.join(localeDir, file), 'utf8'));
  const keys = Object.keys(data);
  const missing = Object.keys(english).filter(key => !(key in data));
  const extra = keys.filter(key => !(key in english));
  const englishCopies = Object.entries(english)
    .filter(([key, val]) => key in data && data[key] === val && code !== 'en' && !allowlist.has(key))
    .map(([key]) => key);
  const emptyValues = Object.entries(data).filter(([key, value]) => {
    if (typeof value !== 'string') return false;
    return value.trim() === '' || value === 'TODO';
  }).map(([key]) => key);
  if (missing.length) issues.push({ type: 'missing', file: code, details: missing.slice(0, 10) });
  if (extra.length) issues.push({ type: 'extra', file: code, details: extra.slice(0, 10) });
  if (englishCopies.length) issues.push({ type: 'english-copy', file: code, details: englishCopies.slice(0, 10) });
  if (emptyValues.length) issues.push({ type: 'empty', file: code, details: emptyValues.slice(0, 10) });
}

const jsFiles = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules' || entry.name === 'dist') continue;
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (/\.(jsx|js|ts|tsx)$/.test(entry.name)) jsFiles.push(full);
  }
}
walk(srcDir);

const hardcoded = [];
const ignorePatterns = [
  /\bt\(['"][^'"]+['"]\)/,
  /\bt\(\s*`[^`]*\$\{[^}]+\}[^`]*`\s*\)/,
  /className=|className:\s*|src=|href=|to=|key=|d=\"/,
  /\buseState\(|\buseMemo\(|\buseEffect\(|\bimport\s+.*from/,
  /\b(aria-label|aria-labelledby|aria-describedby|title|alt|placeholder)\s*=\s*\{/, 
];

for (const file of jsFiles) {
  const text = fs.readFileSync(file, 'utf8');
  const lines = text.split(/\r?\n/);
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (!line.trim() || line.trim().startsWith('//') || line.trim().startsWith('*')) continue;
    const matches = line.match(/(?:>\s*|\{|\(|\[\s*|\s|=)(?:['\"])([A-Za-z][^'\"]{2,})(?:['\"])/g);
    if (!matches) continue;
    const clean = line.replace(/\{[^}]*\}/g, '');
    if (ignorePatterns.some(r => r.test(clean))) continue;
    const suspicious = /(?:[A-Z][a-z]|[A-Za-z]{4,})/.test(clean) && !/(type=|value=|id=|htmlFor=|name=|role=|key=|d=)/.test(clean)
    if (suspicious) {
      hardcoded.push({ file: path.relative(root, file), line: i + 1, text: clean.trim() });
    }
  }
}

const hasIssues = issues.length > 0 || hardcoded.length > 0;
console.log('SUPPORTED_LOCALES', localeCodes.length);
console.log('LOCALE_ISSUES', issues.length);
for (const issue of issues.slice(0, 40)) {
  console.log(`${issue.type.toUpperCase()} ${issue.file} ${JSON.stringify(issue.details)}`);
}
console.log('HARDCODED_CANDIDATES', hardcoded.length);
for (const item of hardcoded.slice(0, 30)) {
  console.log(`${item.file}:${item.line}: ${item.text}`);
}

if (hasIssues) process.exit(1);
console.log('I18N_VALIDATION_PASS');
