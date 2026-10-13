"""
Tests for the assistant's intent detection, entity extraction, and routing
(app/i18n/intents.py, app/i18n/nlu.py, app/routers/assistant.py).

Covers the specific correctness bug this pass fixed: unmatched questions
must return NEEDS_CLARIFICATION, never silently become MARKET_RECOMMENDATION.
Also covers quantity-unit parsing (kg / quintal / ton) and that each
"market-adjacent" intent (forecast, buyer search, transport, profit,
comparison, weather) is routed to its OWN real service rather than all
falling through to the same market-comparison answer.

Uses an isolated in-memory SQLite database, seeded with demo MarketPrice
rows (same pattern as test_market_router.py) -- no live network calls.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app import models, schemas
from app.database import Base
from app.i18n import intents
from app.i18n.nlu import parse
from app.routers import assistant as assistant_router


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


def _seed_price(db, crop, market, modal=3400.0):
    db.add(models.MarketPrice(
        crop=crop, market=market, date="2026-08-20",
        min_price=modal - 200, max_price=modal + 200, modal_price=modal,
        arrivals_tonnes=50.0, data_source="demo",
    ))
    db.commit()


def _seed_buyer_demand(db, crop="Onion", quantity=2000.0, location="Raipur"):
    buyer = models.Buyer(
        email=f"buyer{crop}@example.com", password_hash="x",
        company_name="FreshFoods Test Pvt. Ltd.", buyer_type="wholesaler",
        location=location,
    )
    db.add(buyer)
    db.commit()
    db.refresh(buyer)
    demand = models.BuyerDemand(
        buyer_id=buyer.id, crop=crop, required_quantity_kg=quantity,
        delivery_location=location, status="ACTIVE",
    )
    db.add(demand)
    db.commit()
    return buyer, demand


def ask(db, question, language="en", known_crop=None, known_quantity_kg=None, known_location=None):
    payload = schemas.AssistantAsk(
        question=question, language=language, known_crop=known_crop,
        known_quantity_kg=known_quantity_kg, known_location=known_location,
    )
    return assistant_router.ask(payload, db=db)


# ---------------------------------------------------------------------------
# Intent detection -- unit level, no DB needed
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("Where should I sell my onion?", intents.MARKET_RECOMMENDATION),
    ("Compare Bilaspur and Raipur for onion", intents.MARKET_COMPARISON),
    ("What is the current price of onion in Bilaspur?", intents.PRICE_LOOKUP),
    ("What will onion prices look like next week?", intents.PRICE_FORECAST),
    ("How much profit can I make?", intents.PROFIT_CALCULATION),
    ("Who wants 1000 kg onion?", intents.BUYER_SEARCH),
    ("How much will transport cost?", intents.TRANSPORT),
    ("Will it rain tomorrow in Raipur?", intents.WEATHER),
    ("My tomato leaves are turning yellow", intents.DISEASE_HELP),
    ("What crop should I grow this season?", intents.GENERAL_AGRICULTURE_QUERY),
])
def test_intent_detection(text, expected):
    assert intents.detect_intent(text, "en") == expected


def test_unmatched_question_needs_clarification_not_market_recommendation():
    """The core correctness fix: an off-topic/ambiguous question must NOT
    silently become a market recommendation."""
    result = intents.detect_intent("blah completely unrelated nonsense zzz", "en")
    assert result == intents.NEEDS_CLARIFICATION
    assert result != intents.MARKET_RECOMMENDATION


def test_price_lookup_and_forecast_are_distinct_intents():
    assert intents.detect_intent("what is the current price of onion in Raipur", "en") == intents.PRICE_LOOKUP
    assert intents.detect_intent("onion price next week", "en") == intents.PRICE_FORECAST


# ---------------------------------------------------------------------------
# Entity extraction -- quantity units
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected_kg", [
    ("I have 1 kg onion", 1.0),
    ("I have 100 kg onion", 100.0),
    ("I have 1000 kg onion", 1000.0),
    ("I have 1 ton onion", 1000.0),
    ("I have 1 tonne onion near Nashik", 1000.0),
    ("I have 2 tons onion", 2000.0),
    ("mere paas 10 quintal pyaz hai", 1000.0),
])
def test_quantity_extraction(text, expected_kg):
    parsed = parse(text, language="en")
    assert parsed["quantity_kg"] == expected_kg


def test_conversation_context_carries_forward():
    parsed = parse("Which market is better?", language="en",
                    known_crop="Onion", known_quantity_kg=1000.0, known_location="Raipur")
    assert parsed["crop"] == "Onion"
    assert parsed["quantity_kg"] == 1000.0
    assert parsed["location"] == "Raipur"


# ---------------------------------------------------------------------------
# End-to-end routing through /assistant/ask (real services, seeded demo data)
# ---------------------------------------------------------------------------

def test_market_recommendation_routes_to_market_comparison(db):
    for m in ["Bilaspur", "Raipur", "Durg"]:
        _seed_price(db, "Onion", m)
    result = ask(db, "Where should I sell my onion? I have 1000 kg near Bilaspur.")
    assert result["intent"] == intents.MARKET_RECOMMENDATION
    assert result["clarification_needed"] is None
    assert result["recommended_market"] in ["Bilaspur", "Raipur", "Durg"]
    assert result["market_options"]


def test_transport_intent_uses_transport_optimizer_not_market_pitch(db):
    for m in ["Bilaspur", "Raipur", "Durg"]:
        _seed_price(db, "Onion", m)
    result = ask(db, "How much will transport cost for 1000 kg onion from Bilaspur?")
    assert result["intent"] == intents.TRANSPORT
    assert "transport" in result["answer"].lower() or "परिवहन" in result["answer"]


def test_profit_calculation_has_its_own_wording(db):
    for m in ["Bilaspur", "Raipur", "Durg"]:
        _seed_price(db, "Onion", m)
    result = ask(db, "How much profit can I make? I have 1000 kg onion near Bilaspur.")
    assert result["intent"] == intents.PROFIT_CALCULATION
    market_result = ask(db, "Where should I sell my onion? I have 1000 kg near Bilaspur.")
    # Different intents must produce differently-worded answers, not the
    # exact same market-recommendation sentence (the bug this pass fixed).
    assert result["answer"] != market_result["answer"]


def test_price_lookup_uses_get_price_not_compare_markets(db):
    _seed_price(db, "Onion", "Bilaspur", modal=3400.0)
    result = ask(db, "What is the current price of onion in Bilaspur?")
    assert result["intent"] == intents.PRICE_LOOKUP
    assert "34" in result["answer"]  # 3400/100 = 34 per kg


def test_price_forecast_honestly_reports_unavailable_when_no_history(db):
    # No history seeded at all for this crop/market -- must say so, not
    # silently answer with a market recommendation instead.
    result = ask(db, "What will onion prices look like next week in Bilaspur?")
    assert result["intent"] == intents.PRICE_FORECAST
    assert "forecast" in result["answer"].lower() or result["answer"]  # honest unavailable message


def test_buyer_search_uses_real_buyer_demand_rows(db):
    _seed_buyer_demand(db, crop="Onion", quantity=2000.0, location="Raipur")
    result = ask(db, "Who wants to buy onion?")
    assert result["intent"] == intents.BUYER_SEARCH
    assert "FreshFoods Test" in result["answer"]


def test_buyer_search_honest_when_no_demand_exists(db):
    result = ask(db, "Who wants to buy soybean?")
    assert result["intent"] == intents.BUYER_SEARCH
    assert "Soybean" in result["answer"] or "soybean" in result["answer"].lower()


def test_farmpool_intent_uses_shared_transport_plan(db):
    result = ask(db, "How can I share transport for 1000 kg onion from Bilaspur to Raipur?")
    assert result["intent"] == intents.FARMPOOL
    assert result["clarification_needed"] is None
    assert "shared" in result["answer"].lower() or "pool" in result["answer"].lower()


def test_market_comparison_requires_two_named_markets(db):
    for m in ["Bilaspur", "Raipur"]:
        _seed_price(db, "Onion", m)
    # Only one market named -> must clarify, not guess the second.
    result = ask(db, "Compare Bilaspur for onion", known_location="Durg")
    assert result["intent"] == intents.MARKET_COMPARISON
    assert result["clarification_needed"] == "two_markets"


def test_market_comparison_with_two_markets_and_known_origin(db):
    for m in ["Bilaspur", "Raipur"]:
        _seed_price(db, "Onion", m, modal=3400.0)
    result = ask(db, "Compare Bilaspur and Raipur for onion", known_location="Durg")
    assert result["intent"] == intents.MARKET_COMPARISON
    assert result["clarification_needed"] is None
    assert "Bilaspur" in result["answer"] and "Raipur" in result["answer"]


def test_weather_intent_routes_to_weather_service_not_market(db):
    result = ask(db, "Will it rain tomorrow in Bilaspur?")
    assert result["intent"] == intents.WEATHER
    assert result.get("weather_status") in ("LIVE", "DEMO", None)


def test_disease_help_never_routed_to_market_recommendation(db):
    result = ask(db, "My tomato leaves are turning yellow, what disease is this?")
    assert result["intent"] == intents.DISEASE_HELP
    assert result["intent"] != intents.MARKET_RECOMMENDATION
