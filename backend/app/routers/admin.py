import datetime as dt
import time
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth_utils import require_admin
from app.mock_data.locations import nearest_markets
from app.routers.market import _compare_markets_core
from app.services.transport_optimizer import shared_transport_plan
from app.config import logger

router = APIRouter(prefix="/admin", tags=["admin"])


def _iso(value: Optional[dt.datetime]) -> Optional[str]:
    return value.isoformat() + "Z" if value else None


@router.get("/impact")
def impact_dashboard(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    farmer_count = db.query(models.Farmer).count()
    buyer_count = db.query(models.Buyer).count()
    listings = db.query(models.CropListing).all()
    total_produce_listed_kg = sum(l.quantity_kg for l in listings)
    transactions = db.query(models.Transaction).all()
    completed_transactions = [t for t in transactions if t.status == "COMPLETED"]
    total_transaction_value = sum(t.total_amount for t in transactions)

    price_improvements = []
    listings_by_id = {l.id: l for l in listings}
    for t in transactions:
        listing = listings_by_id.get(t.listing_id)
        if listing and listing.expected_price_per_kg:
            pct = ((t.final_price_per_kg - listing.expected_price_per_kg) / listing.expected_price_per_kg) * 100
            price_improvements.append(pct)
    avg_price_improvement_pct = (
        round(sum(price_improvements) / len(price_improvements), 1) if price_improvements else 0
    )

    cumulative_income_gain = 0.0
    cumulative_transport_savings = 0.0
    # These two estimates each do a market-price lookup (and, in live mode,
    # a real HTTP call) PER listing PER nearby market -- O(listings x
    # markets). Fine for a handful of listings, but unbounded across every
    # listing ever created would make this admin-only dashboard slower with
    # every new listing, and genuinely slow (network-bound) once live mandi
    # data is configured. Cap to the most recent N listings as a
    # representative sample rather than reworking the whole computation.
    _IMPACT_SAMPLE_SIZE = 50
    sample_listings = sorted(listings, key=lambda l: l.id, reverse=True)[:_IMPACT_SAMPLE_SIZE]
    # Shared across every listing in this one admin request: many listings
    # commonly share a crop and nearby markets (e.g. several Wheat listings
    # from the same district), so the exact same (crop, market) network
    # lookup would otherwise be repeated once per listing. A plain dict,
    # scoped to this single request only (never persisted, never shared
    # across requests -- that's what the TTL caches inside
    # live_market_data.py/agmarknet_service.py are for), guarantees each
    # distinct (crop, market) pair is fetched over the network at most once
    # per /admin/impact call, however many of the 50 sampled listings ask
    # for it. See _compare_markets_core's outcome_cache docstring note.
    _outcome_cache: dict = {}
    t_impact_start = time.monotonic()
    for l in sample_listings:
        try:
            comp = _compare_markets_core(
                crop=l.crop, quantity_kg=l.quantity_kg, location=l.location,
                db=db, outcome_cache=_outcome_cache,
            )
            cumulative_income_gain += comp.get("profit_gain_vs_nearest_market", 0)
        except Exception as e:
            # Best-effort dashboard aggregation -- one bad/unmatched listing
            # (e.g. an unrecognized crop) must not break the whole admin
            # dashboard. Logged (not silently swallowed) so a real bug here
            # is still visible in server logs during development.
            logger.debug("impact_dashboard: compare_markets failed for listing %s: %s", l.id, e)
        try:
            nearby = [m for m in nearest_markets(l.location) if m["name"] != l.location]
            if nearby:
                plan = shared_transport_plan(l.crop, l.location, l.quantity_kg, nearby[0]["name"])
                cumulative_transport_savings += plan.get("estimated_savings", 0)
        except Exception as e:
            logger.debug("impact_dashboard: shared_transport_plan failed for listing %s: %s", l.id, e)

    logger.info(
        "impact_dashboard timing sample_size=%d distinct_market_lookups=%d elapsed_seconds=%.3f",
        len(sample_listings), len(_outcome_cache), time.monotonic() - t_impact_start,
    )

    return {
        "farmers_connected": farmer_count,
        "buyers_connected": buyer_count,
        "total_produce_listed_kg": round(total_produce_listed_kg, 1),
        "active_listings": len([l for l in listings if l.status == "active"]),
        "successful_transactions": len(completed_transactions),
        "income_gain_sample_size": len(sample_listings),
        "income_gain_is_sampled": len(listings) > _IMPACT_SAMPLE_SIZE,
        "total_transactions_initiated": len(transactions),
        "total_transaction_value": round(total_transaction_value, 2),
        "average_price_improvement_pct": avg_price_improvement_pct,
        "estimated_transport_savings": round(cumulative_transport_savings, 2),
        "estimated_additional_farmer_income": round(cumulative_income_gain, 2),
    }


# ---------------------------------------------------------------------------
# USER ACTIVITY -- backs the Admin Dashboard's login-activity section.
#
# All timestamps in login_events / created_at / last_login are stored as
# naive UTC (dt.datetime.utcnow(), see app/models.py::now) -- consistent
# with the rest of this codebase (JWT expiry, price-cache TTLs, etc. all
# use the same convention). "Today" / "this week" / "this month" below are
# therefore UTC calendar boundaries, not IST -- see `period_definitions` in
# the response for the exact windows used.
# ---------------------------------------------------------------------------

def _time_windows(now: dt.datetime) -> dict:
    """Shared UTC calendar-boundary definitions used by every analytics
    endpoint below, so "today"/"this week"/"this month" always mean the
    same thing everywhere in the dashboard."""
    start_of_today = dt.datetime(now.year, now.month, now.day)
    start_of_week = start_of_today - dt.timedelta(days=start_of_today.weekday())  # Monday 00:00 UTC
    start_of_month = dt.datetime(now.year, now.month, 1)
    return {"today": start_of_today, "week": start_of_week, "month": start_of_month}


@router.get("/user-activity")
def user_activity(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """
    "Registered users" = account counts (farmers/buyers table rows).
    "Registrations today/this week" = accounts whose created_at falls in
        that window (independent of whether they've ever logged in).
    "Unique users logged in" = distinct (role, user_id) pairs with at least
        one successful login_events row in the window -- counted per role
        because farmer id 3 and buyer id 3 are different people who happen
        to share a numeric id, not the same "unique user". Calculated from
        distinct user identity, never from a raw count of login requests.
    "Successful login events" = total successful login_events rows in the
        window, so the same person logging in 5 times counts as 5 events
        but 1 unique user.
    """
    now = dt.datetime.utcnow()
    w = _time_windows(now)

    total_farmers = db.query(models.Farmer).count()
    total_buyers = db.query(models.Buyer).count()

    def registrations_since(since: dt.datetime) -> int:
        return (
            db.query(models.Farmer).filter(models.Farmer.created_at >= since).count()
            + db.query(models.Buyer).filter(models.Buyer.created_at >= since).count()
        )

    def unique_users_since(since: dt.datetime) -> int:
        return (
            db.query(models.LoginEvent.role, models.LoginEvent.user_id)
            .filter(models.LoginEvent.success.is_(True), models.LoginEvent.login_time >= since)
            .distinct()
            .count()
        )

    def event_count(since: dt.datetime, success: bool) -> int:
        return (
            db.query(models.LoginEvent)
            .filter(models.LoginEvent.success.is_(success), models.LoginEvent.login_time >= since)
            .count()
        )

    return {
        "total_registered_farmers": total_farmers,
        "total_registered_buyers": total_buyers,
        "total_registered_users": total_farmers + total_buyers,
        "registrations_today": registrations_since(w["today"]),
        "registrations_this_week": registrations_since(w["week"]),
        "unique_users_logged_in_today": unique_users_since(w["today"]),
        "unique_users_logged_in_this_week": unique_users_since(w["week"]),
        "successful_login_events_today": event_count(w["today"], True),
        "successful_login_events_this_month": event_count(w["month"], True),
        "failed_login_attempts_today": event_count(w["today"], False),
        "failed_login_attempts_total": db.query(models.LoginEvent).filter(models.LoginEvent.success.is_(False)).count(),
        "as_of": _iso(now),
        "period_definitions": {
            "today": "UTC calendar day, 00:00 UTC to now",
            "this_week": "Current week, Monday 00:00 UTC to now",
            "this_month": "Current calendar month, 1st 00:00 UTC to now",
        },
    }


@router.get("/recent-activity")
def recent_activity(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """
    RECENT ACTIVITY table: most recent login_events rows first, with the
    matching farmer name/email or buyer company name/email attached for
    display (those fields already exist on Farmer/Buyer and are already
    admin-visible elsewhere -- this doesn't expose anything new). Never
    reachable by non-admin users (require_admin guard, same as /impact).
    """
    events = (
        db.query(models.LoginEvent)
        .order_by(models.LoginEvent.login_time.desc())
        .limit(limit)
        .all()
    )

    farmer_ids = {e.user_id for e in events if e.role == "farmer" and e.user_id is not None}
    buyer_ids = {e.user_id for e in events if e.role == "buyer" and e.user_id is not None}
    farmers_by_id = (
        {f.id: f for f in db.query(models.Farmer).filter(models.Farmer.id.in_(farmer_ids)).all()}
        if farmer_ids else {}
    )
    buyers_by_id = (
        {b.id: b for b in db.query(models.Buyer).filter(models.Buyer.id.in_(buyer_ids)).all()}
        if buyer_ids else {}
    )

    rows = []
    for e in events:
        name, email = None, None
        if e.role == "farmer":
            f = farmers_by_id.get(e.user_id)
            if f:
                name, email = f.name, f.email
        elif e.role == "buyer":
            b = buyers_by_id.get(e.user_id)
            if b:
                name, email = b.company_name, b.email
        rows.append({
            "user_id": e.user_id,
            "name": name,   # None when the account no longer resolves (or role == "unknown")
            "email": email,
            "role": e.role,
            "login_time": _iso(e.login_time),
            "success": e.success,
            "status": "success" if e.success else "failed",
        })
    return {"events": rows}


@router.get("/users")
def list_users(
    role: Optional[str] = Query(None, pattern="^(farmer|buyer)$"),
    q: Optional[str] = None,
    limit: int = Query(200, ge=1, le=1000),
    db: Session = Depends(get_db),
    _admin=Depends(require_admin),
):
    """
    Every registered farmer/buyer with their registration date, last_login,
    and a derived login_status -- backs the Admin Dashboard table (User /
    Role / Registered / Last Login / Login Status) and lets an admin answer
    "did this specific person ever log in" directly (search by name or
    email) instead of scanning the recent-activity feed. Sorted with the
    most recently active users first; accounts that have never logged in
    (last_login is null) sort to the bottom, which is exactly the group
    this feature exists to surface.

    login_status is derived from last_login, not stored:
        "never_logged_in" -- last_login is NULL
        "active_today"    -- last_login falls in the current UTC day
        "active_this_week"-- last_login falls in the current UTC week
        "inactive"        -- has logged in before, but not recently
    """
    now = dt.datetime.utcnow()
    w = _time_windows(now)

    def login_status(last_login: Optional[dt.datetime]) -> str:
        if last_login is None:
            return "never_logged_in"
        if last_login >= w["today"]:
            return "active_today"
        if last_login >= w["week"]:
            return "active_this_week"
        return "inactive"

    rows = []
    if role in (None, "farmer"):
        for f in db.query(models.Farmer).all():
            rows.append({
                "id": f.id, "role": "farmer", "name": f.name, "email": f.email,
                "registered_at": _iso(f.created_at), "last_login": _iso(f.last_login),
                "login_status": login_status(f.last_login),
            })
    if role in (None, "buyer"):
        for b in db.query(models.Buyer).all():
            rows.append({
                "id": b.id, "role": "buyer", "name": b.company_name, "email": b.email,
                "registered_at": _iso(b.created_at), "last_login": _iso(b.last_login),
                "login_status": login_status(b.last_login),
            })

    if q:
        ql = q.strip().lower()
        rows = [r for r in rows if ql in (r["name"] or "").lower() or ql in (r["email"] or "").lower()]

    rows.sort(key=lambda r: r["last_login"] or "", reverse=True)
    return {"users": rows[:limit], "as_of": _iso(now)}
