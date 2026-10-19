# 🌾 CropRetain

**Smart Markets. Better Prices. Stronger Farmers.**

CropRetain is a full-stack platform that helps Indian farmers decide *where*, *when* and *to whom* to sell their produce, so they keep more of the value they create. It combines live mandi prices, price forecasting, buyer matching, transport and storage coordination, and a multilingual voice-friendly assistant in one app.

Pan-India by design; the demo defaults to Maharashtra and Chhattisgarh data.

---

## Table of contents
- [Why CropRetain](#why-cropretain)
- [User journey](#user-journey)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Demo accounts](#demo-accounts)
- [Data labels and disclaimer](#data-labels-and-disclaimer)
- [Privacy](#privacy)
- [Testing](#testing)
- [ML price forecast](#ml-price-forecast)
- [Project structure](#project-structure)
- [Honest limitations](#honest-limitations)
- [Proposed business model](#proposed-business-model)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Why CropRetain
Small farmers often sell at whatever price is nearest, because comparing mandis, arranging transport, finding verified buyers and understanding forecasts is hard. CropRetain puts that information in one place, in the farmer's own language, and is explicit about where each number comes from (live government data vs. demo data).

## User journey
The farmer-to-buyer path that exists in the app today (shown with the optional demo accounts):
1. **Abha** (farmer, Bilaspur) compares mandi prices for her crop and sees the estimated net return after transport and charges.
2. She finds **Preeti**'s buyer profile and demand. A buyer is only shown as verified after the verification process; the demo buyer is **unverified**.
3. They explore the supported offer and negotiation workflow (multi-round offers with an audit trail).

Every price or estimate carries a data label (see [Data labels and disclaimer](#data-labels-and-disclaimer)).

## Features

**For farmers**
- 📈 **Market intelligence**: compare mandi prices across markets, with source attribution (data.gov.in, Agmarknet via CEDA, or demo).
- 🔮 **Price forecast**: a statistical trend model plus an optional ML 7-day forecast with an 80% uncertainty band.
- 🤖 **AI advisor and Ask Assistant**: sell/hold recommendations and a natural-language assistant (intent detection, crop and location terms).
- 🧮 **Profit calculator** and **Best Option** finder that weighs price, distance and transport cost.
- 🤝 **Offers and negotiation**: multi-round buyer offers, with a full audit trail.
- 🚚 **Transport**: request quotes, negotiate with transporters, shared-load plans (FarmPool), trip reviews.
- 🏬 **Storage**: find storage facilities and book them.
- 👥 **Group selling / FarmPool**: pool produce with other farmers for better rates.
- 📦 **Lots**, **quality grading** from an uploaded photo, **receipts**, **payments tracking**, **grievances**.
- ☁️ **Weather** cards and **arrival intelligence** for mandis.
- 🌱 **Soil Advisor**: screens Paddy, Soybean and Chana against pH, soil texture and season using cited published guidance, explains each check, and shows the estimated net return at nearby markets via the existing market-comparison logic. See [docs/SOIL_ADVISOR.md](docs/SOIL_ADVISOR.md).

**For buyers**
- Post demands, make and negotiate offers, get verified (verification badge, audit log), and view trust summaries.

**For transporters and admins**
- Transporter dashboard with quotes and workflow; admin console for impact metrics, buyer verification and login activity.

**Platform**
- 🌐 **15 UI languages**: English, Hindi, Marathi, Bengali, Tamil, Telugu, Gujarati, Kannada, Malayalam, Punjabi, Odia, Assamese, Urdu (RTL), Bhojpuri, Maithili. Speech input and text-to-speech use the device's capabilities where available.
- 🔐 Role-based access (farmer, buyer, transporter, admin) with JWT auth.
- 🧾 Honest labelling: simulated features are marked as demo throughout the API and UI.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 18, Vite 5, React Router 6, Tailwind CSS 3, Recharts, lucide-react |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2, Pydantic 2, Uvicorn |
| Database | PostgreSQL (Supabase); in-memory SQLite for tests |
| Auth | JWT (python-jose), bcrypt via passlib |
| Data sources | data.gov.in, Agmarknet via CEDA API, Open weather service |
| ML (optional) | scikit-learn `HistGradientBoostingRegressor`, pandas, joblib |
| Hosting | Vercel (frontend), Render (backend), Supabase (database) |

## Architecture

```
┌────────────────────┐   HTTPS / JSON    ┌───────────────────────────┐
│  React + Vite SPA  │ ────────────────► │  FastAPI  (app/main.py)   │
│  (Vercel)          │ ◄──────────────── │  routers → services       │
│  i18n · Tailwind   │     JWT bearer    │  (Render)                 │
└────────────────────┘                   └──────┬──────────┬─────────┘
                                                │          │
                          ┌─────────────────────┘          └──────────────────┐
                          ▼                                                   ▼
                 PostgreSQL (Supabase)                     External data (optional)
                 farmers, buyers, lots,                    data.gov.in · Agmarknet/CEDA ·
                 offers, transport, payments…              weather · ML artifacts (joblib)
```

Backend layout follows a simple pattern: `routers/` handle HTTP and auth, `services/` hold business logic (offer negotiation, transport optimisation, mandi data, trust summaries, forecasting), and `models.py` / `schemas.py` define persistence and API contracts.

## Getting started

### Prerequisites
- Python **3.12**
- Node.js **18+** and npm
- A PostgreSQL database (a free [Supabase](https://supabase.com) project works well)

### 1. Clone
```bash
git clone https://github.com/abha2008153-bot/CropRetain.git
cd CropRetain
```

### 2. Backend
```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env               # Windows: copy .env.example .env
# edit .env, set at least DATABASE_URL and SECRET_KEY (see Configuration)
uvicorn app.main:app --reload
```
The API is now at http://localhost:8000 and interactive docs at http://localhost:8000/docs. On first start the database tables are created. When `APP_ENV` is not `production` (the default for local runs) the app also seeds an empty database with shared-password demo data; **set `APP_ENV=production` on every real deployment** to disable that.

### 3. Frontend
```bash
cd frontend
npm install
cp .env.example .env               # set VITE_API_BASE_URL=http://localhost:8000
npm run dev
```
Open http://localhost:5173.

### 4. (Optional) ML forecast
```bash
cd backend
pip install -r requirements-ml.txt
python -m scripts.train_price_forecast --since 2023-01-01
```
See [ML price forecast](#ml-price-forecast).

## Configuration

All backend settings live in `backend/.env` (see `backend/.env.example`).

| Variable | Required | Description |
|---|---|---|
| `DATABASE_URL` | **Yes** | SQLAlchemy URL, e.g. `postgresql+psycopg2://user:pass@host:5432/postgres?sslmode=require` |
| `SECRET_KEY` | Yes in production | JWT signing key. If unset, a random one is generated at start-up (tokens reset on restart). |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | Yes in production | Protects `/admin/*`. A warning is logged if the demo default is used. |
| `CORS_ORIGINS` | Yes in production | Comma-separated list of allowed frontend origins. |
| `APP_ENV` | Yes in production | Set to `production` on real deployments: disables automatic demo seeding and refuses to create demo accounts. Default `development`. |
| `DEMO_ACCOUNT_PASSWORD` | Only for demo accounts | 12+ characters, read only by `python -m app.demo_accounts`. No default; never commit it. |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default `1440` (24 h). |
| `MARKET_DATA_SOURCE` | No | `demo` (default) or `live`. In live mode, failures are reported honestly instead of silently showing demo prices. |
| `DATA_GOV_IN_API_KEY` | No | Free key from [data.gov.in](https://data.gov.in). |
| `CEDA_API_KEY` | No | Enables Agmarknet data through CEDA. |
| `DEFAULT_DEMO_STATE` | No | Fallback state when none is supplied (default `Maharashtra`). |

Frontend: `VITE_API_BASE_URL` points the SPA at your backend.

> ⚠️ Never commit `.env` files. Use `.env.example` for placeholders only.

## Demo accounts
Two kinds of demo data exist. Neither represents real people, and both are marked **Demo account** in the app (any account whose e-mail ends in `.demo`).

**1. Opt-in journey accounts (recommended).** Created only when you run the command, never at startup, and refused when `APP_ENV=production`:
```bash
cd backend
DEMO_ACCOUNT_PASSWORD='choose-12-or-more-characters' python -m app.demo_accounts
# Windows PowerShell:  $env:DEMO_ACCOUNT_PASSWORD='choose-12-or-more-characters'; python -m app.demo_accounts
```
| Account | Role | Notes |
|---|---|---|
| `abha.tiwari@cropretain.demo` (Abha Tiwari) | Farmer, Bilaspur | One simulated Soybean listing |
| `preeti.tiwari@cropretain.demo` (Preeti Tiwari) | Buyer, Bilaspur | **Unverified**; one simulated demand and one simulated offer |

You choose the password; it is hashed like any other and is never stored in the repo. The command is repeatable: it adds only what is missing and never overwrites an existing account.

**2. Legacy first-run seed.** On a non-production start with an empty database, `seed_data.py` creates more sample farmers, buyers and transporters (for example `ramesh@cropwise.demo`, `freshfoods@cropwise.demo`) that share the **publicly documented** password in `backend/app/mock_data/demo_users.py`. Some of these sample buyers are seeded as verified for demonstration. Use only for local runs; set `APP_ENV=production` for any real deployment.

## Data labels and disclaimer
Prices and estimates are labelled by their actual source: **LIVE** (configured government source, fetched at request time), **DEMO** (seeded or simulated data), **ESTIMATED** (calculated by CropRetain, for example net return) and **UNAVAILABLE** (nothing is shown rather than guessing). Market pages show the price source and date where available. The in-app page *Market Information & Data Transparency* (`/disclaimer`, linked from the footer) explains this and states that estimates do not guarantee prices, profits, buyers, payments or transactions.

## Privacy
The app stores the details users give it: name or company name, e-mail, phone, location (and coordinates), crops, language, and the listings, offers, lots and transactions they create. Passwords are stored only as bcrypt hashes. Login activity (user id, role, success or failure, time) is recorded for the admin console without storing typed e-mails or passwords. Soil Advisor inputs are not stored. A plain-language summary is available in the app at `/privacy` (linked from the footer). It describes current behaviour and has **not been legally reviewed**; there is no self-service account deletion or data export yet.

## Testing
```bash
cd backend
python -m pytest -q
```
The suite (about 290 test functions, parametrised cases not counted) covers negotiation, transport quotes, buyer verification, receipts, trust summaries, mandi data normalisation, the assistant, weather and ML forecasting. It uses in-memory SQLite, so no Supabase connection is needed. CI (`.github/workflows/ci.yml`) runs the backend tests and the frontend build on every push to `main` and on pull requests; check the Actions tab for the current result. The README does not claim a passing status.

Frontend translation checks:
```bash
cd frontend
npm run i18n:validate
```

## ML price forecast
An optional 7-day modal-price forecast (INR per quintal) served at `/forecast/ml`, `/forecast/ml/status` and `/forecast/ml/compare`. The model is trained **offline** and the API only loads saved artifacts.

- Leakage-safe features (only data up to the as-of date), chronological train/validation/test split with a purge gap.
- Compared against naive baselines (persistence, 7-day mean).
- Returns `available: false` with a reason instead of guessing when history is missing or stale.

Full details: [`docs/ML_PRICE_FORECAST.md`](docs/ML_PRICE_FORECAST.md).

## Project structure
```
.
├── backend/
│   ├── app/
│   │   ├── main.py            # FastAPI app, middleware, router registration
│   │   ├── config.py          # Settings and safety warnings
│   │   ├── models.py          # SQLAlchemy models
│   │   ├── schemas.py         # Pydantic schemas
│   │   ├── routers/           # HTTP endpoints (auth, market, offers, transport, …)
│   │   ├── services/          # Business logic and data providers
│   │   ├── i18n/              # NLU, crop/location terms, translations for the assistant
│   │   └── mock_data/         # Seed/demo data
│   ├── scripts/               # ML training script
│   ├── tests/                 # pytest suite
│   └── requirements*.txt
├── frontend/
│   ├── src/
│   │   ├── pages/             # Route-level screens
│   │   ├── components/        # Reusable UI
│   │   ├── i18n/              # 15 locale files, speech and TTS helpers
│   │   ├── context/           # Auth and theme providers
│   │   └── api/client.js      # API client with timeouts
│   └── vercel.json
├── ml/                        # Dataset helpers
└── docs/                      # Design and ML notes
```

## Honest limitations
CropRetain is a hackathon-stage product, and it says so in the code. Please be aware of:

- **Payments are simulated.** No real payment gateway is integrated; every payment is labelled as demo.
- **Quality grading is heuristic.** It analyses real pixel statistics (colour, brightness, texture) but is not a trained deep-learning model.
- **Live data depends on API keys.** Without them the app runs on a seeded demo dataset, clearly labelled.
- **ML forecast needs trained artifacts** and recent price history; otherwise it reports unavailability.
- **Soil Advisor is a rule check, not soil detection.** It covers 6 of 10 catalogue crops (only those with cited sources), mostly uses guidance that is not specific to Chhattisgarh, and takes soil values the farmer enters. Soil Health Card values are classified but not matched to crops or fertiliser doses. No photo or sensor analysis. See [`docs/SOIL_ADVISOR.md`](docs/SOIL_ADVISOR.md).
- **QoS / reputation scoring is not part of the running app.** Multi-round negotiation, audit timeline, ratings and the trust-summary API are implemented (see [`docs/NEGOTIATION_QOS_STATUS.md`](docs/NEGOTIATION_QOS_STATUS.md)); the evidence-based QoS/reputation module exists only as a patch in Git history (commits `a642df5`, `b287387`) and was never committed as source.
- **Demo data is not verified data.** Seeded buyers and records are demonstrations; a seeded demo "verification" is shown as *Demo buyer (not verified)* in the buyer badge. The separate trust summary endpoint still counts a seeded demo record as verified, so do not seed demo data in production.
- **New disclaimer, privacy and demo-label text exists in English and Hindi only.** The Hindi was drafted by an AI assistant and needs native-speaker review; the other 13 languages fall back to English for these strings.

## Proposed business model
*Proposed only. Nothing below is implemented, priced or validated with users.* Possible directions to test with farmers, FPOs and buyers: a free tier for farmers; paid services for buyers (for example verified-buyer listing or analytics); and partnerships with FPOs. Which, if any, to pursue is undecided.

## Roadmap
- [ ] Real payment integration (UPI / escrow)
- [ ] Trained CNN for crop quality grading
- [ ] Database migrations with Alembic
- [ ] Offline-first PWA mode for low-connectivity villages
- [ ] SMS / WhatsApp alerts for price and offer updates
- [x] CI pipeline for tests and the frontend build (lint not included)

## Contributing
Issues and pull requests are welcome. Please open an issue first to discuss larger changes, run `pytest` before submitting, and keep translations in sync (`npm run i18n:validate`).

## License
MIT. See [LICENSE](LICENSE).


## Acknowledgements
- Government of India Open Data (data.gov.in) and Agmarknet
- CEDA, Ashoka University, for the Agmarknet API
- Supabase, Render and Vercel for hosting

---
*Made with ❤️ for India's farmers.*