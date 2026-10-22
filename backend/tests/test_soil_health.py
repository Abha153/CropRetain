"""
Tests for services/soil_health.py and POST /soil/health-check.

Pins down: thresholds match the cited TNAU chart exactly (incl. boundaries),
chart inconsistencies are flagged rather than guessed, missing inputs are
reported as not_provided, no fertiliser dose is ever produced, and invalid
input is rejected.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

from app.services.soil_health import rate_soil_health, SOURCES, SOURCE_ID


def _rating(result, parameter):
    return next(r for r in result["ratings"] if r["parameter"] == parameter)


@pytest.mark.parametrize("param,value,expected", [
    ("nitrogen", 239.9, "low"), ("nitrogen", 240, "medium"), ("nitrogen", 480, "medium"), ("nitrogen", 480.1, "high"),
    ("phosphorus", 10.9, "low"), ("phosphorus", 11, "medium"), ("phosphorus", 22, "medium"), ("phosphorus", 22.1, "high"),
    ("potassium", 109.9, "low"), ("potassium", 110, "medium"), ("potassium", 280, "medium"), ("potassium", 280.1, "high"),
    ("organic_carbon", 0.49, "low"), ("organic_carbon", 0.5, "medium"), ("organic_carbon", 0.75, "medium"), ("organic_carbon", 0.76, "high"),
])
def test_nutrient_boundaries_match_cited_chart(param, value, expected):
    assert _rating(rate_soil_health(**{param: value}), param)["rating"] == expected


@pytest.mark.parametrize("ph,expected", [
    (5.9, "acid"), (6.0, "normal_to_saline"), (8.5, "normal_to_saline"),
    (8.6, "unclassified"), (8.89, "unclassified"),
    (8.9, "tending_alkaline"), (9.0, "tending_alkaline"), (9.1, "alkaline"),
])
def test_ph_classes_and_chart_gap(ph, expected):
    assert _rating(rate_soil_health(ph=ph), "ph")["rating"] == expected


@pytest.mark.parametrize("ec,expected", [
    (0.9, "normal"), (1, "critical_for_germination"), (1.9, "critical_for_germination"),
    (2, "critical_for_sensitive_crops"), (4, "critical_for_sensitive_crops"),
    (4.1, "injurious_to_most_crops"),
])
def test_ec_classes(ec, expected):
    assert _rating(rate_soil_health(ec=ec), "ec")["rating"] == expected


def test_interpreted_flags_are_set_where_chart_is_ambiguous():
    r = rate_soil_health(organic_carbon=0.6, nitrogen=300, ec=1.5)
    assert _rating(r, "organic_carbon")["interpreted"] is True
    assert "7.5" in _rating(r, "organic_carbon")["note"]
    assert _rating(r, "ec")["interpreted"] is True
    assert _rating(r, "nitrogen")["interpreted"] is False


def test_missing_values_are_reported_not_estimated():
    r = rate_soil_health(nitrogen=100)
    assert [x["parameter"] for x in r["ratings"]] == ["nitrogen"]
    assert set(r["not_provided"]) == {"organic_carbon", "phosphorus", "potassium", "ph", "ec"}


def test_needs_attention_lists_only_concerning_ratings():
    r = rate_soil_health(nitrogen=100, phosphorus=15, potassium=300, ph=7.0, ec=0.5)
    assert r["needs_attention"] == ["nitrogen"]


def test_every_rating_cites_a_known_source_and_no_dose_is_given():
    r = rate_soil_health(organic_carbon=0.6, nitrogen=100, phosphorus=5, potassium=50, ph=5.0, ec=3)
    assert SOURCE_ID in SOURCES
    assert all(x["source"] == SOURCE_ID for x in r["ratings"])
    assert r["sources"][0]["id"] == SOURCE_ID
    flat = str(r).lower()
    assert "dose" not in flat and "kg/acre" not in flat


def test_nothing_provided_is_unavailable():
    r = rate_soil_health()
    assert r["data_quality"] == "UNAVAILABLE" and r["ratings"] == [] and r["sources"] == []


# ---------------------------------------------------------------- router ----
# These need the app's dependencies (fastapi etc.); no DB is touched.

def _client():
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


def test_endpoint_rates_values_and_flags_limitation():
    r = _client().post("/soil/health-check", json={"nitrogen": 200, "ph": 7.2})
    assert r.status_code == 200
    body = r.json()
    assert body["method"] == "RATING_CHART_LOOKUP"
    assert {x["parameter"]: x["rating"] for x in body["ratings"]} == {"nitrogen": "low", "ph": "normal_to_saline"}
    assert "Chhattisgarh" in body["regional_limitation"]


def test_endpoint_rejects_empty_input():
    r = _client().post("/soil/health-check", json={})
    assert r.status_code == 400 and r.json()["code"] == "SOIL_HEALTH_NO_INPUT"


@pytest.mark.parametrize("payload", [{"ph": 15}, {"nitrogen": -1}, {"organic_carbon": 101}, {"ec": -0.1}])
def test_endpoint_pydantic_bounds(payload):
    assert _client().post("/soil/health-check", json=payload).status_code == 422
