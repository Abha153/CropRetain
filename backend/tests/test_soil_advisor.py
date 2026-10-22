"""
Tests for the Soil Advisor (services/soil_advisor.py, services/soil_crop_rules.py,
routers/soil.py).

What they pin down:
  * the engine only uses cited rules, never invents a threshold;
  * crops with no cited rules are UNAVAILABLE, not guessed;
  * disagreeing sources are surfaced, not silently merged;
  * invalid / missing input is rejected safely;
  * every money figure equals what the EXISTING net_profit_breakdown /
    market-comparison logic produces (no parallel calculator), and the
    price label is DEMO when only seeded demo data backs it.
No network: mandi_directory.fetch_price_result is stubbed to always fail so
the market comparison falls back to the seeded demo rows.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models
from app.database import Base, get_db
from app.mock_data.crops import crop_names
from app.mock_data.locations import MARKETS, distance_between
from app.services import mandi_directory
from app.services import soil_advisor
from app.services.soil_crop_rules import CROP_RULES, SOURCES
from app.services.transport_optimizer import net_profit_breakdown


# ---------------------------------------------------------------- engine ----

def _by_crop(result):
    return {r["crop"]: r for r in result["ranked"]}


def test_every_claim_cites_a_known_source():
    for crop, rules in CROP_RULES.items():
        for group in ("ph", "texture", "season", "water"):
            for claim in rules[group]:
                assert claim["source"] in SOURCES, (crop, group, claim)
    for src in SOURCES.values():
        assert src["url"].startswith("https://")


def test_only_cited_crops_are_assessed_rest_are_unavailable():
    res = soil_advisor.evaluate_all(soil_ph=6.2, soil_texture="loam", season="kharif", irrigation=None)
    ranked = {r["crop"] for r in res["ranked"]}
    unavailable = {u["crop"] for u in res["unavailable"]}
    assert ranked == set(CROP_RULES)
    assert ranked | unavailable == set(crop_names())
    assert all(u["data_quality"] == "UNAVAILABLE" and u["reason_code"] == "NO_CITED_RULES"
               for u in res["unavailable"])


def test_loam_kharif_ph_6_5_favours_soybean_over_chana():
    res = soil_advisor.evaluate_all(soil_ph=6.5, soil_texture="loam", season="kharif", irrigation=None)
    crops = _by_crop(res)
    assert crops["Soybean"]["checks_passed"] == 3 == crops["Soybean"]["checks_assessed"]
    # chana: pH 6.5 and loam fit, but season kharif is not rabi
    assert crops["Chana (Gram)"]["checks_passed"] == 2
    assert res["ranked"][0]["crop"] == "Soybean"


def test_rabi_flips_ranking_to_chana():
    res = soil_advisor.evaluate_all(soil_ph=7.0, soil_texture="loam", season="rabi", irrigation=None)
    assert res["ranked"][0]["crop"] == "Chana (Gram)"
    assert _by_crop(res)["Chana (Gram)"]["checks_passed"] == 3


def test_ph_outside_every_cited_range_is_a_mismatch_with_reported_ranges():
    r = soil_advisor.evaluate_crop("Paddy (Rice)", soil_ph=8.5, soil_texture=None, season=None, irrigation=None)
    ph = r["checks"][0]
    assert ph["status"] == "mismatch"
    assert all(rng["within"] is False for rng in ph["ranges"])
    assert {"code": "PH_OUTSIDE_REPORTED"} in r["warnings"]


def test_disagreeing_sources_are_surfaced_not_merged():
    # Soybean pH 5.8: inside NSDC's 5.5-6.5 'optimal' but outside the 6.0-7.5 ranges.
    r = soil_advisor.evaluate_crop("Soybean", soil_ph=5.8, soil_texture=None, season=None, irrigation=None)
    ph = r["checks"][0]
    assert ph["status"] == "match" and ph["sources_disagree"] is True
    assert {"code": "PH_SOURCES_DISAGREE"} in r["warnings"]


def test_paddy_has_no_season_rule_and_says_so():
    r = soil_advisor.evaluate_crop("Paddy (Rice)", soil_ph=6.0, soil_texture=None, season="kharif", irrigation=None)
    assert "season" in r["not_assessed_factors"]
    assert [c["factor"] for c in r["checks"]] == ["ph"]


def test_interpreted_texture_claim_is_flagged():
    r = soil_advisor.evaluate_crop("Soybean", soil_ph=None, soil_texture="clay", season=None, irrigation=None)
    support = r["checks"][0]["supporting"]
    assert support and all(s["interpreted"] for s in support)


def test_irrigation_alone_does_not_assess_anything():
    r = soil_advisor.evaluate_crop("Paddy (Rice)", soil_ph=None, soil_texture=None, season=None, irrigation="rainfed")
    assert r["assessable"] is False and r["reason_code"] == "NO_MATCHING_INPUT"
    assert r["notes"] and r["notes"][0]["code"] == "paddy_high_water"


def test_water_note_only_when_irrigation_not_assured():
    rainfed = soil_advisor.evaluate_crop("Paddy (Rice)", soil_ph=6.0, soil_texture=None, season=None, irrigation="rainfed")
    assured = soil_advisor.evaluate_crop("Paddy (Rice)", soil_ph=6.0, soil_texture=None, season=None, irrigation="assured")
    assert rainfed["notes"] and not assured["notes"]


# ---------------------------------------------------------------- router ----

@pytest.fixture()
def db():
    from sqlalchemy.pool import StaticPool
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


@pytest.fixture()
def client(db, monkeypatch):
    from app.main import app

    def _override():
        yield db

    # No network: every live lookup fails -> existing demo-fallback path.
    monkeypatch.setattr(mandi_directory, "fetch_price_result",
                        lambda crop, market, **k: {"status": "error", "data": None})
    app.dependency_overrides[get_db] = _override
    yield TestClient(app)
    app.dependency_overrides.pop(get_db, None)


def _seed_demo(db, crop, price_per_quintal_by_market):
    for market, price in price_per_quintal_by_market.items():
        db.add(models.MarketPrice(
            crop=crop, market=market, date="2026-10-01",
            min_price=price - 100, max_price=price + 100, modal_price=price,
            arrivals_tonnes=40.0, data_source="demo",
        ))
    db.commit()


def test_options_endpoint_lists_allowed_values(client):
    body = client.get("/soil/options").json()
    assert "loam" in body["soil_texture"] and "kharif" in body["season"]
    assert "Bilaspur" in body["locations"]


def test_rejects_empty_input(client):
    r = client.post("/soil/advise", json={})
    assert r.status_code == 400 and r.json()["code"] == "SOIL_NO_INPUT"


@pytest.mark.parametrize("payload,code", [
    ({"soil_texture": "moon_dust"}, "SOIL_INVALID_TEXTURE"),
    ({"soil_ph": 6.0, "season": "monsoon"}, "SOIL_INVALID_SEASON"),
    ({"soil_ph": 6.0, "irrigation": "flood"}, "SOIL_INVALID_IRRIGATION"),
    ({"soil_ph": 6.0, "quantity_kg": 500}, "SOIL_FINANCIAL_INPUT_INCOMPLETE"),
    ({"soil_ph": 6.0, "location": "Bilaspur"}, "SOIL_FINANCIAL_INPUT_INCOMPLETE"),
    ({"soil_ph": 6.0, "quantity_kg": 500, "location": "Atlantis"}, "SOIL_UNKNOWN_LOCATION"),
])
def test_rejects_invalid_or_incomplete_input(client, payload, code):
    r = client.post("/soil/advise", json=payload)
    assert r.status_code in (400, 422) and r.json()["code"] == code


@pytest.mark.parametrize("payload", [{"soil_ph": 15}, {"soil_ph": -1}, {"soil_ph": 6, "quantity_kg": 0, "location": "Bilaspur"}])
def test_pydantic_bounds(client, payload):
    assert client.post("/soil/advise", json=payload).status_code == 422


def test_without_money_inputs_financial_is_unavailable_not_invented(client):
    body = client.post("/soil/advise", json={"soil_ph": 6.5, "soil_texture": "loam", "season": "kharif"}).json()
    assert body["data_quality"] == "ESTIMATED"
    assert body["recommendations"][0]["crop"] == "Soybean"
    for rec in body["recommendations"]:
        assert rec["financial"] == {
            "data_quality": "UNAVAILABLE", "available": False,
            "reason_code": "QUANTITY_OR_LOCATION_NOT_PROVIDED",
        }
    assert body["inputs"]["provenance"] == "USER_PROVIDED"
    assert body["regional_limitation"] and body["sources"]
    assert {u["crop"] for u in body["unavailable_crops"]} == set(crop_names()) - set(CROP_RULES)


def test_financial_figures_come_from_existing_net_profit_breakdown(client, db):
    prices = {m["name"]: 4200.0 + 40 * i for i, m in enumerate(MARKETS[:6])}
    _seed_demo(db, "Soybean", prices)
    body = client.post("/soil/advise", json={
        "soil_ph": 6.5, "soil_texture": "loam", "season": "kharif",
        "quantity_kg": 2000, "location": "Bilaspur",
    }).json()
    soy = next(r for r in body["recommendations"] if r["crop"] == "Soybean")
    fin = soy["financial"]
    assert fin["available"] and fin["data_quality"] == "ESTIMATED"
    assert fin["price_data_label"] == "DEMO"  # only seeded demo data backs it

    # Recompute independently with the SAME existing function.
    expected = net_profit_breakdown(2000, fin["modal_price_per_kg"],
                                    distance_between("Bilaspur", fin["best_market"]))
    assert fin["estimated_net_return"] == expected["net_profit"]
    assert fin["transport_cost"] == expected["transport_cost"]
    assert fin["mandi_charges"] == expected["mandi_charges"]
    assert fin["handling_cost"] == expected["handling_cost"]
    assert body["financial_assumptions"]


def test_crop_without_any_market_data_gets_unavailable_financial(client, db):
    # Nothing seeded for Chana -> no live, no demo -> must not invent a number.
    body = client.post("/soil/advise", json={
        "soil_ph": 7.0, "soil_texture": "loam", "season": "rabi",
        "quantity_kg": 1000, "location": "Raipur",
    }).json()
    chana = next(r for r in body["recommendations"] if r["crop"] == "Chana (Gram)")
    assert chana["financial"]["available"] is False
    assert chana["financial"]["data_quality"] == "UNAVAILABLE"
    assert "estimated_net_return" not in chana["financial"]


def test_existing_market_compare_still_works(client, db):
    _seed_demo(db, "Soybean", {m["name"]: 4300.0 for m in MARKETS[:6]})
    r = client.get("/market/compare", params={"crop": "Soybean", "quantity_kg": 500, "location": "Bilaspur"})
    assert r.status_code == 200 and r.json()["options"]


# ------------------------------------------- soil-test values in /advise ----

def test_advise_accepts_soil_test_values_alone(client):
    r = client.post("/soil/advise", json={"nitrogen": 200, "phosphorus": 30})
    assert r.status_code == 200
    body = r.json()
    assert {x["parameter"]: x["rating"] for x in body["soil_health"]["ratings"]} == {
        "nitrogen": "low", "phosphorus": "high"}
    assert body["recommendations"] == []          # no pH/texture/season -> no crop checks
    assert any(s["id"] == "tnau_soil_rating_chart" for s in body["sources"])


def test_advise_rates_ph_in_both_crop_checks_and_soil_health(client):
    body = client.post("/soil/advise", json={"soil_ph": 5.0, "nitrogen": 300}).json()
    ph = next(x for x in body["soil_health"]["ratings"] if x["parameter"] == "ph")
    assert ph["rating"] == "acid"
    assert body["recommendations"]               # crop screen still runs on pH


def test_advise_without_test_values_has_null_soil_health(client):
    body = client.post("/soil/advise", json={"soil_texture": "loam"}).json()
    assert body["soil_health"] is None


def test_soil_test_values_do_not_change_crop_checks(client):
    a = client.post("/soil/advise", json={"soil_ph": 6.0, "season": "rabi"}).json()
    b = client.post("/soil/advise", json={"soil_ph": 6.0, "season": "rabi",
                                          "nitrogen": 50, "ec": 5}).json()
    assert a["recommendations"] == b["recommendations"]


@pytest.mark.parametrize("payload", [{"ec": -1}, {"nitrogen": 20000}, {"organic_carbon": 101}])
def test_advise_soil_test_bounds(client, payload):
    assert client.post("/soil/advise", json={"soil_ph": 6.0, **payload}).status_code == 422
