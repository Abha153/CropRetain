"""Past-price series: recorded data only, gaps stay gaps, trend never spans a gap."""
import datetime as dt
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services import past_prices as P


def _use(monkeypatch, series):
    monkeypatch.setattr(P, "_bundled", lambda: series)
    monkeypatch.setattr(P, "_state_series", lambda: {})


def _pts(start, prices, step=1, source="history"):
    d0 = dt.date.fromisoformat(start)
    return {(d0 + dt.timedelta(days=i * step)).isoformat(): {
        "date": (d0 + dt.timedelta(days=i * step)).isoformat(), "modal": p, "min": None, "max": None,
        "source": source, "source_note": source, "note": ""} for i, p in enumerate(prices)}


def test_unknown_series_is_unavailable(monkeypatch):
    _use(monkeypatch, {})
    r = P.build_series("Onion", "Nowhere")
    assert r["available"] is False and r["reason"] == "no_recorded_prices"


def test_rising_series_and_stats(monkeypatch):
    _use(monkeypatch, {("Onion", "Pune"): _pts("2025-01-01", [1000 + 50 * i for i in range(20)])})
    r = P.build_series("Onion", "Pune", today=dt.date(2025, 1, 21))
    s = r["summary"]
    assert s["trend"]["direction"] == "rising" and s["trend"]["change_pct"] > 3
    assert s["latest"]["modal"] == 1950 and s["latest"]["age_days"] == 1
    assert s["high"]["modal"] == 1950 and s["low"]["modal"] == 1000 and r["gaps"] == []


def test_gap_is_reported_and_trend_ignores_it(monkeypatch):
    series = _pts("2025-01-01", [2000] * 10)
    series.update(_pts("2026-10-18", [900], source="snapshot"))
    _use(monkeypatch, {("Onion", "Pune"): series})
    r = P.build_series("Onion", "Pune")
    assert len(r["gaps"]) == 1 and r["gaps"][0]["days"] > 400
    assert r["summary"]["trend"]["direction"] == "unknown"      # 1 point since the gap: no -55% "trend"
    assert r["summary"]["change_30d"] is None                    # nothing recorded ~30 days before
    assert all(p["modal"] in (2000, 900) for p in r["points"])  # nothing interpolated
    assert len(r["points"]) == 11


def test_window_counts_back_from_latest_record(monkeypatch):
    _use(monkeypatch, {("Onion", "Pune"): _pts("2025-01-01", list(range(1000, 1100)))})
    r = P.build_series("Onion", "Pune", window=30)
    assert r["points"][0]["date"] >= "2025-03-10" and r["points"][-1]["date"] == "2025-04-10"


def test_live_rows_override_bundled_same_day_and_extend(monkeypatch):
    _use(monkeypatch, {("Onion", "Pune"): _pts("2025-01-01", [1000] * 5)})
    live = [SimpleNamespace(date="2025-01-05", modal_price=1500, min_price=1400, max_price=1600),
            SimpleNamespace(date="2025-01-06", modal_price=0, min_price=0, max_price=0)]  # zero is not a price
    r = P.build_series("Onion", "Pune", live_rows=live)
    assert len(r["points"]) == 5
    assert r["points"][-1]["modal"] == 1500 and r["points"][-1]["source"] == "live"


def test_bundled_file_is_sane_and_has_no_demo_rows():
    P._bundled.cache_clear()
    series = P._bundled()
    assert series, "app/data/past_prices.csv missing or empty"
    for (crop, market), rows in series.items():
        for r in rows.values():
            assert r["modal"] > 0 and r["source"] in ("history", "snapshot")


def test_builder_accepts_chattisgarh_spelling_and_district_fallback(tmp_path):
    import pandas as pd
    from scripts import build_past_prices as B
    h = tmp_path / "h.csv"
    pd.DataFrame({"state": ["Maharashtra"], "market": ["Pune"], "commodity": ["Onion"],
                  "date": ["2025-01-01"], "modal_price": [1200.0]}).to_csv(h, index=False)
    snap = tmp_path / "s.csv"
    pd.DataFrame({
        "State": ["Chattisgarh", "Chattisgarh", "Maharashtra"],
        "District": ["Raipur", "Raipur", "Pune"],
        "Market": ["Kharora APMC", "Neora APMC", "APMC Pune "],
        "Commodity": ["Paddy(Common)", "Paddy(Common)", "Onion"],
        "Variety": ["x"] * 3, "Grade": ["FAQ"] * 3, "Arrival_Date": ["18/10/2026"] * 3,
        "Min_x0020_Price": [2100, 2200, 1000], "Max_x0020_Price": [2200, 2300, 4800],
        "Modal_x0020_Price": [2150, 2190, 2900]}).to_csv(snap, index=False)
    out = B.build(h, snap, "snapshot_2026-10-18")
    cg = out[(out.market == "Raipur") & (out.crop == "Paddy (Rice)")].iloc[0]
    assert cg["modal"] == 2170 and "Kharora APMC" in cg["note"] and "Neora APMC" in cg["note"]
    pune = out[(out.market == "Pune") & (out.date == "2026-10-18")].iloc[0]
    assert pune["modal"] == 2900 and (pd.isna(pune["note"]) or pune["note"] == "")
    assert len(out[out.market == "Pune"]) == 2


def test_state_scope_is_default_and_market_scope_still_available(monkeypatch):
    _use(monkeypatch, {("Onion", "Pune"): _pts("2025-01-01", [1000] * 5)})
    st = _pts("2026-09-01", [2000 + 20 * i for i in range(40)], source="state_average")
    monkeypatch.setattr(P, "_state_series", lambda: {("Onion", "Maharashtra"): st})
    r = P.build_series("Onion", "Pune")
    assert r["scope"] == "state" and r["state"] == "Maharashtra" and r["scopes_available"] == ["state", "market"]
    assert r["points"][-1]["modal"] == 2780 and r["summary"]["trend"]["direction"] == "rising"
    m = P.build_series("Onion", "Pune", scope="market")
    assert m["scope"] == "market" and len(m["points"]) == 5
    # a market with no state data falls back to its own history
    assert P.build_series("Onion", "Pune", scope="state")["scope"] == "state"
    monkeypatch.setattr(P, "_state_series", lambda: {})
    assert P.build_series("Onion", "Pune", scope="state")["scope"] == "market"


def test_builder_state_report_and_national_files(tmp_path):
    import pandas as pd
    from scripts import build_past_prices as B
    rep = tmp_path / "r.csv"
    rep.write_text(
        ",,,,All Type of Report,,,\n"
        "State/UT,Commodity Group,Commodity,Date,Arrival Quantity,Arrival Unit,Modal Price,Price Unit\n"
        "Chattisgarh,Vegetables,Onion,17-10-2023,207.2,Metric Tonnes,2038.61,Rs./Quintal\n"
        "Chattisgarh,Vegetables,Coriander(Leaves),17-10-2023,40,Bundle,10000,Rs./Bundle\n"
        "Maharashtra,Vegetables,Tomato,18-10-2023,5,Metric Tonnes,800,Rs./Quintal\n"
        "Note:,,,,,,,\n")
    st = B.build_state(rep)
    assert sorted(st["state"]) == ["Chhattisgarh", "Maharashtra"] and set(st["crop"]) == {"Onion", "Tomato"}
    nat = tmp_path / "n.csv"
    nat.write_text('"Commodity","ONE WEEK-Price as on 16-10-2026","ONE WEEK-Prices as on 09-10-2026","ONE YEAR-Prices as on 16-10-2025","% Variation Over-1 Week"\n'
                   '"Paddy","2618.38","2674.36","2356.48","-2.09"\n"Lentil","1","2","3","0"\n')
    n = B.build_national([nat])
    assert set(n["crop"]) == {"Paddy (Rice)"} and list(n["label"]) == ["Latest", "1 week earlier", "1 year earlier"]


def test_bundled_state_and_national_files_are_sane():
    P._state_series.cache_clear(); P._national.cache_clear()
    st = P._state_series()
    assert ("Onion", "Chhattisgarh") in st and ("Tomato", "Maharashtra") in st
    assert all(r["modal"] > 0 for rows in st.values() for r in rows.values())
    nat = P._national()
    assert nat["Onion"][-1]["label"] == "Latest" and nat["Onion"][-1]["date"] == "2026-10-16"
