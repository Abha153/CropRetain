"""
Tests for the real authenticated FARMER <-> TRANSPORTER workflow:
- transporter auth / RBAC (app/auth_utils.py, app/routers/auth.py)
- claiming a request (app/routers/transporters.py)
- multi-round negotiation with persistent offer history (app/routers/transport_negotiation.py)
- chat (app/routers/transport_negotiation.py)
- transporter-driven status transitions (app/routers/transport_negotiation.py)
- two-sided reviews (app/routers/transport_negotiation.py)

Run: pytest backend/tests/test_transporter_workflow.py -v
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
from app.auth_utils import get_current_user, require_farmer, require_transporter
from app.routers import transporters as transporters_router
from app.routers import transport_negotiation as neg
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


def _make_buyer(db, name="Buyer Co", email="buyer@example.com"):
    b = models.Buyer(company_name=name, email=email, password_hash="x", location="Raipur")
    db.add(b)
    db.flush()
    return b


def _make_transporter(db, name="Transporter", email="transporter@example.com"):
    t = models.Transporter(name=name, email=email, password_hash="x")
    db.add(t)
    db.flush()
    return t


def _make_request(db, farmer, estimated_cost=1500.0):
    r = models.TransportRequest(
        farmer_id=farmer.id, pickup_location="Bilaspur", destination="Raipur",
        estimated_cost=estimated_cost,
    )
    db.add(r)
    db.commit()
    db.refresh(r)
    return r


def _claim(db, r, transporter):
    return transporters_router.claim_request(r.id, transporter, db)


# ─── auth / RBAC ──────────────────────────────────────────────────────────────

def test_transporter_role_recognized_by_get_current_user(db, monkeypatch):
    t = _make_transporter(db)
    db.commit()

    import app.auth_utils as au

    monkeypatch.setattr(au, "decode_token", lambda token: {"sub": t.email, "role": "transporter"})
    result = get_current_user(token="fake", db=db)
    assert result["role"] == "transporter"
    assert result["user"].id == t.id


def test_require_transporter_rejects_farmer():
    with pytest.raises(HTTPException) as exc:
        require_transporter({"user": object(), "role": "farmer"})
    assert exc.value.status_code == 403


def test_farmer_cannot_use_transporter_endpoints(db):
    """FastAPI enforces require_transporter via Depends() before a
    transporter-only route body ever runs; this asserts that gate itself
    rejects a farmer, the same pattern used for the ownership checks
    elsewhere in this codebase's test suite."""
    farmer = _make_farmer(db)
    db.commit()
    with pytest.raises(HTTPException) as exc:
        require_transporter({"user": farmer, "role": "farmer"})
    assert exc.value.status_code == 403


def test_buyer_cannot_use_transporter_endpoints():
    with pytest.raises(HTTPException) as exc:
        require_transporter({"user": object(), "role": "buyer"})
    assert exc.value.status_code == 403


def test_transporter_cannot_use_farmer_only_endpoints():
    with pytest.raises(HTTPException) as exc:
        require_farmer({"user": object(), "role": "transporter"})
    assert exc.value.status_code == 403


# ─── claiming ─────────────────────────────────────────────────────────────────

def test_open_request_visible_to_any_transporter_without_farmer_pii(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()

    results = transporters_router.available_requests(t, db)
    assert len(results) == 1
    assert "farmer" not in results[0]   # PII withheld before claiming


def test_transporter_can_claim_open_request(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()

    result = _claim(db, r, t)
    assert result["negotiation_status"] == "NEGOTIATING"
    db.refresh(r)
    assert r.transporter_id == t.id


def test_second_transporter_cannot_claim_already_claimed_request(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t1 = _make_transporter(db, "T1", "t1@example.com")
    t2 = _make_transporter(db, "T2", "t2@example.com")
    db.commit()

    _claim(db, r, t1)
    with pytest.raises(HTTPException) as exc:
        _claim(db, r, t2)
    assert exc.value.status_code == 409


def test_unrelated_transporter_cannot_see_assigned_request_as_theirs(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t1 = _make_transporter(db, "T1", "t1@example.com")
    t2 = _make_transporter(db, "T2", "t2@example.com")
    db.commit()
    _claim(db, r, t1)

    with pytest.raises(HTTPException) as exc:
        transporters_router.get_assigned_request(r.id, t2, db)
    assert exc.value.status_code == 404


# ─── negotiation: valid alternating flow ─────────────────────────────────────

def test_full_negotiation_scenario_matches_spec_example(db):
    """Transporter -> 1350, Farmer -> 1200, Transporter -> 1300,
    Farmer -> 1250, Transporter -> 1275, Farmer -> Accept."""
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _claim(db, r, t)

    o1 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1350), (t, "transporter"), db)
    assert o1.sequence == 1
    o2 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1200), (farmer, "farmer"), db)
    assert o2.sequence == 2
    o3 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1300), (t, "transporter"), db)
    o4 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1250), (farmer, "farmer"), db)
    o5 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1275), (t, "transporter"), db)

    accepted = neg.accept_offer(r.id, o5.id, (farmer, "farmer"), db)
    assert accepted.status == "ACCEPTED"

    db.refresh(r)
    assert r.transporter_agreed_price == 1275
    assert r.negotiation_status == "AGREED"
    assert r.status == "CONFIRMED"   # booking reuses CONFIRMED, no competing status

    history = neg.list_offers(r.id, (farmer, "farmer"), db)
    assert [o.amount for o in history] == [1350, 1200, 1300, 1250, 1275]
    # every prior offer left superseded, none overwritten
    assert [o.status for o in history] == ["SUPERSEDED"] * 4 + ["ACCEPTED"]


def test_first_offer_must_come_from_transporter(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _claim(db, r, t)

    with pytest.raises(HTTPException) as exc:
        neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1000), (farmer, "farmer"), db)
    assert exc.value.status_code == 400


def test_out_of_turn_offer_rejected(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _claim(db, r, t)
    neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1350), (t, "transporter"), db)

    # Transporter tries to offer again before farmer responds.
    with pytest.raises(HTTPException) as exc:
        neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1300), (t, "transporter"), db)
    assert exc.value.status_code == 400


def test_invalid_participant_cannot_offer(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    other_t = _make_transporter(db, "Other", "other-t@example.com")
    db.commit()
    _claim(db, r, t)

    with pytest.raises(HTTPException) as exc:
        neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1350), (other_t, "transporter"), db)
    assert exc.value.status_code == 404


def test_stale_offer_cannot_be_accepted(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _claim(db, r, t)

    o1 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1350), (t, "transporter"), db)
    neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1200), (farmer, "farmer"), db)  # supersedes o1

    # o1's receiver was the farmer -- correct recipient, but the offer is
    # now stale/superseded, which must be rejected on that basis (400),
    # not treated as a recipient mismatch.
    with pytest.raises(HTTPException) as exc:
        neg.accept_offer(r.id, o1.id, (farmer, "farmer"), db)
    assert exc.value.status_code == 400


def test_duplicate_accept_rejected(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _claim(db, r, t)
    o1 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1350), (t, "transporter"), db)
    neg.accept_offer(r.id, o1.id, (farmer, "farmer"), db)

    with pytest.raises(HTTPException) as exc:
        neg.accept_offer(r.id, o1.id, (farmer, "farmer"), db)
    assert exc.value.status_code == 400


def test_cannot_accept_someone_elses_offer(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _claim(db, r, t)
    o1 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1350), (t, "transporter"), db)

    # Sender (transporter) tries to accept their own outstanding offer.
    with pytest.raises(HTTPException) as exc:
        neg.accept_offer(r.id, o1.id, (t, "transporter"), db)
    assert exc.value.status_code == 403


def test_unauthorized_access_to_offers_denied(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    other_farmer = _make_farmer(db, "Other", "otherf@example.com")
    db.commit()
    _claim(db, r, t)

    with pytest.raises(HTTPException) as exc:
        neg.list_offers(r.id, (other_farmer, "farmer"), db)
    assert exc.value.status_code == 404


def test_client_cannot_set_agreed_price_directly():
    """TransportOfferCreate has no receiver/sender/status/agreed_price
    field at all -- schema-level enforcement that these can never be
    supplied by the client."""
    fields = schemas.TransportOfferCreate.model_fields.keys()
    assert "sender_id" not in fields
    assert "receiver_id" not in fields
    assert "status" not in fields
    assert "agreed_price" not in fields


# ─── chat ──────────────────────────────────────────────────────────────────────

def test_chat_participant_access_and_ordering(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _claim(db, r, t)

    neg.send_message(r.id, schemas.TransportMessageCreate(message="Can you do ₹1200?"), (farmer, "farmer"), db)
    neg.send_message(r.id, schemas.TransportMessageCreate(message="I can do ₹1300."), (t, "transporter"), db)

    msgs = neg.list_messages(r.id, (farmer, "farmer"), db)
    assert [m.message for m in msgs] == ["Can you do ₹1200?", "I can do ₹1300."]
    assert msgs[0].sender_role == "farmer" and msgs[0].recipient_role == "transporter"


def test_chat_unrelated_user_denied(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    other_t = _make_transporter(db, "Other", "othert2@example.com")
    db.commit()
    _claim(db, r, t)

    with pytest.raises(HTTPException) as exc:
        neg.send_message(r.id, schemas.TransportMessageCreate(message="hi"), (other_t, "transporter"), db)
    assert exc.value.status_code == 404


def test_message_sender_derived_server_side_not_from_client():
    fields = schemas.TransportMessageCreate.model_fields.keys()
    assert "sender_id" not in fields
    assert "recipient_id" not in fields


# ─── transporter-driven status + completion ──────────────────────────────────

def test_transporter_status_lifecycle_to_completion(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _claim(db, r, t)
    o1 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1275), (t, "transporter"), db)
    neg.accept_offer(r.id, o1.id, (farmer, "farmer"), db)

    for step in ("PICKED_UP", "IN_TRANSIT", "DELIVERED", "COMPLETED"):
        result = neg.transporter_update_status(r.id, schemas.TransporterStatusUpdate(status=step), t, db)
        assert result["status"] == step
    db.refresh(r)
    assert r.picked_up_at is not None
    assert r.delivered_at is not None
    assert r.completed_at is not None


def test_unassigned_transporter_cannot_update_status(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    r.status = "CONFIRMED"
    t = _make_transporter(db)
    other_t = _make_transporter(db, "Other", "othert3@example.com")
    db.commit()
    r.transporter_id = t.id
    db.commit()

    with pytest.raises(HTTPException) as exc:
        neg.transporter_update_status(r.id, schemas.TransporterStatusUpdate(status="PICKED_UP"), other_t, db)
    assert exc.value.status_code == 404


def test_invalid_transporter_status_transition_rejected(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    r.transporter_id = t.id
    db.commit()

    # REQUESTED has no entry in TRANSPORTER_VALID_TRANSITIONS -- cannot skip to DELIVERED.
    with pytest.raises(HTTPException) as exc:
        neg.transporter_update_status(r.id, schemas.TransporterStatusUpdate(status="DELIVERED"), t, db)
    assert exc.value.status_code == 400


# ─── two-sided reviews ────────────────────────────────────────────────────────

def _deliver(db, r, t, farmer):
    _claim(db, r, t)
    o1 = neg.create_offer(r.id, schemas.TransportOfferCreate(amount=1275), (t, "transporter"), db)
    neg.accept_offer(r.id, o1.id, (farmer, "farmer"), db)
    neg.transporter_update_status(r.id, schemas.TransporterStatusUpdate(status="PICKED_UP"), t, db)
    neg.transporter_update_status(r.id, schemas.TransporterStatusUpdate(status="IN_TRANSIT"), t, db)
    neg.transporter_update_status(r.id, schemas.TransporterStatusUpdate(status="DELIVERED"), t, db)


def test_farmer_and_transporter_can_review_each_other_after_completion(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _deliver(db, r, t, farmer)

    review1 = neg.submit_review(
        r.id, schemas.TransportReviewCreate(rating=5, punctuality=5, comment="Great!"),
        (farmer, "farmer"), db,
    )
    assert review1.reviewee_role == "transporter" and review1.reviewee_id == t.id
    db.refresh(t)
    assert t.rating == 5.0 and t.rating_count == 1

    review2 = neg.submit_review(
        r.id, schemas.TransportReviewCreate(rating=4, reliability=4),
        (t, "transporter"), db,
    )
    assert review2.reviewee_role == "farmer" and review2.reviewee_id == farmer.id


def test_review_before_completion_rejected(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    r.transporter_id = t.id
    db.commit()

    with pytest.raises(HTTPException) as exc:
        neg.submit_review(r.id, schemas.TransportReviewCreate(rating=5), (farmer, "farmer"), db)
    assert exc.value.status_code == 400


def test_unrelated_user_cannot_review(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    other_farmer = _make_farmer(db, "Other", "otherf2@example.com")
    db.commit()
    _deliver(db, r, t, farmer)

    with pytest.raises(HTTPException) as exc:
        neg.submit_review(r.id, schemas.TransportReviewCreate(rating=5), (other_farmer, "farmer"), db)
    assert exc.value.status_code == 404


def test_duplicate_review_prevented(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    t = _make_transporter(db)
    db.commit()
    _deliver(db, r, t, farmer)
    neg.submit_review(r.id, schemas.TransportReviewCreate(rating=5), (farmer, "farmer"), db)

    with pytest.raises(HTTPException) as exc:
        neg.submit_review(r.id, schemas.TransportReviewCreate(rating=3), (farmer, "farmer"), db)
    assert exc.value.status_code == 400


def test_reviewer_identity_not_client_supplied():
    fields = schemas.TransportReviewCreate.model_fields.keys()
    assert "reviewer_id" not in fields
    assert "reviewee_id" not in fields


# ─── regression: legacy farmer-mediated quote flow untouched ────────────────

def test_legacy_farmer_quote_flow_still_works(db):
    farmer = _make_farmer(db)
    r = _make_request(db, farmer)
    db.commit()

    result = transport_router.submit_quote(r.id, schemas.TransportQuoteSubmit(quoted_price=1450.0), farmer, db)
    assert result["quote_status"] == "QUOTED"
    accepted = transport_router.accept_quote(r.id, farmer, db)
    assert accepted["agreed_price"] == 1450.0
    # Legacy and new negotiated-price fields are fully independent.
    assert accepted["transporter_agreed_price"] is None
    assert accepted["negotiation_status"] == "OPEN"
