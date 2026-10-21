"""
Statewide history availability vs market-specific forecast availability.

Regression for: Tomato / Bilaspur showed "Historical mandi data is currently unavailable"
in Price Forecast while Past prices charted a Chhattisgarh Tomato series. Both were
"correct" -- they answer different questions -- and these tests pin that difference using
the REAL bundled data files and the REAL shipped model metadata (no network, no fabrication).
"""
import datetime as dt
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import forecast_availability as fa
from app.services import past_prices

TODAY = dt.date(2026, 10, 20)          # fixed so the bundled series' age is deterministic
MODELS = Path(__file__).resolve().parents[1] / "models"


def _meta(name):
    return json.loads((MODELS / name / "metadata.json").read_text(encoding="utf-8"))


# ---- the three sources are genuinely separate ------------------------------------------------

def test_statewide_history_exists_for_tomato_bilaspur():
    h = fa.history_scope("Tomato", "Bilaspur", [], "state", TODAY)
    assert h["available"] is True and h["scope"] == "state"
    assert h["label"] == "Chhattisgarh average"
    assert h["n_points"] > 300 and h["age_days"] <= 7            # recent, statewide
    assert 5 < h["latest_price_per_kg"] < 100                    # per kg, not per quintal


def test_bilaspur_only_history_is_old_and_small():
    h = fa.history_scope("Tomato", "Bilaspur", [], "market", TODAY)
    assert h["available"] is True and h["scope"] == "market"
    assert h["label"] == "Bilaspur"
    assert h["n_points"] < 100 and h["latest_date"] < "2024-01-01"   # recorded in 2023 only
    assert h["age_days"] > 365


def test_requested_scope_never_silently_swapped():
    """A market with no statewide series must not report the market series as 'state'."""
    h = fa.history_scope("Tomato", "Bilaspur", [], "state", TODAY)
    assert h["scope"] == "state"
    assert fa.history_scope("Dragonfruit", "Bilaspur", [], "state", TODAY) == {"available": False}
    assert fa.history_scope("Dragonfruit", "Bilaspur", [], "market", TODAY) == {"available": False}


def test_recorded_history_does_not_make_live_history_sufficient():
    out = fa.build_availability("Tomato", "Bilaspur", live_rows=[], market_ml=None, state_ml=None,
                                min_live_points=4, today=TODAY)
    assert out["recorded_history"]["state"]["available"] is True
    assert out["live_history"] == {"points": 0, "required_for_trend_forecast": 4, "sufficient": False}


def test_live_rows_counted_but_not_demo_inflated():
    rows = [SimpleNamespace(date=f"2026-10-{d:02d}", modal_price=1800.0, min_price=1700.0, max_price=1900.0)
            for d in range(10, 15)]
    out = fa.build_availability("Tomato", "Bilaspur", live_rows=rows, market_ml=None, state_ml=None,
                                min_live_points=4, today=TODAY)
    assert out["live_history"]["points"] == 5 and out["live_history"]["sufficient"] is True


# ---- ML status classification -----------------------------------------------------------------

def test_classify_distinguishes_unsupported_insufficient_and_service_error():
    unsupported = fa.classify_ml({"available": False, "reason": "unsupported_crop", "message": "x"})
    insufficient = fa.classify_ml({"available": False, "reason": "insufficient_history", "message": "y"})
    failed = fa.classify_ml(None)                                # backend fault -> never "no data"
    assert unsupported["status"] == "unsupported_crop"
    assert insufficient["status"] == "insufficient_history"
    assert failed["status"] == "service_error"
    assert len({unsupported["status"], insufficient["status"], failed["status"]}) == 3


def test_classify_available_flags_replay_and_age():
    live = fa.classify_ml({"available": True, "is_historical_replay": False,
                           "forecast": {"as_of_date": "2026-10-17", "history_age_days": 3}})
    replay = fa.classify_ml({"available": True, "is_historical_replay": True,
                             "forecast": {"as_of_date": "2025-06-10", "history_age_days": 496}})
    assert live["status"] == "available" and live["is_historical_replay"] is False
    assert replay["status"] == "available" and replay["is_historical_replay"] is True
    assert replay["history_age_days"] == 496


def test_unmapped_market_has_no_state_model_status():
    out = fa.build_availability("Tomato", "Nowhereville", live_rows=[], market_ml=None, state_ml=None,
                                min_live_points=4, today=TODAY)
    assert out["state"] is None and out["state_ml"]["status"] == "no_state"
    assert out["recorded_history"]["state"] == {"available": False}


# ---- shipped model coverage: statewide history != market-level forecast ----------------------

def test_market_model_excludes_tomato_but_statewide_model_covers_it():
    market_model, state_model = _meta("price_forecast"), _meta("price_forecast_state")
    assert "Tomato" not in market_model["commodity_idx"] and "Tomato" in market_model["excluded_crops"]
    assert "Tomato" in state_model["commodity_idx"]


def test_market_model_prediction_for_tomato_is_refused_not_invented():
    pytest.importorskip("sklearn")
    pytest.importorskip("pandas")
    from app.services.price_forecast import inference as inf
    hist = [{"date": (TODAY - dt.timedelta(days=i)).isoformat(), "modal_price": 1800.0} for i in range(30, 0, -1)]
    with pytest.raises(inf.ForecastError) as e:
        inf.predict(hist, "Tomato", "Bilaspur", today=TODAY)
    assert e.value.code == "unsupported_crop"
    # ...and that real refusal is what the availability report surfaces:
    status = fa.classify_ml({"available": False, "reason": e.value.code, "message": e.value.message})
    assert status["status"] == "unsupported_crop"


def test_statewide_model_can_forecast_tomato_when_history_is_fresh():
    """Statewide history for Chhattisgarh Tomato feeds the statewide model (a statewide number, not Bilaspur's)."""
    pytest.importorskip("sklearn")
    pytest.importorskip("pandas")
    from app.services.price_forecast import inference as inf
    series = past_prices._state_series()[("Tomato", "Chhattisgarh")]
    hist = [{"date": d, "modal_price": r["modal"]} for d, r in sorted(series.items())]
    arts = inf.load_artifacts(MODELS / "price_forecast_state")
    # evaluate as of the series' own last day so the test does not expire as the calendar moves
    as_of = dt.date.fromisoformat(hist[-1]["date"])
    fc = inf.predict(hist, "Tomato", "Chhattisgarh (state average)", today=as_of, artifacts=arts)
    assert fc["predicted_price_low"] <= fc["predicted_price"] <= fc["predicted_price_high"]
    assert fc["unit"].startswith("INR per quintal") and 0 < fc["predicted_price_per_kg"] < 200
