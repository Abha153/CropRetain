"""CEDA AGMARKNET provider.

This module owns CEDA authentication, request validation, identifier lookup,
and response-shape normalization. It deliberately returns provider-neutral
records so the existing market service can keep its public contract.
"""
import datetime as dt
from typing import Optional

import httpx

from app.config import logger, settings

BASE_URL = "https://api.ceda.ashoka.edu.in/v1"
REQUEST_TIMEOUT_SECONDS = 8.0
CACHE_TTL_SECONDS = 3600  # commodity/geography reference lists -- change rarely
PRICE_CACHE_TTL_SECONDS = 600  # 10 minutes -- same policy as live_market_data.py/
# district_market_data.py for actual price data, which is daily-granularity
# but still worth a short TTL so a burst of requests for the same
# crop/market doesn't each re-hit CEDA's price+quantity endpoints.

_cache: dict = {}
_last_status = {"provider": None, "available": False}
_SENTINEL = object()

# Failures (timeouts, auth errors, unreachable host, ...) are NOT cached by
# _cache_get/_cache_set above -- those only ever store a *successful* call's
# records. Without this, every request in a loop (e.g. compare_markets()
# trying several markets) re-pays the full REQUEST_TIMEOUT_SECONDS timeout
# for get_commodities()/get_geographies() again and again even though the
# underlying failure (e.g. CEDA unreachable) hasn't changed in the last few
# seconds. This is a short-TTL cache of the failure itself so a burst of
# calls in the same request cycle fails fast after the first real attempt.
_FAILURE_CACHE_TTL_SECONDS = 30.0
_failure_cache: dict = {}


def _failure_cached(key: str) -> bool:
    expires_at = _failure_cache.get(key)
    if expires_at is None:
        return False
    if dt.datetime.utcnow() > expires_at:
        _failure_cache.pop(key, None)
        return False
    return True


def _record_failure(key: str) -> None:
    _failure_cache[key] = dt.datetime.utcnow() + dt.timedelta(seconds=_FAILURE_CACHE_TTL_SECONDS)


class AgmarknetError(Exception):
    """A CEDA request failed or returned an invalid response."""


def is_configured() -> bool:
    return bool(settings.ceda_api_key)


def status() -> dict:
    return {
        "configured": is_configured(),
        "available": _last_status["available"],
        "provider": _last_status["provider"],
    }


def _cache_get(key):
    entry = _cache.get(key)
    if not entry:
        return _SENTINEL
    expires_at, value = entry
    if dt.datetime.utcnow() > expires_at:
        _cache.pop(key, None)
        return _SENTINEL
    return value


def _cache_set(key, value, ttl_seconds=None):
    _cache[key] = (
        dt.datetime.utcnow() + dt.timedelta(seconds=ttl_seconds if ttl_seconds is not None else CACHE_TTL_SECONDS),
        value,
    )


def _request(method: str, path: str, *, json_body: Optional[dict] = None) -> dict:
    if not is_configured():
        raise AgmarknetError("CEDA API key is not configured")

    headers = {"Authorization": f"Bearer {settings.ceda_api_key}"}
    url = f"{BASE_URL}{path}"
    try:
        with httpx.Client(timeout=REQUEST_TIMEOUT_SECONDS) as client:
            response = client.request(method, url, headers=headers, json=json_body)
    except (httpx.TimeoutException, httpx.HTTPError) as exc:
        raise AgmarknetError("CEDA request failed") from exc

    if response.status_code == 401:
        raise AgmarknetError("CEDA authentication failed")
    if response.status_code == 429:
        raise AgmarknetError("CEDA rate limit exceeded")
    if response.status_code >= 500:
        raise AgmarknetError("CEDA server error")
    if response.status_code >= 400:
        raise AgmarknetError("CEDA request rejected")

    try:
        payload = response.json()
    except (ValueError, TypeError) as exc:
        raise AgmarknetError("CEDA returned invalid JSON") from exc
    if not isinstance(payload, dict):
        raise AgmarknetError("CEDA returned an invalid response")
    return payload


def _list(path: str, key: str, *, json_body: Optional[dict] = None) -> list:
    payload = _request("POST" if json_body is not None else "GET", path, json_body=json_body)
    records = payload.get(key)
    if records is None and key == "data":
        records = payload.get("data")
    if not isinstance(records, list):
        raise AgmarknetError("CEDA returned an invalid list")
    return records


def get_commodities() -> list:
    if not is_configured():
        raise AgmarknetError("CEDA API key is not configured")
    cached = _cache_get("commodities")
    if cached is not _SENTINEL:
        return cached
    if _failure_cached("commodities"):
        raise AgmarknetError("CEDA request failed (recently failed, not retried yet)")
    try:
        records = _list("/agmarknet/commodities", "commodities")
    except AgmarknetError:
        _record_failure("commodities")
        raise
    _cache_set("commodities", records)
    _last_status.update(provider="CEDA_AGMARKNET", available=True)
    return records


def get_geographies() -> list:
    if not is_configured():
        raise AgmarknetError("CEDA API key is not configured")
    cached = _cache_get("geographies")
    if cached is not _SENTINEL:
        return cached
    if _failure_cached("geographies"):
        raise AgmarknetError("CEDA request failed (recently failed, not retried yet)")
    try:
        records = _list("/agmarknet/geographies", "geographies")
    except AgmarknetError:
        _record_failure("geographies")
        raise
    _cache_set("geographies", records)
    _last_status.update(provider="CEDA_AGMARKNET", available=True)
    return records


def get_markets(commodity_id: int, state_id: int, district_id: int, indicator: str) -> list:
    if indicator not in {"price", "quantity"}:
        raise ValueError("indicator must be 'price' or 'quantity'")
    return _list(
        "/agmarknet/markets",
        "data",
        json_body={
            "commodity_id": commodity_id,
            "state_id": state_id,
            "district_id": district_id,
            "indicator": indicator,
        },
    )


def get_prices(
    commodity_id: int,
    state_id: int,
    from_date: str,
    to_date: str,
    district_id: Optional[int] = None,
    market_id: Optional[list[int]] = None,
) -> list:
    body = {
        "commodity_id": commodity_id,
        "state_id": state_id,
        "from_date": from_date,
        "to_date": to_date,
    }
    if district_id is not None:
        body["district_id"] = [district_id]
    if market_id:
        body["market_id"] = market_id
    return _list("/agmarknet/prices", "data", json_body=body)


def get_quantities(
    commodity_id: int,
    state_id: int,
    from_date: str,
    to_date: str,
    district_id: Optional[int] = None,
    market_id: Optional[list[int]] = None,
) -> list:
    body = {
        "commodity_id": commodity_id,
        "state_id": state_id,
        "from_date": from_date,
        "to_date": to_date,
    }
    if district_id is not None:
        body["district_id"] = [district_id]
    if market_id:
        body["market_id"] = market_id
    return _list("/agmarknet/quantities", "data", json_body=body)


def _find_id(records: list, name: str, id_key: str, name_key: str) -> Optional[int]:
    wanted = (name or "").strip().casefold()
    for record in records:
        if str(record.get(name_key, "")).strip().casefold() == wanted:
            return record.get(id_key)
    return None


def _resolve_ids(crop: str, state: str, district: str) -> tuple[int, int, int]:
    commodity_id = _find_id(get_commodities(), crop, "id", "name")
    if commodity_id is None:
        raise AgmarknetError("CEDA commodity was not found")

    geographies = get_geographies()
    for geography in geographies:
        if str(geography.get("state_name", "")).strip().casefold() != state.strip().casefold():
            continue
        state_id = geography.get("state_id")
        district_id = _find_id(geography.get("districts") or [], district, "district_id", "district_name")
        if state_id is not None and district_id is not None:
            return commodity_id, state_id, district_id
    raise AgmarknetError("CEDA geography was not found")


def fetch_price(crop: str, market: str, state: str, district: str) -> dict:
    """Return the latest CEDA price for the requested market, if
    available. Cached for `PRICE_CACHE_TTL_SECONDS` per (crop, market,
    state, district) -- this is the actual price fetch, not the
    commodity/geography reference-list lookups above (which have their
    own, separate cache), so without this every repeated request for the
    same crop/market re-hit CEDA's price + quantity endpoints even
    seconds apart. Failures are also cached (briefly, via the shared
    `_failure_cache` mechanism) so a burst of calls to an unreachable
    CEDA doesn't each re-pay the full request timeout -- but a failure is
    NEVER cached as if it were a successful "ok" result, and a demo/
    fallback value is never written into this cache at all (this module
    only ever sees genuine CEDA responses, never demo data)."""
    cache_key = f"price:{crop}|{market}|{state}|{district}"
    cached = _cache_get(cache_key)
    if cached is not _SENTINEL:
        return cached
    if _failure_cached(cache_key):
        raise AgmarknetError("CEDA price request failed (recently failed, not retried yet)")
    try:
        result = _fetch_price_uncached(crop, market, state, district)
    except AgmarknetError:
        _record_failure(cache_key)
        raise
    if result["status"] == "ok":
        _cache_set(cache_key, result, ttl_seconds=PRICE_CACHE_TTL_SECONDS)
    # "no_records" is a genuine, stable answer (this exact selection has
    # no CEDA record) -- also worth caching briefly so a burst of
    # requests for the same absent record doesn't each re-query CEDA, but
    # distinctly from a real "ok" price so it's never mistaken for one.
    elif result["status"] == "no_records":
        _cache_set(cache_key, result, ttl_seconds=PRICE_CACHE_TTL_SECONDS)
    return result


def _fetch_price_uncached(crop: str, market: str, state: str, district: str) -> dict:
    commodity_id, state_id, district_id = _resolve_ids(crop, state, district)
    markets = get_markets(commodity_id, state_id, district_id, "price")
    market_id = _find_id(markets, market, "market_id", "market_name")
    if market_id is None:
        return {"status": "no_records", "data": None}

    today = dt.date.today()
    rows = get_prices(
        commodity_id, state_id,
        (today - dt.timedelta(days=60)).isoformat(), today.isoformat(),
        district_id=district_id, market_id=[market_id],
    )
    matching = [row for row in rows if row.get("market_id") == market_id]
    if not matching:
        return {"status": "no_records", "data": None}
    latest = max(matching, key=lambda row: row.get("date", ""))
    modal = _positive_number(latest.get("modal_price"))
    if modal is None:
        return {"status": "no_records", "data": None}

    quantity = None
    try:
        quantity_rows = get_quantities(
            commodity_id, state_id,
            latest.get("date", today.isoformat()), latest.get("date", today.isoformat()),
            district_id=district_id, market_id=[market_id],
        )
        quantity = next(
            (_positive_number(row.get("quantity")) for row in quantity_rows
             if row.get("market_id") == market_id),
            None,
        )
    except AgmarknetError:
        logger.warning("CEDA quantity request failed; continuing with price data")

    _last_status.update(provider="CEDA_AGMARKNET", available=True)
    return {
        "status": "ok",
        "data": {
            "source": "CEDA_AGMARKNET",
            "provider": "CEDA AGMARKNET",
            "crop": crop,
            "market": market,
            "state": state,
            "arrival_date": latest.get("date"),
            "modal_price": modal,
            "min_price": _positive_number(latest.get("min_price")) or modal,
            "max_price": _positive_number(latest.get("max_price")) or modal,
            "quantity": quantity,
            "market_id": market_id,
            "source_resource": "market",
            "fetched_at": dt.datetime.utcnow().isoformat() + "Z",
        },
    }


def _positive_number(value) -> Optional[float]:
    try:
        number = float(value)
        return number if number > 0 else None
    except (TypeError, ValueError):
        return None
