"""
Second live government data source: "Variety-wise Daily Market Prices Data
of Commodity" (data.gov.in resource id in `settings.data_gov_in_district_resource_id`,
default 35985678-0d79-46b4-9ed6-6f13308a1d24).

This is a DIFFERENT dataset from the one `live_market_data.py` talks to --
different resource id, different (capitalized) field names, and keyed by
`District` rather than `Market`:

    filters[State], filters[District], filters[Commodity], filters[Arrival_Date]

It commonly returns multiple rows per district/commodity/day -- one per
variety/grade -- so this module aggregates them into a single district-level
price signal (average modal price across varieties for the most recent
date) while keeping the individual variety rows available too, so callers
can show real variety-level detail if useful.

This module is intentionally independent of `live_market_data.py` -- it
does not modify or replace it. `mandi_directory.fetch_price_result()` is
what tries the two in order (market-specific resource first, this
district/variety resource second, demo dataset last) and applies the
honest "Government Mandi Price" vs "District Reference Price" labeling
depending on which one actually produced the record.

HONESTY NOTE: same caveat as `live_market_data.py` -- this was written and
exercised against the failure/fallback path only, since this sandbox has
no route to api.data.gov.in. Field names above come directly from the
resource's published OpenAPI/Swagger definition, but have not been
observed against a real successful response. Verify with real internet
access and report back if the shape differs.
"""
import datetime as dt
import statistics
from typing import Optional

import httpx

from app.config import settings
from app.services.mandi_source_normalization import to_source_state, to_source_commodity, display_state

BASE_URL = "https://api.data.gov.in/resource"
REQUEST_TIMEOUT_SECONDS = 6.0
CACHE_TTL_SECONDS = 600  # 10 minutes, same policy as live_market_data.py

_cache: dict = {}
_SENTINEL = object()


def _cache_get(key):
    entry = _cache.get(key)
    if not entry:
        return _SENTINEL
    expires_at, value = entry
    if dt.datetime.utcnow() > expires_at:
        _cache.pop(key, None)
        return _SENTINEL
    return value


def _cache_set(key, value):
    _cache[key] = (dt.datetime.utcnow() + dt.timedelta(seconds=CACHE_TTL_SECONDS), value)


def is_configured() -> bool:
    return bool(settings.data_gov_in_api_key) and settings.market_data_source == "live"


def _parse_price(raw) -> Optional[float]:
    try:
        val = float(raw)
        return val if val > 0 else None
    except (TypeError, ValueError):
        return None


def fetch_district_variety_price_status(crop_name: str, district: str, state: str = settings.default_demo_state) -> dict:
    """
    Status-aware fetch of variety-wise prices for this commodity/district/
    state, most recent day. Mirrors `live_market_data.fetch_live_price_status()`'s
    three-outcome contract instead of collapsing "no matching rows" and
    "the request itself failed" into the same None:

      {"status": "ok", "result": {...}}          real rows found
      {"status": "no_records", "result": None}   API worked, nothing here
      {"status": "error", "result": None}         API call itself failed
      {"status": "not_configured", "result": None}

    Query shape follows the documented resource contract: State and
    District are the mandatory filters; Commodity is applied too since
    CropRetain always has a specific crop selected at this point in the
    flow. Arrival_Date is deliberately NOT sent as a filter -- the
    dd-MM-yyyy vs dd-MM-yy formatting isn't independently confirmed here,
    and fetching without a date filter then sorting client-side by the
    returned Arrival_Date (below) sidesteps that ambiguity entirely while
    still landing on the most recent available date.

    On success, returns a dict with an aggregated `modal_price` (mean of
    that day's per-variety modal prices) plus the individual `varieties`
    list -- each variety row also carries `market` / `commodity_code` when
    the API includes those fields, captured defensively via `.get()` since
    that hasn't been independently confirmed present on every row.

    HONESTY NOTE: same caveat as `live_market_data.py` -- exercised against
    the not_configured/error paths only in this sandbox (no route to
    api.data.gov.in here). Field names come from the resource's documented
    schema, not an observed response. Verify with real internet access.
    """
    if not is_configured():
        return {"status": "not_configured", "result": None}

    cache_key = (crop_name, district, state)
    cached = _cache_get(cache_key)
    if cached is not _SENTINEL:
        return cached

    params = {
        "api-key": settings.data_gov_in_api_key,
        "format": "json",
        "limit": "50",
        "filters[State]": to_source_state(state),
        "filters[District]": district,
        "filters[Commodity]": to_source_commodity(crop_name),
    }
    url = f"{BASE_URL}/{settings.data_gov_in_district_resource_id}"

    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            resp = client.get(url, params=params)
        if resp.status_code != 200:
            outcome = {"status": "error", "result": None}
            _cache_set(cache_key, outcome)
            return outcome
        data = resp.json()
        records = data.get("records") or []
        if not records:
            outcome = {"status": "no_records", "result": None}
            _cache_set(cache_key, outcome)
            return outcome

        # Same defense-in-depth as live_market_data.py: don't blindly trust
        # the server-side filter -- re-validate District/State/Commodity on
        # every record before using it. Market isn't checked here since
        # this resource is genuinely keyed by district (not every row
        # reliably carries a Market field at all, per the HONESTY NOTE
        # above), but the dimensions this resource IS keyed by must match.
        source_state = to_source_state(state)
        source_commodity = to_source_commodity(crop_name)
        validated = [
            r for r in records
            if (r.get("District") or "").strip().lower() == district.strip().lower()
            and (r.get("State") or "").strip().lower() == source_state.strip().lower()
            and (r.get("Commodity") or "").strip().lower() == source_commodity.strip().lower()
        ]
        if not validated:
            outcome = {"status": "no_records", "result": None}
            _cache_set(cache_key, outcome)
            return outcome
        records = validated

        def _record_date(r):
            try:
                return dt.datetime.strptime(r.get("Arrival_Date", ""), "%d/%m/%Y")
            except (ValueError, TypeError):
                return dt.datetime.min

        records.sort(key=_record_date, reverse=True)
        latest_date = _record_date(records[0])
        latest_batch = [r for r in records if _record_date(r) == latest_date]

        modal_prices, varieties = [], []
        for r in latest_batch:
            modal = _parse_price(r.get("Modal_Price"))
            if modal is None:
                continue
            modal_prices.append(modal)
            varieties.append({
                "variety": r.get("Variety"),
                "grade": r.get("Grade"),
                "min_price": _parse_price(r.get("Min_Price")) or modal,
                "max_price": _parse_price(r.get("Max_Price")) or modal,
                "modal_price": modal,
                # Documented on this resource but not independently
                # confirmed present on every row -- captured defensively.
                "market": r.get("Market"),
                "commodity_code": r.get("Commodity_Code"),
            })

        if not modal_prices:
            outcome = {"status": "no_records", "result": None}
            _cache_set(cache_key, outcome)
            return outcome

        result = {
            "source": "live",
            "provider": "data.gov.in (Variety-wise Daily Market Prices)",
            "crop": crop_name,
            "district": district,
            "state": display_state(latest_batch[0].get("State", state)) or state,
            "arrival_date": latest_batch[0].get("Arrival_Date"),
            "modal_price": round(statistics.mean(modal_prices), 2),
            "min_price": round(min(v["min_price"] for v in varieties), 2),
            "max_price": round(max(v["max_price"] for v in varieties), 2),
            "varieties": varieties,
            "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
        }
        outcome = {"status": "ok", "result": result}
        _cache_set(cache_key, outcome)
        return outcome
    except (httpx.TimeoutException, httpx.HTTPError, ValueError, KeyError):
        outcome = {"status": "error", "result": None}
        _cache_set(cache_key, outcome)
        return outcome


def fetch_district_variety_price(crop_name: str, district: str, state: str = settings.default_demo_state) -> Optional[dict]:
    """
    Backward-compatible wrapper around `fetch_district_variety_price_status()`
    for callers that only care about "did we get real rows" and don't need
    to distinguish "no_records" from "error" (both come back as None here).
    Prefer the status-aware version for new call sites -- see
    `app/services/mandi_directory.fetch_price_result()`.
    """
    outcome = fetch_district_variety_price_status(crop_name, district, state)
    return outcome["result"] if outcome["status"] == "ok" else None
