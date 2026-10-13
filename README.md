# 🌾 CropRetain

**Smart Markets. Better Prices. Stronger Farmers.**

CropRetain is a full-stack platform that helps Indian farmers decide *where*, *when* and *to whom* to sell their produce, so they keep more of the value they create. It combines live mandi prices, price forecasting, buyer matching, transport and storage coordination, and a multilingual voice-friendly assistant in one app.

Pan-India by design; the demo defaults to Maharashtra and Chhattisgarh data.

---

## Table of contents
- [Why CropRetain](#why-cropretain)
- [Features](#features)
- [Tech stack](#tech-stack)
- [Architecture](#architecture)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Demo accounts](#demo-accounts)
- [Testing](#testing)
- [ML price forecast](#ml-price-forecast)
- [Project structure](#project-structure)
- [Honest limitations](#honest-limitations)
- [Roadmap](#roadmap)
- [Contributing](#contributing)
- [License](#license)

---

## Why CropRetain
Small farmers often sell at whatever price is nearest, because comparing mandis, arranging transport, finding verified buyers and understanding forecasts is hard. CropRetain puts that information in one place, in the farmer's own language, and is explicit about where each number comes from (live government data vs. demo data).

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
git clone https://github.com/<your-username>/<your-repo>.git
cd <your-repo>
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
The API is now at http://localhost:8000 and interactive docs at http://localhost:8000/docs. On first start the database tables are created and demo data is seeded automatically.

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
| `ACCESS_TOKEN_EXPIRE_MINUTES` | No | Default `1440` (24 h). |
| `MARKET_DATA_SOURCE` | No | `demo` (default) or `live`. In live mode, failures are reported honestly instead of silently showing demo prices. |
| `DATA_GOV_IN_API_KEY` | No | Free key from [data.gov.in](https://data.gov.in). |
| `CEDA_API_KEY` | No | Enables Agmarknet data through CEDA. |
| `DEFAULT_DEMO_STATE` | No | Fallback state when none is supplied (default `Maharashtra`). |

Frontend: `VITE_API_BASE_URL` points the SPA at your backend.

> ⚠️ Never commit `.env` files. Use `.env.example` for placeholders only.

## Demo accounts
Seed data includes sample farmers, buyers and transporters (for example `ramesh@cropwise.demo`, `freshfoods@cropwise.demo`). All demo accounts share one demo password, which is defined in `backend/app/mock_data/demo_users.py`. These accounts exist only for local and demo use; disable or change seeding in any real deployment.

## Testing
```bash
cd backend
python -m pytest -q
```
The suite (260+ tests) covers negotiation, transport quotes, buyer verification, receipts, trust summaries, mandi data normalisation, the assistant, weather and ML forecasting. It uses in-memory SQLite, so no Supabase connection is needed.

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

## Roadmap
- [ ] Real payment integration (UPI / escrow)
- [ ] Trained CNN for crop quality grading
- [ ] Database migrations with Alembic
- [ ] Offline-first PWA mode for low-connectivity villages
- [ ] SMS / WhatsApp alerts for price and offer updates
- [ ] CI pipeline (tests + lint on every PR)

## Contributing
Issues and pull requests are welcome. Please open an issue first to discuss larger changes, run `pytest` before submitting, and keep translations in sync (`npm run i18n:validate`).

## License


## Acknowledgements
- Government of India Open Data (data.gov.in) and Agmarknet
- CEDA, Ashoka University, for the Agmarknet API
- Supabase, Render and Vercel for hosting

---
*Made with ❤️ for India's farmers.*