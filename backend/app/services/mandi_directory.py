"""
Official mandi/APMC name discovery and mapping layer.

WHY THIS EXISTS
----------------
`live_market_data.fetch_live_price_status()` (kept exactly as-is -- see
that module) queries data.gov.in with `filters[market] = <name>`. That is
an EXACT string match against whatever the government dataset calls a
market. CropRetain's own town/location list (`app/mock_data/locations.py`)
was built for distance/transport math, not as a government mandi
directory, so a name like "Bilaspur" is not guaranteed to be
spelled/formatted identically to the official Agmarknet "market" field
for that APMC. Matching on the raw local name alone silently produces a
lot of avoidable demo fallbacks.

This module does NOT touch or replace `fetch_live_price_status()`. It sits
in front of it:

    local town name  -->  resolve_candidate_market_names()  -->  try each
    candidate against the live resource, in confidence order, first
    genuine hit wins  -->  falls through to the district/variety resource,
    then CEDA AGMARKNET, and finally to the demo dataset, exactly as documented in
    `fetch_price_result()` below.

CONSERVATIVE MATCHING, BY DESIGN
---------------------------------
Wrong live mandi data is worse than no live data. Every candidate name
this module tries is one of:
  1. The local town name itself, tried VERBATIM as an exact server-side
     filter -- this carries no false-positive risk at all: the government
     API either has a record under that exact string or it returns
     nothing. There is no way for this step to silently return the wrong
     mandi's data.
  2. A hand-curated alias (`ALIAS_HINTS`) -- someone deliberately
     confirmed this mapping, so it's treated as maximum confidence.
  3. A fuzzy match against the real discovered market list for the state
     -- and ONLY the single best match, and ONLY if its similarity score
     clears a high bar (`FUZZY_ACCEPT_THRESHOLD`). A close-but-ambiguous
     candidate is REJECTED, not guessed at. Every fuzzy attempt (accepted
     or rejected) is logged internally (see `_log_match_decision`) with
     the local name, the candidate, the score, and the reason -- never
     surfaced to end users, but auditable server-side.

Discovery: `discover_state_markets()` asks the live API for the *actual*
list of market names the government dataset has for a state (querying
only `filters[state]`, no market/commodity filter), paginating through
ALL available pages rather than an arbitrary fixed record cap, then
fuzzy-matches CropRetain's local town names against that real list (difflib
-- no extra dependency needed). Results are cached in-process for 24h so
we don't re-discover on every request.

HONESTY NOTE: exactly like `live_market_data.py`, this was written and
exercised against the failure/fallback path only -- this sandbox has no
route to api.data.gov.in. The discovery HTTP call, caching, and
confidence-scored matching logic are real, but nobody has yet watched it
resolve a real Chhattisgarh mandi name against the live dataset. Verify
with real internet access and a valid key, and expect to tune
ALIAS_HINTS below once you see the actual official names data.gov.in
returns.
"""
import datetime as dt
import difflib
from concurrent.futures import ThreadPoolExecutor
from typing import List, Optional

import httpx

from app.config import settings, logger
from app.mock_data.locations import MARKETS
from app.services import live_market_data, district_market_data, agmarknet_service
from app.services.mandi_source_normalization import to_source_state

DISCOVERY_CACHE_TTL_SECONDS = 24 * 60 * 60  # 24h -- market directories change rarely
DISCOVERY_TIMEOUT_SECONDS = 8.0
DISCOVERY_PAGE_LIMIT = 200  # per-request page size (data.gov.in's own per-call cap)
# Safety ceiling on total *pages* fetched during one discovery call -- NOT
# a claim that data.gov.in caps state market directories at this size.
# Paging continues until the API itself returns a short/empty page; this
# just guards against an unexpected infinite-pagination response shape.
DISCOVERY_MAX_PAGES = 50  # up to 10,000 records -- discovery is a rare, cached (24h) call

# A fuzzy candidate is only ever accepted above this similarity score.
# Deliberately high: an ambiguous or "looks kind of close" match is exactly
# the failure mode this module exists to avoid (wrong live data is worse
# than no live data), so this is tuned conservative, not permissive.
FUZZY_ACCEPT_THRESHOLD = 0.90

# Hand-maintained hints for cases where CropRetain's local/town name is known
# (or suspected) to differ from the official Agmarknet "market" field --
# e.g. the APMC serving a town is usually named after a nearby bigger mandi
# town, or uses "New <Name>" / "<Name> (F&V)" style naming. Add to this as
# real mismatches are confirmed by running against the live API -- treated
# as maximum confidence since a human verified them, not the fuzzy matcher.
ALIAS_HINTS = {
    "Bilha": ["Bilaspur", "Bilha"],
    "Ambikapur": ["Ambikapur", "Surguja", "Ambikapur(Surguja)"],
    "Mahasamund": ["Mahasamund"],
}

# CropRetain's local town names -> the Chhattisgarh REVENUE DISTRICT they sit
# in. Needed only for the second resource (district_market_data.py), which
# is keyed by District rather than Market. Most of our towns are their own
# district headquarters; the exceptions are noted.
LOCAL_MARKET_TO_DISTRICT = {
    "Bilaspur": "Bilaspur",
    "Raipur": "Raipur",
    "Durg": "Durg",
    "Raigarh": "Raigarh",
    "Korba": "Korba",
    "Bilha": "Bilaspur",       # Bilha is a tehsil within Bilaspur district
    "Ambikapur": "Surguja",    # Ambikapur is the HQ of Surguja district
    "Rajnandgaon": "Rajnandgaon",
    "Mahasamund": "Mahasamund",
    "Jagdalpur": "Bastar",     # Jagdalpur is the HQ of Bastar district
}

_discovery_cache: dict = {}  # state -> (expires_at, list_of_official_market_names)


def _cache_get(key):
    entry = _discovery_cache.get(key)
    if not entry:
        return None
    expires_at, value = entry
    if dt.datetime.utcnow() > expires_at:
        _discovery_cache.pop(key, None)
        return None
    return value


def _cache_set(key, value):
    _discovery_cache[key] = (
        dt.datetime.utcnow() + dt.timedelta(seconds=DISCOVERY_CACHE_TTL_SECONDS),
        value,
    )


def _log_match_decision(local_name: str, candidate: Optional[str], score: Optional[float],
                         accepted: bool, reason: str) -> None:
    """
    Internal-only audit trail for the matching decision -- never surfaced
    to end users (the API/UI only ever say "matched" or "no verified
    government market match found"). Logged at INFO so it's queryable
    server-side without turning on DEBUG, but stays out of any
    user-facing response payload.
    """
    logger.info(
        "mandi_match local=%r candidate=%r score=%s accepted=%s reason=%s",
        local_name, candidate, f"{score:.2f}" if score is not None else "n/a",
        accepted, reason,
    )


def discover_state_markets(state: str = settings.default_demo_state, max_pages: int = DISCOVERY_MAX_PAGES) -> List[str]:
    """
    Ask the live government dataset what markets it actually has for this
    state (no market/commodity filter). Pages through results until the
    API returns a short page (fewer rows than the page size) or an empty
    one -- i.e. until data.gov.in itself says there's no more, not an
    arbitrary fixed record count. `max_pages` is a safety ceiling against
    a malformed/looping response, not a designed limit (see module
    docstring). Returns a sorted list of distinct official market names,
    or [] if unconfigured/unreachable/empty -- never raises.
    """
    if not live_market_data.is_configured():
        return []

    cached = _cache_get(state)
    if cached is not None:
        return cached

    names = set()
    try:
        with httpx.Client(timeout=DISCOVERY_TIMEOUT_SECONDS) as client:
            for page in range(max_pages):
                params = {
                    "api-key": settings.data_gov_in_api_key,
                    "format": "json",
                    "limit": str(DISCOVERY_PAGE_LIMIT),
                    "offset": str(page * DISCOVERY_PAGE_LIMIT),
                    # Same resource, same confirmed fix as
                    # live_market_data.py -- see its "FILTER KEY" comment.
                    "filters[state.keyword]": to_source_state(state),
                }
                url = f"{live_market_data.BASE_URL}/{settings.data_gov_in_resource_id}"
                resp = client.get(url, params=params)
                if resp.status_code != 200:
                    break
                data = resp.json()
                records = data.get("records") or []
                if not records:
                    break
                for r in records:
                    m = (r.get("market") or "").strip()
                    if m:
                        names.add(m)
                if len(records) < DISCOVERY_PAGE_LIMIT:
                    break  # short page -- this was the last one
    except (httpx.TimeoutException, httpx.HTTPError, ValueError, KeyError):
        # Discovery is best-effort -- on any failure just return whatever
        # (possibly nothing) we gathered so far, never raise into a request.
        pass

    result = sorted(names)
    _cache_set(state, result)
    return result


def resolve_candidate_market_names(local_name: str, state: str = settings.default_demo_state) -> List[str]:
    """
    Build an ordered, deduped list of market names worth trying against
    the live API for this local/town name -- best guess first:
      1. The local name itself -- zero false-positive risk, see module
         docstring.
      2. Hand-maintained alias hints, if any exist for this town --
         human-verified, maximum confidence.
      3. AT MOST ONE fuzzy match from the real discovered market list for
         this state, and only if it clears `FUZZY_ACCEPT_THRESHOLD`. Every
         fuzzy candidate considered is logged via `_log_match_decision`,
         whether accepted or rejected, so matching behaviour is auditable
         without ever guessing in the response itself.
    Always returns at least [local_name], so a caller that ignores this
    module entirely still behaves exactly as before.
    """
    candidates = [local_name]
    for hint in ALIAS_HINTS.get(local_name, []):
        if hint not in candidates:
            candidates.append(hint)
        _log_match_decision(local_name, hint, None, True, "manual_alias")

    official = discover_state_markets(state)
    if official:
        scored = sorted(
            ((name, difflib.SequenceMatcher(None, local_name.lower(), name.lower()).ratio())
             for name in official),
            key=lambda pair: pair[1],
            reverse=True,
        )
        if scored:
            best_name, best_score = scored[0]
            runner_up_score = scored[1][1] if len(scored) > 1 else 0.0
            if best_score >= FUZZY_ACCEPT_THRESHOLD and best_name not in candidates:
                candidates.append(best_name)
                _log_match_decision(local_name, best_name, best_score, True, "fuzzy_high_confidence")
            else:
                reason = (
                    "below_threshold" if best_score < FUZZY_ACCEPT_THRESHOLD
                    else "already_a_candidate"
                )
                _log_match_decision(local_name, best_name, best_score, False, reason)
            # Log the runner-up too when it's close enough to matter, purely
            # for audit visibility into ambiguous cases -- never acted on.
            if len(scored) > 1 and runner_up_score >= FUZZY_ACCEPT_THRESHOLD - 0.10:
                _log_match_decision(local_name, scored[1][0], runner_up_score, False, "runner_up_not_used")

    return candidates


def _normalize_source_record(raw: dict, source: str, source_resource: str) -> dict:
    """Common shape for a single provider's single record, regardless of
    which of the three underlying resources (data.gov.in market-level,
    data.gov.in district/variety-level, or Agmarknet-via-CEDA) produced
    it. `source` is always exactly "data.gov.in" or "agmarknet" -- never
    a resource-specific label -- since that's the granularity the rest of
    the app (and the response text) attributes data to."""
    return {
        "source": source,
        "source_resource": source_resource,  # "market" | "district_variety"
        "commodity": raw.get("crop"),
        "market": raw.get("market"),
        "state": raw.get("state"),
        "date": raw.get("arrival_date"),
        "variety": raw.get("variety"),
        "grade": raw.get("grade"),
        "min_price": raw.get("min_price"),
        "max_price": raw.get("max_price"),
        "modal_price": raw.get("modal_price"),
        "arrival": raw.get("quantity"),
        "fetched_at": raw.get("fetched_at"),
    }


# Two modal prices for the same commodity/market/date are treated as
# "agreeing" (merged silently) if they're within this fraction of each
# other -- real government price feeds routinely differ by a rupee or two
# from rounding/timing even when reporting the same underlying mandi
# session. Anything wider is a genuine discrepancy and must be flagged,
# never silently averaged away (see module docstring / fetch_price_result).
_PRICE_AGREEMENT_TOLERANCE = 0.02  # 2%


def _parse_source_date(value):
    """Parse a date string from either provider into a comparable value.
    data.gov.in reports DD/MM/YYYY; CEDA/Agmarknet reports YYYY-MM-DD.
    Neither sorts correctly as a plain string against the other, and a
    naive string comparison would also wrongly treat the same calendar
    date as two different ones when grouping records -- see
    `_combine_source_records`. Falls back to datetime.min (sorts first,
    never wins a "most recent" comparison) for anything unparseable."""
    if not value:
        return dt.datetime.min
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(value, fmt)
        except (ValueError, TypeError):
            continue
    return dt.datetime.min


def _combine_source_records(records: List[dict]) -> dict:
    """
    Combine 1+ per-source normalized records (see `_normalize_source_record`)
    for the same crop/market into one response payload, WITHOUT discarding
    any source's values.

    Always returns a dict with:
      sources            -- sorted list of every source that had a usable
                             record ("data.gov.in", "agmarknet", or both).
      source_conflict     -- True if 2+ sources reported the same date's
                             modal price and those prices genuinely
                             disagree (see _PRICE_AGREEMENT_TOLERANCE).
      source_values       -- {source_name: normalized_record}, so a caller
                             can always see exactly what each source said,
                             even when they disagree.
      observations        -- every distinct (date, source) record, so two
                             sources reporting *different* dates are both
                             preserved rather than one being discarded.
    Top-level modal_price/min_price/max_price/date/variety/grade/etc. are
    taken from the MOST RECENT observation across all sources (what "the
    latest price" means when a caller doesn't care about per-source
    detail) -- this mirrors the pre-multi-source single-record shape so
    every existing caller keeps working unchanged.
    """
    by_source = {r["source"]: r for r in records}
    sources = sorted(by_source.keys())

    # "Same observation" = same reported CALENDAR date, not the same raw
    # string -- data.gov.in reports DD/MM/YYYY, CEDA reports YYYY-MM-DD,
    # so grouping on the raw string would treat the identical date as two
    # different ones and silently skip conflict detection entirely. Parse
    # both into a comparable value before grouping.
    by_date: dict = {}
    for r in records:
        by_date.setdefault(_parse_source_date(r.get("date")), []).append(r)

    conflict = False
    for parsed_date, recs_for_date in by_date.items():
        prices = [r["modal_price"] for r in recs_for_date if r.get("modal_price") is not None]
        if len(prices) >= 2 and max(prices) > 0:
            spread = (max(prices) - min(prices)) / max(prices)
            if spread > _PRICE_AGREEMENT_TOLERANCE:
                conflict = True

    latest = max(records, key=lambda r: _parse_source_date(r.get("date")))

    combined = dict(latest)
    combined["sources"] = sources
    combined["source_conflict"] = conflict
    combined["source_values"] = by_source
    combined["observations"] = records
    return combined


def fetch_price_result(crop_name: str, local_market: str, state: str = settings.default_demo_state) -> dict:
    """
    Status-aware price lookup -- the single entry point routers should
    use. Distinguishes real outcomes rather than collapsing them into a
    single "use demo data" fallback:

      {"status": "ok", "data": {...}}
          At least one provider returned a genuine record. `data["sources"]`
          lists every provider that contributed ("data.gov.in", "agmarknet",
          or both -- see module docstring for how this is decided).
          `data["source_conflict"]` is True if the providers genuinely
          disagree on the same date's modal price (see
          `_combine_source_records`); `data["source_values"]` always has
          the full per-source detail, so a caller can show both numbers
          even when they conflict.
          `data["source_resource"]` on the top-level (latest) values is
          either:
            "market"           -- a real, mandi-specific record.
                                   Label this "Government Mandi Price".
            "district_variety" -- data.gov.in's district/variety-
                                   aggregated resource. Label this
                                   "District Reference Price" -- see
                                   `data["district_reference_note"]`.

      {"status": "no_records", "data": None}
          Every configured provider responded successfully but none has a
          record for this crop/market/state. This is NOT a failure --
          callers should show "No official government record found for
          this selection." and must NOT substitute demo data.

      {"status": "error", "data": None}
          At least one configured provider itself failed (network error,
          timeout, non-200, bad key, unparseable response) and no
          provider produced a genuine record. This is the ONLY status
          that should trigger a demo-data fallback.

      {"status": "not_configured", "data": None}
          No provider is configured at all (no keys / demo mode). Not an
          error -- this is the normal, expected state for a demo
          deployment, so callers should fall back to demo data without
          an "unavailable" framing.

    ARCHITECTURE NOTE (multi-source): data.gov.in and Agmarknet-via-CEDA
    are queried CONCURRENTLY, not as a first-hit-wins fallback chain --
    both are genuinely independent government-linked observations of the
    same underlying mandi, so both are fetched whenever both are
    configured, normalized into a common shape, and combined by
    `_combine_source_records` rather than one silently shadowing the
    other. data.gov.in's own market-level candidate-name resolution (see
    `resolve_candidate_market_names`) still runs its conservative,
    confidence-ordered matching internally -- that's data.gov.in's own
    fetch, not a cross-provider fallback.
    """
    # Thread-safe-enough append target for each branch's own status
    # observations (each branch only ever appends from its own worker
    # thread, list.append is atomic under the GIL, and nothing reads this
    # list until both futures below have already been resolved).
    _statuses: list = []

    def _fetch_data_gov_in() -> Optional[dict]:
        """data.gov.in's own market-level candidate resolution, sequential
        and confidence-ordered by design (see module docstring) -- this is
        internal to the data.gov.in fetch itself, not a fallback to a
        different provider. Falls back to the district/variety resource
        only if no market-level candidate has a record; still reported as
        "data.gov.in" either way."""
        for candidate in resolve_candidate_market_names(local_market, state):
            outcome = live_market_data.fetch_live_price_status(crop_name, candidate, state)
            if outcome["status"] == "ok":
                result = dict(outcome["result"])
                result["local_market_name"] = local_market
                result["matched_market_name"] = candidate
                record = _normalize_source_record(result, "data.gov.in", "market")
                record["matched_market_name"] = candidate
                return record
            if outcome["status"] == "error":
                _statuses.append("error")
            elif outcome["status"] == "not_configured":
                _statuses.append("not_configured")
            elif outcome["status"] == "no_records":
                _statuses.append("no_records")

        district = LOCAL_MARKET_TO_DISTRICT.get(local_market, local_market)
        district_outcome = district_market_data.fetch_district_variety_price_status(crop_name, district, state)
        if district_outcome["status"] == "ok":
            result = dict(district_outcome["result"])
            result["local_market_name"] = local_market
            result["matched_market_name"] = f"{district} (district)"
            record = _normalize_source_record(result, "data.gov.in", "district_variety")
            record["matched_market_name"] = result["matched_market_name"]
            record["district_reference_note"] = (
                "Calculated from available variety-level government records; "
                "this is not a specific mandi modal price."
            )
            return record
        if district_outcome["status"] == "error":
            _statuses.append("error")
        elif district_outcome["status"] == "not_configured":
            _statuses.append("not_configured")
        elif district_outcome["status"] == "no_records":
            _statuses.append("no_records")
        return None

    def _fetch_agmarknet() -> Optional[dict]:
        if not agmarknet_service.is_configured():
            _statuses.append("not_configured")
            return None
        district = LOCAL_MARKET_TO_DISTRICT.get(local_market, local_market)
        try:
            outcome = agmarknet_service.fetch_price(crop_name, local_market, state, district)
        except agmarknet_service.AgmarknetError:
            logger.warning("agmarknet (CEDA) request failed for %s/%s", crop_name, local_market)
            _statuses.append("error")
            return None
        if outcome["status"] == "ok":
            record = _normalize_source_record(outcome["data"], "agmarknet", "market")
            record["matched_market_name"] = local_market
            return record
        if outcome["status"] == "error":
            _statuses.append("error")
        elif outcome["status"] == "no_records":
            _statuses.append("no_records")
        return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_data_gov_in = pool.submit(_fetch_data_gov_in)
        f_agmarknet = pool.submit(_fetch_agmarknet)
        data_gov_in_record = f_data_gov_in.result()
        agmarknet_record = f_agmarknet.result()

    saw_error = "error" in _statuses
    saw_no_records = "no_records" in _statuses
    saw_not_configured = "not_configured" in _statuses

    records = [r for r in (data_gov_in_record, agmarknet_record) if r is not None]
    if records:
        combined = _combine_source_records(records)
        # Backward-compatible field name for every existing caller that
        # doesn't yet know about multi-source (`_resolve_price` etc.):
        combined["crop"] = combined.pop("commodity", crop_name)
        return {"status": "ok", "data": combined}

    # Priority when nothing usable was found: a genuine error anywhere
    # outranks everything (something may be hiding real data behind a
    # failure); otherwise, if AT LEAST ONE provider was actually
    # configured and queried and came back with a confirmed empty result,
    # that's "no_records" (a real answer: no government record exists)
    # even if the OTHER provider happens not to be configured -- one
    # provider's non-configuration must never downgrade a definitive
    # "no_records" from the other into an "unavailable" framing. Only
    # when NO provider was configured at all does this fall through to
    # "not_configured".
    if saw_error:
        return {"status": "error", "data": None}
    if saw_no_records:
        return {"status": "no_records", "data": None}
    if saw_not_configured:
        return {"status": "not_configured", "data": None}
    return {"status": "no_records", "data": None}

def known_local_markets() -> List[str]:
    return [m["name"] for m in MARKETS]


def state_for_market(market_name: str) -> str:
    for market in MARKETS:
        if market["name"].casefold() == market_name.casefold():
            return market["state"]
    return settings.default_demo_state
