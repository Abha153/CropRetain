"""
Live government mandi-price data integration (data.gov.in).

Resource: "Current Daily Price of Various Commodities from Various Markets
(Mandi)" -- published by the Ministry of Agriculture & Farmers Welfare via
the data.gov.in Open Government Data (OGD) platform, resource id
9ef84268-d588-465a-a308-a864a43d0070 (Agmarknet-sourced).

HONESTY NOTE (important -- read before trusting this blindly):
This module implements a real HTTP client against the documented
data.gov.in API contract, using the API key configured in
`backend/.env` (see `.env.example`). It was NOT possible to verify live
connectivity to api.data.gov.in from the sandboxed development
environment this was built in -- that domain is outside the sandbox's
network allowlist. The request/response handling, field mapping, and
fallback logic have all been exercised and tested (the "API unreachable /
times out / returns no data" path is exactly what actually happens in that
sandbox, so that failure path is genuinely tested), but a live successful
fetch has not been observed by the assistant that wrote this. Please
verify against the real API once running with normal internet access, and
report back if the field names/response shape have changed -- data.gov.in
resource schemas do occasionally change without notice.

Design: CropRetain NEVER lets a live-data failure break the app or silently
serve stale/wrong data as if it were fresh, and never conflates "the
government API is fine but has no record for this selection" with "the
live fetch itself failed" -- see `fetch_live_price_status()` below for
the three-way status contract that keeps those separate. `fetch_live_price()`
is kept only as a backward-compatible wrapper. Callers (see
app/services/mandi_directory.py and app/routers/market.py) fall back to
the demo dataset only on a genuine "error", and label every response with
an accurate data_source so the UI's data-transparency badge is never
guessed at.
"""
import datetime as dt
from typing import Optional

import httpx

from app.config import settings
from app.services.mandi_source_normalization import (
    to_source_state, to_source_commodity, display_state,
)

BASE_URL = "https://api.data.gov.in/resource"
REQUEST_TIMEOUT_SECONDS = 6.0
CACHE_TTL_SECONDS = 600  # 10 minutes -- avoids re-hitting the live API for
                          # every market in a single compare_markets() call

_cache: dict = {}  # (crop, market, state) -> (expires_at, result_or_None)
_SENTINEL = object()


def _cache_get(key):
    entry = _cache.get(key)
    if not entry:
        return _SENTINEL  # not cached at all -- caller should fetch
    expires_at, value = entry
    if dt.datetime.utcnow() > expires_at:
        _cache.pop(key, None)
        return _SENTINEL
    return value  # may legitimately be None (a cached miss)


def _cache_set(key, value):
    _cache[key] = (dt.datetime.utcnow() + dt.timedelta(seconds=CACHE_TTL_SECONDS), value)



class LiveMarketDataError(Exception):
    pass


def is_configured() -> bool:
    return bool(settings.data_gov_in_api_key) and settings.market_data_source == "live"


def _parse_price(raw: str) -> Optional[float]:
    try:
        val = float(raw)
        return val if val > 0 else None
    except (TypeError, ValueError):
        return None


def fetch_live_price_status(crop_name: str, market_name: str, state: str = settings.default_demo_state) -> dict:
    """
    Status-aware fetch, distinguishing two genuinely different situations
    that the old boolean-ish `fetch_live_price()` used to collapse into a
    single `None`:

      {"status": "ok", "result": {...}}
          A real record was found -- see `result` for the parsed row.

      {"status": "no_records", "result": None}
          The live API call itself succeeded (HTTP 200, valid JSON) but
          simply has no record for this exact crop/market/state/date
          combination. This is NOT a failure and must never trigger the
          demo-data fallback -- per spec, the honest response for this
          case is "No official government record found for this
          selection.", not a silently-substituted demo price.

      {"status": "error", "result": None}
          The live API call itself failed -- not configured, network
          error, timeout, non-200 status, or an unparseable/unexpected
          response body. THIS is the only case that should fall back to
          the demo dataset.

    Never raises. Caching mirrors the previous behaviour (both genuine
    misses and errors are cached briefly so a bad combination or an
    unreachable endpoint doesn't add multi-second delays to every request
    in a compare_markets() call).

    HONESTY NOTE: this method has been exercised end-to-end against the
    "not configured" / "error" paths only -- this build/sandbox has no
    network route to api.data.gov.in, so the "ok" and real "no_records"
    paths are implemented against the documented API contract but have
    not been observed against a real response by the assistant that wrote
    this. Verify with real internet access and a valid key.
    """
    if not is_configured():
        return {"status": "not_configured", "result": None}

    cache_key = (crop_name, market_name, state)
    cached = _cache_get(cache_key)
    if cached is not _SENTINEL:
        return cached

    params = {
        "api-key": settings.data_gov_in_api_key,
        "format": "json",
        "limit": "20",
        # FILTER KEY: "state.keyword" is confirmed correct against a real,
        # live, successful response's own `field_exposed` metadata block
        # (data.gov.in's authoritative declaration of filterable fields for
        # this exact resource) -- captured and verified earlier in this
        # project's history. Plain "state" silently returns zero/wrong rows
        # for this resource; only the State field needs ".keyword", the
        # others (market, commodity, variety, grade) do not.
        "filters[state.keyword]": to_source_state(state),
        "filters[market]": market_name,
        "filters[commodity]": to_source_commodity(crop_name),
    }

    url = f"{BASE_URL}/{settings.data_gov_in_resource_id}"
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
            # A genuine, successful "nothing here" response -- not an error.
            outcome = {"status": "no_records", "result": None}
            _cache_set(cache_key, outcome)
            return outcome

        # Defense in depth: the request already filtered server-side by
        # state/market/commodity, so this SHOULD be unnecessary -- but a
        # wrong market's price shown against the requested market is
        # unacceptable, and relying solely on an external API's filter
        # behaviour (which could be case-insensitive, substring-based, or
        # simply buggy) is exactly the kind of blind trust that produced
        # real cross-state mismatches before (e.g. a "Bilaspur" query
        # returning a Himachal Pradesh record instead of Chhattisgarh's).
        # Re-validate every record client-side and drop any that don't
        # actually match what was requested, rather than trusting
        # records[0] on the server's word alone.
        source_state = to_source_state(state)
        source_commodity = to_source_commodity(crop_name)
        validated = [
            r for r in records
            if (r.get("market") or "").strip().lower() == market_name.strip().lower()
            and (r.get("state") or "").strip().lower() == source_state.strip().lower()
            and (r.get("commodity") or "").strip().lower() == source_commodity.strip().lower()
        ]
        if not validated:
            # The API returned rows, but none of them actually match the
            # requested market/state/commodity once double-checked -- treat
            # this the same as a genuine no-match rather than silently
            # accepting a record for the wrong place.
            outcome = {"status": "no_records", "result": None}
            _cache_set(cache_key, outcome)
            return outcome
        records = validated

        # Records are typically most-recent-first from this API, but sort
        # defensively by arrival_date to be sure we use the latest one.
        def _record_date(r):
            try:
                return dt.datetime.strptime(r.get("arrival_date", ""), "%d/%m/%Y")
            except (ValueError, TypeError):
                return dt.datetime.min
        records.sort(key=_record_date, reverse=True)
        latest = records[0]

        modal = _parse_price(latest.get("modal_price"))
        min_p = _parse_price(latest.get("min_price"))
        max_p = _parse_price(latest.get("max_price"))
        if modal is None:
            # Record(s) exist but none carry a usable modal price -- treat
            # as "nothing usable here" rather than a hard error.
            outcome = {"status": "no_records", "result": None}
            _cache_set(cache_key, outcome)
            return outcome

        result = {
            "source": "live",
            "provider": "data.gov.in (Agmarknet)",
            "crop": crop_name,
            "market": market_name,
            "state": display_state(latest.get("state", state)) or state,
            "arrival_date": latest.get("arrival_date"),
            "modal_price": modal,          # Rs per quintal, matches internal convention
            "min_price": min_p or modal,
            "max_price": max_p or modal,
            "variety": latest.get("variety"),
            "grade": latest.get("grade"),
            "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
        }
        outcome = {"status": "ok", "result": result}
        _cache_set(cache_key, outcome)
        return outcome
    except (httpx.TimeoutException, httpx.HTTPError, ValueError, KeyError):
        # Network failure, non-JSON response, unexpected shape, etc. --
        # always degrade gracefully, never raise into the request path.
        # Cache the miss too (briefly) so a flaky/unreachable endpoint
        # doesn't add multi-second delays to every single request.
        outcome = {"status": "error", "result": None}
        _cache_set(cache_key, outcome)
        return outcome


def fetch_live_price(crop_name: str, market_name: str, state: str = settings.default_demo_state) -> Optional[dict]:
    """
    Backward-compatible convenience wrapper around
    `fetch_live_price_status()` for any caller that only cares about
    "did we get a real record" and doesn't need to distinguish
    "no_records" from "error" (both simply come back as None here).
    Prefer `fetch_live_price_status()` for new call sites -- see
    `app/services/mandi_directory.fetch_price_result()`.
    """
    outcome = fetch_live_price_status(crop_name, market_name, state)
    return outcome["result"] if outcome["status"] == "ok" else None
