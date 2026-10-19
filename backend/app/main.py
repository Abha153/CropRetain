from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import time

from app.config import settings, logger
from app.database import Base, engine, run_lightweight_migrations
from sqlalchemy import text
from app.seed_data import seed, ensure_demo_buyer_verification_records
from app.demo_policy import auto_seed_allowed
from app.routers import (
    auth, farmers, buyers, listings, offers, market, advisor,
    forecast, matching, logistics, profit, group_selling, notifications,
    quality, assistant, admin,
)
from app.routers import lots, buyer_demands, buyer_verification
from app.routers import transactions, payments, grievances, receipts
from app.routers import storage, transport, ratings, trip_reviews
from app.routers import weather
from app.routers import offer_negotiation
from app.routers import transporters, transport_negotiation
from app.routers import trust
from app.routers import price_forecast_ml
from app.routers import past_prices
from app.routers import soil

Base.metadata.create_all(bind=engine)
run_lightweight_migrations()

app = FastAPI(
    title=settings.app_name,
    description="CropRetain API -- Smart Markets. Better Prices. Stronger Farmers.",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# i18n Phase 6 -- see app/errors.py's module docstring. Purely additive:
# only affects the new AppError type, never plain HTTPException.
from app.errors import install_error_handlers
install_error_handlers(app)


# Lightweight request-timing diagnostic: method, path (no query string --
# query params can contain user-entered location/crop text), status, and
# duration only. No headers, bodies, tokens, or user data. Cheap enough to
# leave on permanently in production, and exactly what's needed to tell
# "this specific route is slow" apart from "the whole app is slow" (e.g.
# Render cold start) from server logs alone, without a live debugger.
@app.middleware("http")
async def _timing_middleware(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    duration_ms = (time.monotonic() - start) * 1000
    logger.info(
        "request method=%s path=%s status=%d duration_ms=%.1f",
        request.method, request.url.path, response.status_code, duration_ms,
    )
    return response


def _backfill_offer_rounds():
    """Idempotent: create round 1 for any pre-negotiation BuyerOffer."""
    from app.database import SessionLocal
    from app.services.offer_negotiation import backfill_offer_rounds
    db = SessionLocal()
    try:
        n = backfill_offer_rounds(db)
        logger.info("startup: offer-round backfill created %d round(s)", n)
    except Exception:
        db.rollback()
        logger.exception("startup: offer-round backfill failed (offers are still lazily backfilled on use)")
    finally:
        db.close()


@app.on_event("startup")
def on_startup():
    t0 = time.monotonic()
    if auto_seed_allowed(settings.app_env):
        seed()
    else:
        logger.info("startup: APP_ENV=%s -- automatic demo seeding is disabled", settings.app_env)
    _backfill_offer_rounds()
    logger.info("startup: seed() completed in %.3fs", time.monotonic() - t0)
    # Trust summaries need a backing BuyerVerification record for every demo
    # buyer marked verified (see seed_data.ensure_demo_buyer_verification_records).
    # Idempotent; a failure here must never stop the API from starting.
    try:
        ensure_demo_buyer_verification_records()
    except Exception:
        logger.exception("startup: could not backfill demo buyer verification records")


@app.get("/")
def root():
    return {
        "name": "CropRetain API",
        "tagline": "Smart Markets. Better Prices. Stronger Farmers.",
        "status": "ok",
        "docs": "/docs",
    }


@app.get("/health")
def health():
    """Cheap liveness check: process is up and can talk to the DB. This is
    exactly what a cold-start-vs-slow-backend diagnostic should hit first
    (see the deployment notes) -- a slow/failing response here means the
    process itself or the DB connection is the problem, not any external
    market/weather provider (this endpoint never calls those)."""
    t0 = time.monotonic()
    db_ok = True
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {
        "status": "ok" if db_ok else "degraded",
        "db_ok": db_ok,
        "db_check_ms": round((time.monotonic() - t0) * 1000, 1),
    }


app.include_router(auth.router)
app.include_router(farmers.router)
app.include_router(buyers.router)
app.include_router(listings.router)
app.include_router(offers.router)
app.include_router(offer_negotiation.router)  # after offers.router: static /offers/* paths must win
app.include_router(market.router)
app.include_router(past_prices.router)
app.include_router(advisor.router)
app.include_router(forecast.router)
app.include_router(price_forecast_ml.router)
app.include_router(matching.router)
app.include_router(logistics.router)
app.include_router(profit.router)
app.include_router(group_selling.router)
app.include_router(notifications.router)
app.include_router(quality.router)
app.include_router(assistant.router)
app.include_router(admin.router)
app.include_router(lots.router)
app.include_router(buyer_demands.router)
app.include_router(buyer_verification.router)
app.include_router(transactions.router)
app.include_router(payments.router)
app.include_router(receipts.router)
app.include_router(grievances.router)
app.include_router(storage.router)
app.include_router(transport.router)
app.include_router(transporters.router)
app.include_router(transport_negotiation.router)
app.include_router(ratings.router)
app.include_router(trip_reviews.router)
app.include_router(trust.router)
app.include_router(weather.router)
app.include_router(soil.router)
