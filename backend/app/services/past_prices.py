"""Past-price series for the Price Forecast page.

Sources, merged per (crop, market, date) with later/live data winning:
  * bundled recorded history   app/data/past_prices.csv  (scripts/build_past_prices.py)
  * live rows already stored    market_prices with data_source="live"
Demo/synthetic rows are never included. Nothing is interpolated: a stretch with no recorded prices is
reported as a gap, not filled in. Prices are INR/quintal; per-kg values are price / 100.
"""
import csv
import datetime as dt
import statistics
from functools import lru_cache
from pathlib import Path
from typing import Optional

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_FILE = DATA_DIR / "past_prices.csv"
STATE_FILE = DATA_DIR / "state_prices.csv"        # state-wide daily weighted-average modal price
NATIONAL_FILE = DATA_DIR / "national_prices.csv"  # national wholesale price on the same date in earlier years
GAP_DAYS = 30        # no recorded price for this long -> shown as a gap
STEADY_PCT = 3.0     # |change| below this is "steady"
WINDOWS = (30, 90, 180, 365)


def _f(v) -> Optional[float]:
    try:
        x = float(v)
        return x if x == x and x > 0 else None
    except (TypeError, ValueError):
        return None


@lru_cache(maxsize=1)
def _bundled() -> dict:
    out = {}
    if not DATA_FILE.exists():
        return out
    with open(DATA_FILE, newline="") as fh:
        for r in csv.DictReader(fh):
            modal = _f(r["modal"])
            if modal is None:
                continue
            kind = "history" if r["source"] == "history" else "snapshot"
            out.setdefault((r["crop"], r["market"]), {})[r["date"]] = {
                "date": r["date"], "modal": modal, "min": _f(r["min"]), "max": _f(r["max"]),
                "source": kind, "source_note": r["source"], "note": r.get("note") or ""}
    return out


@lru_cache(maxsize=1)
def _state_series() -> dict:
    out = {}
    if not STATE_FILE.exists():
        return out
    with open(STATE_FILE, newline="") as fh:
        for r in csv.DictReader(fh):
            modal = _f(r["modal"])
            if modal is None:
                continue
            out.setdefault((r["crop"], r["state"]), {})[r["date"]] = {
                "date": r["date"], "modal": modal, "min": None, "max": None, "source": "state_average",
                "source_note": r.get("source", ""), "note": ""}
    return out


@lru_cache(maxsize=1)
def _national() -> dict:
    out = {}
    if not NATIONAL_FILE.exists():
        return out
    with open(NATIONAL_FILE, newline="") as fh:
        for r in csv.DictReader(fh):
            modal = _f(r["modal"])
            if modal is not None:
                out.setdefault(r["crop"], []).append({"date": r["date"], "modal": modal, "label": r["label"]})
    for v in out.values():
        v.sort(key=lambda x: x["date"])
    return out


def state_of(market: str) -> Optional[str]:
    from app.mock_data.locations import MARKET_BY_NAME
    m = MARKET_BY_NAME.get(market)
    return m["state"] if m else None


def available_series() -> list:
    return [{"crop": c, "market": m} for (c, m) in sorted(_bundled())]


def _nearest_before(pts, target: dt.date, tol_days: int):
    """Latest point on/before target and within tol_days of it (no extrapolation)."""
    best = None
    for p in pts:
        d = dt.date.fromisoformat(p["date"])
        if d <= target and (target - d).days <= tol_days:
            best = p
    return best


def _national_same_day(crop: str, last_d: dt.date):
    """National wholesale price on the same calendar date in earlier years (from the published trend files)."""
    rows = _national().get(crop)
    if not rows:
        return None
    return [{"date": r["date"], "modal": r["modal"], "label": r["label"]} for r in rows]


def _pct(new, old):
    return round((new - old) / old * 100, 1) if old else None


def build_series(crop: str, market: str, live_rows=(), window: Optional[int] = None, today: Optional[dt.date] = None,
                 scope: str = "auto"):
    """Return the response dict. live_rows: objects with date/modal_price/min_price/max_price.

    scope "market": this market's own recorded prices. "state": the state-wide daily average (one price per
    day for the whole state, weighted by arrivals). "auto": state when available (it is the more current),
    else market. The response always says which one it is and which others exist.
    """
    today = today or dt.date.today()
    state = state_of(market)
    state_pts = _state_series().get((crop, state)) if state else None
    market_pts = dict(_bundled().get((crop, market), {}))
    for r in live_rows:
        modal = _f(r.modal_price)
        if modal is None:
            continue
        market_pts[r.date] = {"date": r.date, "modal": modal, "min": _f(r.min_price), "max": _f(r.max_price),
                              "source": "live", "source_note": "live", "note": ""}
    if scope == "auto":
        scope = "state" if state_pts else "market"
    if scope == "state" and not state_pts:
        scope = "market"
    merged = dict(state_pts) if scope == "state" else market_pts
    if not merged:
        return {"available": False, "crop": crop, "market": market, "reason": "no_recorded_prices",
                "message": "No recorded prices for this crop and market yet."}

    allpts = sorted(merged.values(), key=lambda p: p["date"])
    last = allpts[-1]
    last_d = dt.date.fromisoformat(last["date"])
    if window:
        start = last_d - dt.timedelta(days=window)
        pts = [p for p in allpts if dt.date.fromisoformat(p["date"]) >= start]
    else:
        pts = allpts

    prices = [p["modal"] for p in pts]
    hi = max(pts, key=lambda p: p["modal"])
    lo = min(pts, key=lambda p: p["modal"])

    gaps, prev = [], None
    for p in pts:
        d = dt.date.fromisoformat(p["date"])
        if prev and (d - prev).days > GAP_DAYS:
            gaps.append({"from": prev.isoformat(), "to": d.isoformat(), "days": (d - prev).days})
        prev = d

    # Trend uses only the newest unbroken run of records, so a long gap is never read as a price move.
    run = pts
    if gaps:
        cut = gaps[-1]["to"]
        run = [p for p in pts if p["date"] >= cut]
    if len(run) >= 4:
        n = min(5, max(1, len(run) // 3))
        early, late = statistics.median(p["modal"] for p in run[:n]), statistics.median(p["modal"] for p in run[-n:])
        pct = _pct(late, early)
        direction = "rising" if pct > STEADY_PCT else "falling" if pct < -STEADY_PCT else "steady"
    else:
        pct, direction = None, "unknown"
    trend = {"direction": direction, "change_pct": pct, "from_date": run[0]["date"], "to_date": run[-1]["date"],
             "n_points": len(run), "after_gap": bool(gaps)}

    def change(days, tol):
        ref = _nearest_before(allpts[:-1], last_d - dt.timedelta(days=days), tol)
        return {"days": days, "from_date": ref["date"], "from_price": ref["modal"],
                "pct": _pct(last["modal"], ref["modal"])} if ref else None

    # same-month average per calendar month across all recorded years (seasonality hint, recorded data only)
    by_month = {}
    for p in allpts:
        by_month.setdefault(int(p["date"][5:7]), []).append(p["modal"])
    monthly = [{"month": m, "avg": round(statistics.mean(v), 1), "n": len(v)} for m, v in sorted(by_month.items()) if len(v) >= 5]

    return {
        "available": True, "crop": crop, "market": market, "unit": "INR/quintal",
        "scope": scope, "state": state,
        "scopes_available": [x for x, ok in (("state", bool(state_pts)), ("market", bool(market_pts))) if ok],
        "national": _national_same_day(crop, last_d),
        "window_days": window, "points": [{"date": p["date"], "modal": p["modal"], "min": p["min"],
                                           "max": p["max"], "source": p["source"]} for p in pts],
        "summary": {
            "latest": {"date": last["date"], "modal": last["modal"], "min": last["min"], "max": last["max"],
                       "source": last["source"], "note": last["note"], "age_days": (today - last_d).days},
            "trend": trend,
            "change_7d": change(7, 4), "change_30d": change(30, 10),
            "high": {"date": hi["date"], "modal": hi["modal"]}, "low": {"date": lo["date"], "modal": lo["modal"]},
            "average": round(statistics.mean(prices), 1), "n_points": len(pts),
            "first_date": pts[0]["date"],
        },
        "gaps": gaps, "monthly_average": monthly,
        "sources": sorted({p["source"] for p in pts}),
        "notes": ["Recorded mandi prices only; stretches with no record are left blank, not estimated.",
                  "Prices are modal prices in INR per quintal (100 kg)."],
    }
