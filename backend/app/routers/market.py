import datetime as dt
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.mock_data.crops import CROPS, CROP_BY_NAME
from app.mock_data.locations import MARKETS, distance_between, nearest_market_to_coordinates, haversine_km
from app.services.transport_optimizer import net_profit_breakdown
from app.services import live_market_data, mandi_directory, agmarknet_service, mandi_sync
from app.auth_utils import require_admin
from app.config import logger, settings

router = APIRouter(prefix="/market", tags=["market"])


@router.get("/crops")
def get_crops():
    return CROPS


@router.get("/markets")
def get_markets():
    return MARKETS


@router.get("/nearest-market")
def nearest_market(latitude: float, longitude: float):
    """Resolve raw GPS coordinates (from the browser's geolocation API) to
    the nearest known CropRetain market, pan-India. This is what lets granted
    location permission genuinely override the configurable demo default
    (Settings.default_demo_state) instead of the frontend staying pinned to
    the demo region's town regardless of where the user actually is."""
    match = nearest_market_to_coordinates(latitude, longitude)
    if not match:
        raise HTTPException(status_code=404, detail="No known markets configured")
    return {
        "market": match["name"],
        "state": match["state"],
        "latitude": match["latitude"],
        "longitude": match["longitude"],
        "distance_km": round(haversine_km(latitude, longitude, match["latitude"], match["longitude"]), 1),
    }


@router.get("/live-markets")
def live_markets(state: str = settings.default_demo_state):
    """
    Official mandi/market names the live government dataset actually has
    for this state right now (discovery, not CropRetain's internal town
    list) -- see app/services/mandi_directory.py. Empty list simply means
    live data isn't configured or the discovery call didn't return
    anything (never raises).
    """
    names = mandi_directory.discover_state_markets(state)
    return {
        "state": state,
        "live_data_configured": live_market_data.is_configured(),
        "official_market_names": names,
        "note": (
            "Discovered directly from data.gov.in (Agmarknet), not CropRetain's "
            "internal town list. Empty when live data isn't configured, or "
            "the discovery request didn't succeed."
        ),
    }


@router.get("/sync-status")
def sync_status(db: Session = Depends(get_db)):
    """Provider-level freshness: when the last SUCCESSFUL official-data
    sync completed, and whether the most recent attempt failed.

    Distinct from any individual price's own timestamps -- a price row
    carries `observed_at` (when the source says it was observed) and
    `fetched_at` (when CropRetain obtained it); this endpoint answers the
    separate question "how current is our picture of this provider overall".
    """
    return mandi_sync.freshness(db)


@router.post("/sync")
def trigger_sync(
    state: str = Query(mandi_sync.DEFAULT_SYNC_STATE),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """Admin-only: run an official-data sync for one state.

    Government-sourced DAILY mandi prices -- the newest record available
    may legitimately be from a previous day. Never describe this as
    real-time. Returns an honest status ("ok" / "no_records" /
    "not_configured" / "error") rather than failing the request when the
    provider is unreachable.
    """
    return mandi_sync.sync_state(db, state=state)


@router.get("/data-source-status")
def data_source_status():
    """Lets the frontend show an accurate 🟢 Live / 🟡 Demo badge without
    guessing -- reflects the actual configured/available data source(s)."""
    both_configured = live_market_data.is_configured() and agmarknet_service.is_configured()
    return {
        "live_data_configured": (
            live_market_data.is_configured() or agmarknet_service.is_configured()
        ),
        "provider": (
            "data.gov.in + Agmarknet" if both_configured else
            "Agmarknet" if agmarknet_service.is_configured() else
            "data.gov.in" if live_market_data.is_configured() else None
        ),
        "providers": {
            "data.gov.in": {
                "configured": live_market_data.is_configured(),
                "available": live_market_data.is_configured(),
            },
            "agmarknet": agmarknet_service.status(),
        },
        "fallback": "Demo/seeded mandi-style dataset",
        "note": (
            "CropRetain queries data.gov.in and Agmarknet CONCURRENTLY (not "
            "one as a fallback for the other) whenever both are "
            "configured, combines their results with source attribution, "
            "and transparently falls back to the seeded dataset (labeled "
            "per-record) only when neither live source has usable data."
        ),
    }


def _latest_price_row(db: Session, crop: str, market: str):
    return (
        db.query(models.MarketPrice)
        .filter(models.MarketPrice.crop == crop, models.MarketPrice.market == market)
        .order_by(models.MarketPrice.date.desc())
        .first()
    )


def _record_live_snapshot(db: Session, crop: str, local_market: str, live: dict) -> None:
    """
    Persist a genuine live fetch result as a real MarketPrice row
    (data_source="live") so honest historical trend data actually
    accumulates over time. Upserts on (crop, market, date) so re-fetching
    the same day's data (e.g. from the 10-minute cache expiring and being
    re-hit) doesn't create duplicate rows. Never raises -- a persistence
    hiccup should never break the price-lookup request that triggered it.
    """
    date_str = live.get("date") or dt.date.today().isoformat()
    sources = live.get("sources") or ([live["source"]] if live.get("source") else [])
    source_label = "+".join(sources) if sources else None
    source_timestamp = live.get("fetched_at")
    try:
        existing = (
            db.query(models.MarketPrice)
            .filter(
                models.MarketPrice.crop == crop,
                models.MarketPrice.market == local_market,
                models.MarketPrice.date == date_str,
                models.MarketPrice.data_source == "live",
            )
            .first()
        )
        if existing:
            existing.min_price = live["min_price"]
            existing.max_price = live["max_price"]
            existing.modal_price = live["modal_price"]
            existing.source = source_label
            existing.source_timestamp = source_timestamp
        else:
            db.add(models.MarketPrice(
                crop=crop, market=local_market, date=date_str,
                min_price=live["min_price"], max_price=live["max_price"],
                modal_price=live["modal_price"],
                # This data.gov.in resource does not provide arrival
                # volume -- store None ("not available"), never 0.0.
                # A fabricated 0 would be indistinguishable from a
                # genuine zero-arrivals day and would silently corrupt
                # arrival_intelligence()'s trend/demand-signal math once
                # live rows are mixed with demo history (see that
                # endpoint for how None is now excluded from averages).
                arrivals_tonnes=None,
                data_source="live",
                source=source_label,
                source_timestamp=source_timestamp,
            ))
        db.commit()
    except Exception as e:
        # Deliberately broad: this wraps a best-effort DB persist of a live
        # snapshot. A persistence hiccup here must never break the price
        # lookup request that triggered it -- but log it (not silent) so a
        # real, recurring failure is still visible in server logs.
        db.rollback()
        logger.debug("_record_live_snapshot failed for %s/%s: %s", crop, local_market, e)


def _fetch_price_outcome(crop: str, market: str) -> dict:
    """
    The network-bound half of `_get_price` -- talks to
    `mandi_directory.fetch_price_result` only, touches no database session.
    Deliberately separated out so it can be run concurrently across many
    markets (see `compare_markets`) without ever sharing a SQLAlchemy
    Session across threads: each worker thread calls only this function,
    and every DB read/write happens back on the caller's own thread via
    `_resolve_price` below.
    """
    return mandi_directory.fetch_price_result(
        crop, market, state=mandi_directory.state_for_market(market),
    )


def _resolve_price(db: Session, crop: str, market: str, outcome: dict) -> dict:
    """DB-only half of `_get_price`: turns a `_fetch_price_outcome` result
    into the final response dict, persisting a live snapshot or reading the
    demo fallback row as needed. Safe to call repeatedly on the same
    request-scoped `db` Session from a single thread -- never call this
    from more than one thread against the same Session."""
    if outcome["status"] == "ok":
        live = outcome["data"]
        is_market_level = live.get("source_resource") == "market"
        if is_market_level:
            _record_live_snapshot(db, crop, market, live)
        sources = live.get("sources") or ([live["source"]] if live.get("source") else [])
        return {
            "status": "ok", "data_source": "live",
            "provider": " + ".join(sources) if sources else live.get("provider", "data.gov.in / Agmarknet"),
            "sources": sources,  # e.g. ["agmarknet"], ["data.gov.in"], or ["agmarknet", "data.gov.in"]
            "source_conflict": live.get("source_conflict", False),
            "source_values": live.get("source_values"),  # per-source detail, always present when sources has 2+ entries
            "modal_price": live["modal_price"], "min_price": live["min_price"],
            "max_price": live["max_price"], "date": live.get("date") or "",
            "arrivals_tonnes": live.get("arrival"),
            "matched_market_name": live.get("matched_market_name", market),
            "district": mandi_directory.LOCAL_MARKET_TO_DISTRICT.get(market, market),
            "variety": live.get("variety") if is_market_level else None,
            "grade": live.get("grade") if is_market_level else None,
            "varieties": live.get("varieties") if not is_market_level else None,
            "fetched_at": live.get("fetched_at"),
            "source_resource": live.get("source_resource"),
            "district_reference_note": live.get("district_reference_note"),
            "message": None,
        }

    # PRODUCT DECISION (explicitly requested by the project owner, superseding
    # the previous stricter behaviour): live data is still always preferred
    # and always tried first above, but the dashboard must never go blank or
    # show a dead end. Every non-"ok" outcome -- a confirmed "no record for
    # this exact selection", a live request that errored/timed out, or live
    # mode simply not being configured -- now falls through to the same
    # seeded demo dataset below, rather than stopping short. The *reason* for
    # the fallback is still preserved in `status`/`message` for transparency
    # and logging; only the "give up and show nothing" behaviour is removed.
    demo_row = _latest_price_row(db, crop, market)
    if not demo_row:
        # Genuine last resort: this exact crop/market combination has no
        # live record AND nothing seeded for it either. Still not "hide the
        # page" -- callers (compare_markets) treat this market as simply not
        # contributing an option, and try further markets instead.
        return {
            "status": "unavailable", "data_source": None,
            "message": "No live or demo data available for this selection.",
        }

    reason_message = {
        "no_records": "🟡 Demo Data — no official government record for this exact selection.",
        "error": "🟡 Demo Data — government market API could not be reached (timeout or request failure).",
        "not_configured": "🟡 Demo Data",
    }.get(outcome["status"], "🟡 Demo Data")
    logger.info("Using demo data (reason=%s) for %s/%s", outcome["status"], crop, market)
    return {
        "status": "demo_fallback", "data_source": "demo",
        # Preserved purely for audit/debugging -- never shown to users as a
        # separate concept from the "demo" badge itself.
        "fallback_reason": outcome["status"],
        "provider": "DEMO",
        "modal_price": demo_row.modal_price, "min_price": demo_row.min_price,
        "max_price": demo_row.max_price, "date": demo_row.date,
        "arrivals_tonnes": demo_row.arrivals_tonnes,
        "matched_market_name": market,
        "district": mandi_directory.LOCAL_MARKET_TO_DISTRICT.get(market, market),
        "variety": None, "grade": None, "varieties": None,
        "fetched_at": None, "source_resource": None, "district_reference_note": None,
        "message": reason_message,
    }


def _get_price(db: Session, crop: str, market: str) -> dict:
    """
    Real price lookup -- see `_fetch_price_outcome` (network) and
    `_resolve_price` (DB) for the two halves this combines. Four distinct,
    honestly-reported outcomes (see mandi_directory.fetch_price_result for
    the full status contract): status="ok" (live), "no_records" (no demo
    fallback -- a confirmed absence, not an error), "error" (falls back to
    demo), "not_configured" (falls back to demo, not framed as a failure).
    Always returns a dict (never None).

    Kept as a single function for every caller except `compare_markets`,
    which needs the two halves split to fetch several markets' network
    calls concurrently while keeping all DB access on one thread (see
    there for why).
    """
    outcome = _fetch_price_outcome(crop, market)
    return _resolve_price(db, crop, market, outcome)



def _history_rows(db: Session, crop: str, market: str, days: Optional[int] = None,
                   data_source: Optional[str] = None):
    q = (
        db.query(models.MarketPrice)
        .filter(models.MarketPrice.crop == crop, models.MarketPrice.market == market)
    )
    if data_source:
        q = q.filter(models.MarketPrice.data_source == data_source)
    rows = q.order_by(models.MarketPrice.date.asc()).all()
    if days:
        rows = rows[-days:]
    return rows


UNAVAILABLE_MESSAGE = "Historical mandi data is currently unavailable."


@router.get("/prices")
def get_prices(crop: str, market: str, days: int = 30, include_demo: bool = False,
                db: Session = Depends(get_db)):
    """
    Historical price series for a crop/market.

    HONESTY: by default this returns ONLY genuine data points -- rows with
    data_source="live", i.e. real snapshots CropRetain itself captured from
    data.gov.in over time (see `_record_live_snapshot`). It does NOT
    return the synthesized 60-day demo series here, because that series is
    not real historical data and must never be presented as a real price
    trend. If there isn't enough genuine history yet, `available` is
    false and `message` explains why -- the frontend should show that
    message instead of drawing a chart.

    Pass `include_demo=true` to explicitly opt into the clearly-labeled
    synthetic demo series instead (e.g. for a hackathon walkthrough) --
    every row it returns is still tagged `data_source: "demo"` so it can
    never be mistaken for real data downstream.
    """
    if crop not in CROP_BY_NAME:
        raise HTTPException(status_code=404, detail="Unknown crop")

    rows = _history_rows(db, crop, market, days, data_source="live")
    if rows:
        return {
            "crop": crop, "market": market, "available": True,
            "data_source": "live", "is_demo": False, "message": None,
            "rows": [
                {"date": r.date, "min_price": r.min_price, "max_price": r.max_price,
                 "modal_price": r.modal_price, "arrivals_tonnes": r.arrivals_tonnes,
                 "data_source": r.data_source}
                for r in rows
            ],
        }

    if include_demo:
        demo_rows = _history_rows(db, crop, market, days, data_source="demo")
        return {
            "crop": crop, "market": market, "available": bool(demo_rows),
            "data_source": "demo" if demo_rows else None, "is_demo": True,
            "message": (None if demo_rows else UNAVAILABLE_MESSAGE),
            "demo_disclaimer": (
                "Simulated for demonstration only -- not real government "
                "mandi data. Requested explicitly via include_demo=true."
            ) if demo_rows else None,
            "rows": [
                {"date": r.date, "min_price": r.min_price, "max_price": r.max_price,
                 "modal_price": r.modal_price, "arrivals_tonnes": r.arrivals_tonnes,
                 "data_source": r.data_source}
                for r in demo_rows
            ],
        }

    return {
        "crop": crop, "market": market, "available": False,
        "data_source": None, "is_demo": False, "message": UNAVAILABLE_MESSAGE,
        "rows": [],
    }


@router.get("/compare")
def compare_markets(
    crop: str = Query(...), quantity_kg: float = Query(...), location: str = Query(...),
    top_n: int = Query(6, ge=1, le=30), db: Session = Depends(get_db),
):
    """Thin FastAPI wrapper -- all logic lives in `_compare_markets_core` so
    non-HTTP callers (admin.py's impact dashboard) can pass a shared
    `outcome_cache` across many calls in the same request without touching
    this endpoint's public query-parameter contract."""
    return _compare_markets_core(crop, quantity_kg, location, top_n, db)


def _compare_markets_core(
    crop: str, quantity_kg: float, location: str, top_n: int = 6,
    db: Session = None, outcome_cache: Optional[dict] = None,
):
    # compare_markets is called two ways: as an HTTP endpoint (where
    # FastAPI resolves the Query(...) defaults above into real values
    # before this body runs) AND directly as a plain Python function by
    # advisor.py and admin.py, which omit top_n and rely on its default.
    # A direct call never goes through FastAPI's request-parsing layer, so
    # it would receive the raw Query(...) marker object itself instead of
    # 6 -- which crashed every such call with "slice indices must be
    # integers" the moment top_n gained bounds validation. Coerce defensively
    # so both call styles work.
    if not isinstance(top_n, int):
        top_n = 6
    top_n = max(1, min(top_n, 30))

    if crop not in CROP_BY_NAME:
        raise HTTPException(status_code=404, detail="Unknown crop")
    if quantity_kg <= 0:
        raise HTTPException(status_code=400, detail="quantity_kg must be positive")

    all_markets_by_distance = sorted(MARKETS, key=lambda m: distance_between(location, m["name"]))
    candidate_markets = all_markets_by_distance[:top_n]

    # Markets where NEITHER live NOR demo data exists at all -- the one
    # genuine "nothing to show" case left after the fallback below. Kept
    # for transparency (surfaced as `unavailable_markets`), never silently
    # dropped without explanation.
    unavailable_markets = []
    timing = {"network_calls": 0, "cache_hits": 0, "network_seconds": 0.0}

    def _build_option(m, latest):
        """Turn a resolved `_resolve_price` result into an `options` row,
        or None if truly nothing (live or demo) exists for this market."""
        if latest.get("data_source") is None:
            unavailable_markets.append({"market": m["name"], "message": latest["message"]})
            return None
        price_per_kg = round(latest["modal_price"] / 100.0, 2)
        distance = distance_between(location, m["name"])
        breakdown = net_profit_breakdown(quantity_kg, price_per_kg, distance)
        return {
            "market": m["name"],
            "distance_km": distance,
            "modal_price_per_kg": price_per_kg,
            "min_price_per_kg": round(latest["min_price"] / 100.0, 2),
            "max_price_per_kg": round(latest["max_price"] / 100.0, 2),
            "arrivals_tonnes": latest["arrivals_tonnes"],
            "as_of_date": latest["date"],
            # When CropRetain actually retrieved this record from the source.
            # Distinct from `as_of_date`, which is when the SOURCE says the
            # price was observed. Null for demo rows (nothing was fetched),
            # which is why the UI must omit it rather than substitute a time.
            "fetched_at": latest.get("fetched_at"),
            "data_source": latest["data_source"],  # "live" | "demo" -- per-market, never blended silently
            "source_resource": latest.get("source_resource"),  # "market" | "district_variety" | None
            "matched_market_name": latest.get("matched_market_name", m["name"]),
            "district_reference_note": latest.get("district_reference_note"),
            "fallback_reason": latest.get("fallback_reason"),  # None when data_source == "live"
            **breakdown,
            "net_profit_is_estimated": True,
        }

    # The network half (`_fetch_price_outcome`) is I/O-bound (each call may
    # hit data.gov.in and/or CEDA over the network, each with its own
    # several-second timeout) and independent per market -- there is no
    # reason to pay top_n x single-market-latency sequentially. Fetching
    # every candidate market's outcome concurrently is what turns a worst
    # case of (markets x per-market network time) into roughly one single
    # market's worth of wall-clock time. This was previously a plain `for`
    # loop and was the dominant cause of multi-minute compare_markets()/
    # Best Selling Option loads whenever live data was configured but
    # slow/unreachable.
    #
    # Only `_fetch_price_outcome` (pure network, no DB) runs inside the
    # thread pool. The DB half (`_resolve_price` -- persisting a live
    # snapshot, reading the demo fallback row) always runs afterwards, back
    # on this request's own thread, against the single shared `db` Session
    # -- SQLAlchemy Sessions are not safe to use from multiple threads at
    # once, so DB access is deliberately kept single-threaded rather than
    # opening one session per worker.
    #
    # `outcome_cache`, when supplied by the caller (admin.py's impact
    # dashboard is the only current user), is a plain dict shared across
    # MANY compare_markets calls in the same outer request -- keyed on
    # (crop, market name), since that's exactly what `_fetch_price_outcome`
    # itself is keyed on. This is deliberately separate from the TTL caches
    # already inside live_market_data.py/district_market_data.py/
    # agmarknet_service.py (those are safe to share, but only within their
    # own process-lifetime cache); this dict instead guarantees each
    # distinct (crop, market) pair is fetched over the network AT MOST
    # ONCE per admin request, even across 50 listings, without waiting on
    # any TTL. It is never used for a single normal compare_markets() call
    # (outcome_cache=None there), so the one-request, one-market-set
    # behaviour every other caller relies on is unchanged.
    def _fetch_outcomes(markets_to_try):
        outcomes = {}
        to_fetch = []
        for m in markets_to_try:
            key = (crop, m["name"])
            if outcome_cache is not None and key in outcome_cache:
                outcomes[m["name"]] = outcome_cache[key]
                timing["cache_hits"] += 1
            else:
                to_fetch.append(m)
        if to_fetch:
            t0 = time.monotonic()
            with ThreadPoolExecutor(max_workers=min(len(to_fetch), 12)) as pool:
                future_to_market = {
                    pool.submit(_fetch_price_outcome, crop, m["name"]): m for m in to_fetch
                }
                for future in as_completed(future_to_market):
                    m = future_to_market[future]
                    result = future.result()
                    outcomes[m["name"]] = result
                    if outcome_cache is not None:
                        outcome_cache[(crop, m["name"])] = result
            timing["network_seconds"] += time.monotonic() - t0
            timing["network_calls"] += len(to_fetch)
        return outcomes

    options = []
    considered_names = {m["name"] for m in candidate_markets}
    outcomes = _fetch_outcomes(candidate_markets)
    for m in candidate_markets:
        latest = _resolve_price(db, crop, m["name"], outcomes[m["name"]])
        row = _build_option(m, latest)
        if row:
            options.append(row)

    # Guarantee at least 3 markets to compare whenever the platform knows
    # about 3+ markets at all -- live data is still preferred per market,
    # this only reaches further down the distance-sorted list (never
    # fabricates a market that isn't in MARKETS) when the initial top_n
    # candidates came up short.
    MIN_OPTIONS = 3
    if len(options) < MIN_OPTIONS:
        remaining = [
            m for m in all_markets_by_distance
            if m["name"] not in considered_names
        ][: MIN_OPTIONS * 2]  # small, bounded extra batch, fetched concurrently too
        for m in remaining:
            considered_names.add(m["name"])
        remaining_outcomes = _fetch_outcomes(remaining)
        for m in remaining:
            if len(options) >= MIN_OPTIONS:
                break
            latest = _resolve_price(db, crop, m["name"], remaining_outcomes[m["name"]])
            row = _build_option(m, latest)
            if row:
                options.append(row)

    if not options:
        # Genuinely nothing -- not even one demo-backed market -- which in
        # practice only happens for a crop with no seeded data at all.
        logger.info(
            "compare_markets timing crop=%s markets=%d network_calls=%d cache_hits=%d "
            "network_seconds=%.3f result=insufficient_data",
            crop, len(candidate_markets), timing["network_calls"], timing["cache_hits"],
            timing["network_seconds"],
        )
        return {
            "crop": crop, "quantity_kg": quantity_kg, "location": location,
            "options": [], "recommended_market": None,
            "insufficient_data": True,
            "message": "Insufficient data to make a reliable recommendation.",
            "why": None,
            "profit_gain_vs_nearest_market": 0,
            "data_source_summary": None,
            "unavailable_markets": unavailable_markets,
        }

    options.sort(key=lambda o: o["net_profit"], reverse=True)
    best = options[0]
    nearest_option = min(options, key=lambda o: o["distance_km"])
    profit_gain_vs_nearest = round(best["net_profit"] - nearest_option["net_profit"], 2)

    why = _explain_recommendation(best, nearest_option, options)

    # Bug: this used to be `"live" if any_live else "demo"`, which calls a
    # result set "live" the moment even ONE of several compared markets
    # had a live price -- silently mislabeling a mostly-demo comparison as
    # fully live. Report the actual mix instead.
    _sources_seen = {o["data_source"] for o in options}
    if _sources_seen == {"live"}:
        data_source_summary = "live"
    elif _sources_seen == {"demo"}:
        data_source_summary = "demo"
    elif _sources_seen:
        data_source_summary = "mixed"
    else:
        data_source_summary = "unavailable"  # unreachable in practice (options is non-empty here)

    # Lightweight, non-sensitive timing diagnostics: no prices, locations,
    # crop-financial figures, keys, or user data -- just counts and
    # durations, cheap enough to leave on in production and specific
    # enough to separate "network was slow" from "something else was slow"
    # without needing a live debugger session.
    logger.info(
        "compare_markets timing crop=%s markets=%d network_calls=%d cache_hits=%d "
        "network_seconds=%.3f data_source=%s",
        crop, len(options), timing["network_calls"], timing["cache_hits"],
        timing["network_seconds"], data_source_summary,
    )

    return {
        "crop": crop,
        "quantity_kg": quantity_kg,
        "location": location,
        "options": options,
        "recommended_market": best["market"],
        "insufficient_data": False,
        "message": None,
        "why": why,
        "profit_gain_vs_nearest_market": max(profit_gain_vs_nearest, 0),
        # "live" | "demo" | "mixed" | "unavailable" -- each option's own
        # data_source is still preserved unchanged above; this is only a
        # rollup summary, never a substitute for the per-option field.
        "data_source_summary": data_source_summary,
        "unavailable_markets": unavailable_markets,
    }


def _explain_recommendation(best: dict, nearest: dict, options: list) -> str:
    """
    Plain-language explanation of why `best` was recommended. Built only
    from figures already computed for this request -- no invented
    numbers -- and always frames the net-profit figures as estimates.
    """
    if best["market"] == nearest["market"]:
        return (
            f"{best['market']} is both the nearest option and gives the highest estimated "
            f"net return among the markets compared, after estimated transport, commission, "
            f"and handling costs."
        )

    highest_price_option = max(options, key=lambda o: o["modal_price_per_kg"])
    if highest_price_option["market"] != best["market"] and highest_price_option["modal_price_per_kg"] > best["modal_price_per_kg"]:
        return (
            f"Although {highest_price_option['market']} has a higher mandi price "
            f"(₹{highest_price_option['modal_price_per_kg']}/kg vs ₹{best['modal_price_per_kg']}/kg), "
            f"the estimated transportation and mandi costs to reach it reduce that advantage. "
            f"Based on the available inputs, {best['market']} currently gives the highest "
            f"estimated net return (≈₹{best['net_profit']:,} on this quantity)."
        )

    return (
        f"{best['market']} gives the highest estimated net return (≈₹{best['net_profit']:,} on this "
        f"quantity) among the markets compared, after estimated transport, commission, and "
        f"handling costs -- {best['distance_km']} km away vs {nearest['distance_km']} km for the "
        f"nearest option."
    )


# ─── Phase 8: Arrival Volume Intelligence ────────────────────────────────────

@router.get("/arrivals")
def arrival_intelligence(
    crop: str = Query(...),
    market: str = Query(...),
    days: int = Query(14, ge=3, le=60),
    db: Session = Depends(get_db),
):
    """
    Return arrival volumes + price trend for a crop/market combination.
    Uses existing MarketPrice.arrivals_tonnes from the seeded dataset.
    Data source is clearly labelled per-row.
    """
    if crop not in CROP_BY_NAME:
        raise HTTPException(status_code=404, detail="Unknown crop")

    rows = _history_rows(db, crop, market, days)
    if not rows:
        return {
            "crop": crop, "market": market, "available": False,
            "is_demo": False,
            "demo_disclaimer": None,
            "message": "No arrival data found for this crop/market.",
            "data": [],
            "summary": None,
        }

    data = [
        {
            "date": r.date,
            "arrivals_tonnes": r.arrivals_tonnes,
            "modal_price": round(r.modal_price / 100.0, 2),
            "min_price": round(r.min_price / 100.0, 2),
            "max_price": round(r.max_price / 100.0, 2),
            "data_source": r.data_source,
        }
        for r in rows
    ]

    # compute summary signals
    latest = data[-1]
    prev = data[-2] if len(data) >= 2 else None
    week_slice = data[-7:] if len(data) >= 7 else data
    two_week_slice = data[-14:] if len(data) >= 14 else data

    arrival_change_pct = None
    price_change_pct = None
    if prev:
        # Guard against None (live rows genuinely have no arrival-volume
        # field from this data.gov.in resource -- treat as "unavailable",
        # never as a real zero, so a live day doesn't fake a -100% arrival
        # swing or drag the averages below down to a false "oversupply"
        # signal).
        if prev["arrivals_tonnes"] is not None and latest["arrivals_tonnes"] is not None and prev["arrivals_tonnes"] > 0:
            arrival_change_pct = round(
                (latest["arrivals_tonnes"] - prev["arrivals_tonnes"]) / prev["arrivals_tonnes"] * 100, 1
            )
        if prev["modal_price"] and prev["modal_price"] > 0:
            price_change_pct = round(
                (latest["modal_price"] - prev["modal_price"]) / prev["modal_price"] * 100, 1
            )

    _week_known = [d["arrivals_tonnes"] for d in week_slice if d["arrivals_tonnes"] is not None]
    _2w_known = [d["arrivals_tonnes"] for d in two_week_slice if d["arrivals_tonnes"] is not None]
    avg_arrivals_week = round(sum(_week_known) / len(_week_known), 1) if _week_known else None
    avg_arrivals_2w = round(sum(_2w_known) / len(_2w_known), 1) if _2w_known else None

    # demand signal
    if arrival_change_pct is not None and price_change_pct is not None:
        if arrival_change_pct < -10 and price_change_pct > 0:
            demand_signal = "STRONG"
            signal_explanation = "Arrivals falling while price rising — strong demand signal"
        elif arrival_change_pct > 10 and price_change_pct < 0:
            demand_signal = "WEAK"
            signal_explanation = "Arrivals increasing while price falling — oversupply signal"
        elif price_change_pct > 3:
            demand_signal = "POSITIVE"
            signal_explanation = "Price trending upward"
        elif price_change_pct < -3:
            demand_signal = "NEGATIVE"
            signal_explanation = "Price trending downward"
        else:
            demand_signal = "NEUTRAL"
            signal_explanation = "Price and arrivals stable"
    else:
        demand_signal = "UNKNOWN"
        signal_explanation = "Insufficient comparison data"

    is_demo = all(d["data_source"] == "demo" for d in data)

    # ── Arrival-volume honesty (separate from price honesty above) ──
    # Bug: `is_demo` (price) can be False while every arrivals_tonnes
    # figure actually shown/averaged still came from demo rows (live rows
    # from data.gov.in always have arrivals_tonnes=None, since that
    # verified resource does not provide arrival volume at all). That
    # meant a mixed live-price/demo-history result could reach the
    # frontend with `is_demo: false` and no warning, even though every
    # arrival number on screen was seeded demo data. Compute arrival
    # honesty from which rows actually contributed a non-None arrivals
    # figure, not from the overall price data_source mix.
    _arrival_sources_seen = {d["data_source"] for d in data if d["arrivals_tonnes"] is not None}
    if not _arrival_sources_seen:
        arrivals_status = "unavailable"  # no source (live or demo) has an arrival figure at all
    elif _arrival_sources_seen == {"live"}:
        arrivals_status = "live"
    elif _arrival_sources_seen == {"demo"}:
        arrivals_status = "demo"
    else:
        arrivals_status = "mixed"  # some days live (still None today), some days demo-illustrative

    arrivals_demo_disclaimer = (
        "⚠️ Arrival volume shown is DEMO/ILLUSTRATIVE data, not a live government feed. "
        "The verified live mandi-price source (data.gov.in) does not publish arrival "
        "volume, so no live figure is available for this crop/market yet."
    ) if arrivals_status in ("demo", "mixed") else (
        "Arrival volume is not available for this crop/market from any configured source."
        if arrivals_status == "unavailable" else None
    )

    return {
        "crop": crop,
        "market": market,
        "available": True,
        "is_demo": is_demo,
        "demo_disclaimer": (
            "⚠️ Demo data — not a real-time government mandi feed. "
            "Add a data.gov.in API key to enable live arrival data."
        ) if is_demo else None,
        # Dedicated, always-accurate label for the arrival-volume figures
        # specifically -- read this instead of (or alongside) `is_demo`
        # when deciding whether to show an arrival-data warning banner.
        "arrivals_status": arrivals_status,  # "live" | "demo" | "mixed" | "unavailable"
        "arrivals_demo_disclaimer": arrivals_demo_disclaimer,
        "summary": {
            "latest_date": latest["date"],
            "today_arrivals_tonnes": latest["arrivals_tonnes"],
            "yesterday_arrivals_tonnes": prev["arrivals_tonnes"] if prev else None,
            "arrival_change_pct": arrival_change_pct,
            "modal_price": latest["modal_price"],
            "min_price": latest["min_price"],
            "max_price": latest["max_price"],
            "price_change_pct": price_change_pct,
            "avg_arrivals_7d": avg_arrivals_week,
            "avg_arrivals_14d": avg_arrivals_2w,
            "demand_signal": demand_signal,
            "signal_explanation": signal_explanation,
        },
        "data": data,
    }


@router.get("/selling-window")
def selling_window(
    crop: str = Query(...),
    market: str = Query(...),
    quantity_kg: float = Query(..., gt=0),
    storage_cost_per_kg_per_day: float = Query(0.05),
    db: Session = Depends(get_db),
):
    """
    Phase 7 — Best Selling Window recommendation.
    Combines price forecast + storage cost to find optimal sell timing.
    Based entirely on available forecast data — never invents predictions.
    """
    if crop not in CROP_BY_NAME:
        raise HTTPException(status_code=404, detail="Unknown crop")

    # Get current price
    current = _get_price(db, crop, market)
    if current.get("data_source") is None:
        raise HTTPException(status_code=404, detail="No price data available for this market")

    current_price = round(current["modal_price"] / 100.0, 2)

    # Get history for forecast
    rows = _history_rows(db, crop, market)
    is_demo = all(r.data_source == "demo" for r in rows) if rows else True
    history = [{"date": r.date, "modal_price": round(r.modal_price / 100.0, 2),
                "arrivals_tonnes": r.arrivals_tonnes} for r in rows]

    if not history:
        raise HTTPException(status_code=404, detail="Insufficient history for forecast")

    from app.services.price_predictor import predict_next_days
    forecast_dict = predict_next_days(history, days=15)
    # Convert daily_predictions list into list-of-dicts for slicing
    daily_preds = forecast_dict.get("daily_predictions", [])
    forecast_list = [{"predicted_price": p} for p in daily_preds]

    # Build options: SELL_NOW, WAIT_5, WAIT_7, STORE_15
    options = []

    def _window_option(label: str, days: int, forecast_slice: list) -> dict:
        if not forecast_slice:
            return None
        prices = [f["predicted_price"] for f in forecast_slice if f.get("predicted_price")]
        if not prices:
            return None
        avg_price = round(sum(prices) / len(prices), 2)
        max_price = round(max(prices), 2)
        storage_cost = round(quantity_kg * storage_cost_per_kg_per_day * days, 2)
        gross_revenue = round(avg_price * quantity_kg, 2)
        net_revenue = round(gross_revenue - storage_cost, 2)
        current_revenue = round(current_price * quantity_kg, 2)
        additional_revenue = round(net_revenue - current_revenue, 2)
        # risk: higher variance = higher risk
        if len(prices) > 1:
            variance = sum((p - avg_price) ** 2 for p in prices) / len(prices)
            std_dev = variance ** 0.5
            cv = std_dev / avg_price if avg_price else 0
            risk = "HIGH" if cv > 0.05 else ("MEDIUM" if cv > 0.02 else "LOW")
        else:
            risk = "MEDIUM"
        return {
            "label": label,
            "days_to_wait": days,
            "expected_price_range": {
                "min": round(min(prices), 2),
                "max": max_price,
                "avg": avg_price,
            },
            "storage_cost": storage_cost,
            "estimated_gross_revenue": gross_revenue,
            "estimated_net_revenue": net_revenue,
            "additional_revenue_vs_now": additional_revenue,
            "risk": risk,
        }

    options.append({
        "label": "SELL_NOW",
        "days_to_wait": 0,
        "expected_price_range": {"min": current_price, "max": current_price, "avg": current_price},
        "storage_cost": 0,
        "estimated_gross_revenue": round(current_price * quantity_kg, 2),
        "estimated_net_revenue": round(current_price * quantity_kg, 2),
        "additional_revenue_vs_now": 0,
        "risk": "LOW",
    })

    for label, days in [("WAIT_5_DAYS", 5), ("WAIT_7_DAYS", 7), ("STORE_15_DAYS", 15)]:
        slice_ = forecast_list[:days]
        opt = _window_option(label, days, slice_)
        if opt:
            options.append(opt)

    # Recommend: best net revenue
    best = max(options, key=lambda o: o["estimated_net_revenue"])

    return {
        "crop": crop,
        "market": market,
        "quantity_kg": quantity_kg,
        "current_price": current_price,
        "is_demo": is_demo,
        "forecast_disclaimer": (
            "⚠️ Demo forecast — based on simulated mandi data, not a real government feed."
        ) if is_demo else "Based on available historical data. Forecasts are estimates only.",
        "recommendation": best["label"],
        "recommendation_explanation": (
            f"Waiting {best['days_to_wait']} day(s) gives estimated net revenue of "
            f"₹{best['estimated_net_revenue']:,.0f} vs ₹{round(current_price * quantity_kg):,} now, "
            f"after ₹{best['storage_cost']:,.0f} estimated storage cost. Risk: {best['risk']}."
            if best["days_to_wait"] > 0 else
            "Selling now gives the best estimated net return given current forecast."
        ),
        "options": options,
    }
