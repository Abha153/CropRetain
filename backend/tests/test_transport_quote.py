"""
Tests for the transporter quote -> counter-offer -> accept/reject ->
agreed-price flow on TransportRequest (app/routers/transport.py).

There is no transporter login in this codebase (only farmer/buyer/admin
roles) -- see the note on TransportRequest.quote_status in models.py.
The quote is recorded by the farmer who owns the request, and every
mutating action is gated by that same ownership check, which is what
these tests exercise.

Run: pytest backend/tests/test_transport_quote.py -v
"""
import os
import sys

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import models, schemas
from app.database import Base
from app.routers import transport as transport_router


@pytest.fixture()
def db():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    yield session
    session.close()


def _make_farmer(db, name="Farmer", email="farmer@example.com"):
    f = models.Farmer(name=name, email=email, password_hash="x", location="Bilaspur")
    db.add(f)
    db.flush()
    return f


def _make_request(db, farmer, estimated_cost=1500.0):
    r = models.TransportRequest(
        farmer_id=farmer.id, pickup_location="Bilaspur", destination="Raipur",
        estimated_cost=estimated_cost,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


# ─── happy path: estimate -> quote -> accept -> agreed price ────────────────

def test_new_request_starts_awaiting_quote(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    assert r.quote_status == "AWAITING_QUOTE"
    assert r.quoted_price is None
    assert r.agreed_price is None


def test_owner_can_submit_quote_and_timestamp_is_server_generated(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)

    result = transport_router.submit_quote(
        r.id, schemas.TransportQuoteSubmit(quoted_price=1450.0), farmer, db
    )

    assert result["quote_status"] == "QUOTED"
    assert result["quoted_price"] == 1450.0
    assert result["quoted_at"] is not None          # server-generated, not client-supplied
    assert result["estimated_cost"] == 1500.0        # estimate untouched -- stays distinct


def test_accept_computes_agreed_price_server_side_from_quote(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=1450.0), farmer, db)

    result = transport_router.accept_quote(r.id, farmer, db)

    assert result["quote_status"] == "ACCEPTED"
    assert result["agreed_price"] == 1450.0          # taken from the stored quote, not the client
    assert result["agreed_at"] is not None
    assert result["estimated_cost"] == 1500.0        # estimate and agreed price remain distinct


def test_reject_does_not_set_agreed_price(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=1450.0), farmer, db)

    result = transport_router.reject_quote(r.id, farmer, db)

    assert result["quote_status"] == "REJECTED"
    assert result["agreed_price"] is None


# ─── counter-offer (one lightweight round) ──────────────────────────────────

def test_counter_offer_then_revised_quote_returns_to_quoted(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=1500.0), farmer, db)

    countered = transport_router.counter_offer(r.id, schemas.TransportCounterOffer(counter_price=1400.0), farmer, db)
    assert countered["quote_status"] == "COUNTERED"
    assert countered["counter_price"] == 1400.0

    revised = transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=1450.0), farmer, db)
    assert revised["quote_status"] == "QUOTED"
    assert revised["quoted_price"] == 1450.0

    accepted = transport_router.accept_quote(r.id, farmer, db)
    assert accepted["agreed_price"] == 1450.0


def test_cannot_counter_offer_before_a_quote_exists(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    with pytest.raises(HTTPException) as exc:
        transport_router.counter_offer(r.id, schemas.TransportCounterOffer(counter_price=1000.0), farmer, db)
    assert exc.value.status_code == 400


# ─── authorization: only the owning farmer can act ──────────────────────────

def test_unauthorized_farmer_cannot_submit_quote(db):
    owner = _make_farmer(db, "Owner", "owner@example.com")
    other = _make_farmer(db, "Other", "other@example.com")
    r = _make_request(db, owner)

    with pytest.raises(HTTPException) as exc:
        transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=1450.0), other, db)
    assert exc.value.status_code == 404   # not found for this user, not "forbidden" -- no ownership leak


def test_unauthorized_farmer_cannot_accept_quote(db):
    owner = _make_farmer(db, "Owner", "owner@example.com")
    other = _make_farmer(db, "Other", "other@example.com")
    r = _make_request(db, owner)
    transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=1450.0), owner, db)

    with pytest.raises(HTTPException) as exc:
        transport_router.accept_quote(r.id, other, db)
    assert exc.value.status_code == 404


# ─── state-machine guards ────────────────────────────────────────────────────

def test_cannot_accept_before_a_quote_exists(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    with pytest.raises(HTTPException) as exc:
        transport_router.accept_quote(r.id, farmer, db)
    assert exc.value.status_code == 400


def test_cannot_resubmit_quote_once_accepted(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=1450.0), farmer, db)
    transport_router.accept_quote(r.id, farmer, db)

    with pytest.raises(HTTPException) as exc:
        transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=999.0), farmer, db)
    assert exc.value.status_code == 400
    db.refresh(r)
    assert r.agreed_price == 1450.0   # accepted price is untouched by the rejected attempt


def test_cannot_act_on_a_cancelled_request(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    r.status = "CANCELLED"
    db.commit()

    with pytest.raises(HTTPException) as exc:
        transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=1450.0), farmer, db)
    assert exc.value.status_code == 400


# ─── pickup / delivery timestamps (server-set, not client-supplied) ─────────

def test_status_update_sets_picked_up_and_delivered_at_only_on_transition(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    assert r.picked_up_at is None
    assert r.delivered_at is None

    for step in ("MATCHED", "CONFIRMED", "PICKED_UP"):
        transport_router.update_status(r.id, schemas.TransportStatusUpdate(status=step), farmer, db)
    db.refresh(r)
    assert r.picked_up_at is not None
    assert r.delivered_at is None

    for step in ("IN_TRANSIT", "DELIVERED"):
        transport_router.update_status(r.id, schemas.TransportStatusUpdate(status=step), farmer, db)
    db.refresh(r)
    assert r.delivered_at is not None
