"""
Tests for multi-round crop-deal negotiation (buyer <-> farmer):
legacy behaviour preserved, counters, strict turn-taking, identity/RBAC,
stale/concurrent protection, shared finalization, history, backfill,
notifications. Real JWTs through a real FastAPI app on in-memory SQLite.

Run: pytest backend/tests/test_offer_negotiation.py -v
"""
import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import models
from app.database import Base, get_db
from app.auth_utils import create_access_token
from app.routers import offers as offers_router
from app.routers import offer_negotiation as neg_router
from app.routers import transactions as txn_router
from app.services import offer_negotiation as svc


@pytest.fixture()
def env():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Maker = sessionmaker(bind=engine)
    app = FastAPI()
    app.include_router(offers_router.router)
    app.include_router(neg_router.router)
    app.include_router(txn_router.router)

    def _db():
        s = Maker()
        try:
            yield s
        finally:
            s.close()
    app.dependency_overrides[get_db] = _db
    db = Maker()
    yield {"client": TestClient(app), "db": db, "Maker": Maker}
    db.close()


def _farmer(db, email="farmer@example.com"):
    f = models.Farmer(name="Farmer", email=email, password_hash="x", location="Bilaspur", phone="9999", )
    db.add(f); db.flush(); return f


def _buyer(db, email="buyer@example.com"):
    b = models.Buyer(company_name="Buyer Co", email=email, password_hash="x", location="Raipur", phone="8888")
    db.add(b); db.flush(); return b


def _listing(db, farmer, qty=100, floor=None):
    l = models.CropListing(farmer_id=farmer.id, crop="Tomato", quantity_kg=qty, expected_price_per_kg=30,
                           location="Bilaspur", available_date="2026-10-01", min_acceptable_price=floor)
    db.add(l); db.flush(); return l


def _lot(db, farmer, qty=100, floor=None, status="AVAILABLE"):
    l = models.Lot(lot_number=f"LOT-T-{qty}-{farmer.id}", farmer_id=farmer.id, crop="Tomato", quantity_kg=qty,
                   location="Bilaspur", expected_price=30, minimum_price=floor, status=status)
    db.add(l); db.flush(); return l


def H(user_or_email, role):
    email = user_or_email if isinstance(user_or_email, str) else user_or_email.email
    return {"Authorization": f"Bearer {create_access_token(email, role)}"}


@pytest.fixture()
def deal(env):
    """farmer + buyer + 100 kg listing + buyer's round-1 offer of 40 kg @ ₹24."""
    db, c = env["db"], env["client"]
    farmer, buyer = _farmer(db), _buyer(db)
    listing = _listing(db, farmer)
    db.commit()
    r = c.post("/offers", json={"listing_id": listing.id, "offered_price_per_kg": 24, "quantity_kg": 40, "message": "hi"},
               headers=H(buyer, "buyer"))
    assert r.status_code == 200, r.text
    return {**env, "farmer": farmer, "buyer": buyer, "listing": listing, "offer_id": r.json()["id"],
            "fh": H(farmer, "farmer"), "bh": H(buyer, "buyer")}


def rounds(d):
    return d["client"].get(f"/offers/{d['offer_id']}/rounds", headers=d["fh"]).json()


def counter(d, headers, price, **kw):
    return d["client"].post(f"/offers/{d['offer_id']}/counter", json={"price_per_kg": price, **kw}, headers=headers)


# ─── legacy behaviour preserved ──────────────────────────────────────────────

def test_create_offer_writes_round_one_and_awaits_farmer(deal):
    rs = rounds(deal)
    assert len(rs) == 1
    r = rs[0]
    assert (r["sequence"], r["sender_role"], r["receiver_role"], r["status"]) == (1, "buyer", "farmer", "PENDING")
    assert r["receiver_id"] == deal["farmer"].id and r["sender_id"] == deal["buyer"].id
    mine = deal["client"].get("/offers/mine", headers=deal["bh"]).json()
    assert mine[0]["awaiting_role"] == "farmer" and mine[0]["round_count"] == 1


def test_legacy_accept_never_countered_unchanged(deal):
    c, db = deal["client"], deal["db"]
    r = c.patch(f"/offers/{deal['offer_id']}/accept", headers=deal["fh"])
    assert r.status_code == 200 and r.json()["accepted"] is True
    txn = db.query(models.Transaction).one()
    assert (txn.final_price_per_kg, txn.quantity_kg, txn.total_amount, txn.status) == (24, 40, 960, "OFFER_ACCEPTED")
    assert txn.farmer_id == deal["farmer"].id and txn.buyer_id == deal["buyer"].id
    db.refresh(deal["listing"])
    assert deal["listing"].quantity_kg == 60 and deal["listing"].status == "active"
    ev = [e.event_type for e in db.query(models.TransactionEvent).order_by(models.TransactionEvent.id)]
    assert ev == ["OFFER_CREATED", "OFFER_ACCEPTED"]


def test_legacy_reject_and_lot_release(env):
    db, c = env["db"], env["client"]
    farmer, buyer = _farmer(db), _buyer(db)
    lot = _lot(db, farmer); db.commit()
    oid = c.post("/offers", json={"lot_id": lot.id, "offered_price_per_kg": 25, "quantity_kg": 10}, headers=H(buyer, "buyer")).json()["id"]
    db.refresh(lot); assert lot.status == "UNDER_OFFER"
    assert c.patch(f"/offers/{oid}/reject", headers=H(farmer, "farmer")).json() == {"rejected": True}
    db.expire_all(); db.refresh(lot)
    assert lot.status == "AVAILABLE"
    assert db.query(models.BuyerOffer).one().status == "rejected"
    assert db.query(models.BuyerOfferRound).one().status == "REJECTED"


def test_legacy_endpoints_keep_403_for_wrong_farmer(deal):
    other = _farmer(deal["db"], "other@example.com"); deal["db"].commit()
    r = deal["client"].patch(f"/offers/{deal['offer_id']}/accept", headers=H(other, "farmer"))
    assert r.status_code == 403


# ─── multi-round flow ────────────────────────────────────────────────────────

def test_full_multi_round_flow_final_price_is_accepted_round(deal):
    c, db = deal["client"], deal["db"]
    assert counter(deal, deal["fh"], 27).status_code == 200            # R2 farmer
    assert counter(deal, deal["bh"], 25.5, message="meet me").status_code == 200   # R3 buyer
    rs = rounds(deal)
    assert [r["sequence"] for r in rs] == [1, 2, 3]
    assert [r["status"] for r in rs] == ["COUNTERED", "COUNTERED", "PENDING"]
    assert [(r["sender_role"], r["receiver_role"]) for r in rs] == [("buyer", "farmer"), ("farmer", "buyer"), ("buyer", "farmer")]
    off = db.query(models.BuyerOffer).one()
    assert off.offered_price_per_kg == 25.5 and off.status == "pending"   # mirror == latest round
    # farmer accepts through the LEGACY endpoint -> shared finalization
    assert c.patch(f"/offers/{deal['offer_id']}/accept", headers=deal["fh"]).status_code == 200
    db.expire_all()
    txn = db.query(models.Transaction).one()
    assert (txn.final_price_per_kg, txn.total_amount) == (25.5, 25.5 * 40)
    off = db.query(models.BuyerOffer).one()
    assert (off.status, off.agreed_price_per_kg, off.agreed_quantity_kg) == ("accepted", 25.5, 40)
    assert off.accepted_round_id == rs[2]["id"] and off.agreed_at is not None
    rs = rounds(deal)
    assert [r["status"] for r in rs] == ["COUNTERED", "COUNTERED", "ACCEPTED"]
    assert [r["price_per_kg"] for r in rs] == [24, 27, 25.5]       # history never lost
    types = [e.event_type for e in db.query(models.TransactionEvent).order_by(models.TransactionEvent.id)]
    assert types == ["OFFER_CREATED", "OFFER_COUNTERED", "OFFER_ACCEPTED"] or sorted(types) == sorted(["OFFER_CREATED", "OFFER_COUNTERED", "OFFER_ACCEPTED"])
    tl = c.get(f"/transactions/{txn.id}/timeline", headers=deal["fh"]).json()["timeline"]
    assert [e["event_type"] for e in tl].count("OFFER_COUNTERED") == 1


def test_buyer_accepts_farmer_counter_new_endpoint_uses_owner_as_farmer(deal):
    c, db = deal["client"], deal["db"]
    counter(deal, deal["fh"], 27)
    r2 = rounds(deal)[1]
    r = c.post(f"/offers/{deal['offer_id']}/rounds/{r2['id']}/accept", headers=deal["bh"])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["accepted"] and body["final_price_per_kg"] == 27 and body["quantity_kg"] == 40
    txn = db.query(models.Transaction).one()
    assert txn.farmer_id == deal["farmer"].id            # ownership, NOT the caller (a buyer)
    assert txn.buyer_id == deal["buyer"].id and txn.total_amount == 1080
    ev = db.query(models.TransactionEvent).filter_by(event_type="OFFER_ACCEPTED").one()
    assert ev.performed_by == "buyer" and "buyer" in ev.description
    # downstream lifecycle still works from a negotiated deal
    r = c.patch(f"/transactions/{txn.id}/status", json={"status": "ORDER_CONFIRMED"}, headers=deal["bh"])
    assert r.status_code == 200, r.text


def test_farmer_accepts_via_new_endpoint_and_reject_closes_only_this_thread(env):
    db, c = env["db"], env["client"]
    farmer, b1, b2 = _farmer(db), _buyer(db, "b1@example.com"), _buyer(db, "b2@example.com")
    listing = _listing(db, farmer); db.commit()
    o1 = c.post("/offers", json={"listing_id": listing.id, "offered_price_per_kg": 20, "quantity_kg": 10}, headers=H(b1, "buyer")).json()["id"]
    o2 = c.post("/offers", json={"listing_id": listing.id, "offered_price_per_kg": 21, "quantity_kg": 10}, headers=H(b2, "buyer")).json()["id"]
    r1 = c.get(f"/offers/{o1}/rounds", headers=H(farmer, "farmer")).json()[0]
    assert c.post(f"/offers/{o1}/rounds/{r1['id']}/reject", headers=H(farmer, "farmer")).json()["rejected"] is True
    db.expire_all()
    assert db.get(models.BuyerOffer, o1).status == "rejected"
    assert db.get(models.BuyerOffer, o2).status == "pending"         # other buyer unaffected
    assert db.query(models.Transaction).count() == 0


# ─── turn enforcement ────────────────────────────────────────────────────────

def test_turn_enforcement(deal):
    c = deal["client"]
    assert counter(deal, deal["bh"], 26).status_code == 400            # buyer holds nothing: own round 1 outstanding
    assert counter(deal, deal["fh"], 27).status_code == 200
    assert counter(deal, deal["fh"], 28).status_code == 400            # farmer can't counter own counter twice
    r2 = rounds(deal)[1]
    assert c.post(f"/offers/{deal['offer_id']}/rounds/{r2['id']}/accept", headers=deal["fh"]).status_code == 400  # own counter
    assert c.post(f"/offers/{deal['offer_id']}/rounds/{r2['id']}/reject", headers=deal["fh"]).status_code == 400
    assert c.patch(f"/offers/{deal['offer_id']}/accept", headers=deal["fh"]).status_code == 400   # legacy is turn-aware
    assert c.patch(f"/offers/{deal['offer_id']}/reject", headers=deal["fh"]).status_code == 400
    assert deal["db"].query(models.Transaction).count() == 0


# ─── identity & authorization ────────────────────────────────────────────────

def test_authorization_and_identity(deal):
    c, db = deal["client"], deal["db"]
    oid = deal["offer_id"]
    other_f, other_b = _farmer(db, "of@example.com"), _buyer(db, "ob@example.com")
    t = models.Transporter(name="T", email="t@example.com", password_hash="x"); db.add(t); db.commit()
    for hdrs in (H(other_f, "farmer"), H(other_b, "buyer")):
        assert c.get(f"/offers/{oid}", headers=hdrs).status_code == 404
        assert c.get(f"/offers/{oid}/rounds", headers=hdrs).status_code == 404
        assert c.post(f"/offers/{oid}/counter", json={"price_per_kg": 20}, headers=hdrs).status_code == 404
        assert c.post(f"/offers/{oid}/withdraw", headers=hdrs).status_code == 404
    assert c.get(f"/offers/{oid}", headers=H("t@example.com", "transporter")).status_code == 403
    assert c.get(f"/offers/{oid}").status_code == 401
    assert c.post(f"/offers/{oid}/counter", json={"price_per_kg": 20}).status_code == 401


def test_client_supplied_ids_are_ignored(deal):
    r = counter(deal, deal["fh"], 27, sender_id=999, receiver_id=999, sender_role="buyer", buyer_id=999, farmer_id=999)
    assert r.status_code == 200
    j = r.json()
    assert (j["sender_role"], j["sender_id"], j["receiver_role"], j["receiver_id"]) == ("farmer", deal["farmer"].id, "buyer", deal["buyer"].id)


def test_thread_privacy_and_floor_visibility(env):
    db, c = env["db"], env["client"]
    farmer, buyer = _farmer(db), _buyer(db)
    listing = _listing(db, farmer, floor=18); db.commit()
    oid = c.post("/offers", json={"listing_id": listing.id, "offered_price_per_kg": 20, "quantity_kg": 10}, headers=H(buyer, "buyer")).json()["id"]
    f = c.get(f"/offers/{oid}", headers=H(farmer, "farmer")).json()
    b = c.get(f"/offers/{oid}", headers=H(buyer, "buyer")).json()
    for j in (f, b):
        assert "email" not in j["buyer"] and "phone" not in j["buyer"] and "email" not in j["farmer"] and "phone" not in j["farmer"]
    assert f["target"]["min_price_per_kg"] == 18 and "min_price_per_kg" not in b["target"]
    assert f["can_act"]["accept"] and not f["can_act"]["withdraw"] and b["can_act"]["withdraw"] and not b["can_act"]["accept"]


# ─── validation ──────────────────────────────────────────────────────────────

def test_counter_validation(env):
    db, c = env["db"], env["client"]
    farmer, buyer = _farmer(db), _buyer(db)
    listing = _listing(db, farmer, qty=100, floor=22); db.commit()
    fh, bh = H(farmer, "farmer"), H(buyer, "buyer")
    oid = c.post("/offers", json={"listing_id": listing.id, "offered_price_per_kg": 23, "quantity_kg": 40}, headers=bh).json()["id"]
    url = f"/offers/{oid}/counter"
    assert c.post(url, json={"price_per_kg": 0}, headers=fh).status_code == 422
    assert c.post(url, json={"price_per_kg": -1}, headers=fh).status_code == 422
    assert c.post(url, json={"price_per_kg": 25, "quantity_kg": 0}, headers=fh).status_code == 422
    assert c.post(url, json={"price_per_kg": 25, "quantity_kg": 101}, headers=fh).status_code == 400
    assert c.post(url, json={"price_per_kg": 25, "message": "x" * 2001}, headers=fh).status_code == 422
    # farmer may counter below their own minimum (floor is enforced on BUYER rounds only)
    assert c.post(url, json={"price_per_kg": 15}, headers=fh).status_code == 200
    assert c.post(url, json={"price_per_kg": 21.5}, headers=bh).status_code == 400       # buyer below farmer floor
    assert c.post(url, json={"price_per_kg": 22.5, "quantity_kg": 30}, headers=bh).status_code == 200


def test_round_cap(deal):
    for i in range(1, svc.MAX_ROUNDS_PER_OFFER):
        hdrs = deal["fh"] if i % 2 else deal["bh"]
        assert counter(deal, hdrs, 20 + i).status_code == 200, i
    assert len(rounds(deal)) == svc.MAX_ROUNDS_PER_OFFER
    last_hdrs = deal["bh"] if svc.MAX_ROUNDS_PER_OFFER % 2 == 1 else deal["fh"]
    assert counter(deal, deal["fh"] if svc.MAX_ROUNDS_PER_OFFER % 2 == 1 else deal["bh"], 99).status_code == 400


# ─── stale / concurrent protection ───────────────────────────────────────────

def test_stale_round_actions_are_409(deal):
    c = deal["client"]
    r1 = rounds(deal)[0]
    counter(deal, deal["fh"], 27)
    assert c.post(f"/offers/{deal['offer_id']}/rounds/{r1['id']}/accept", headers=deal["fh"]).status_code == 409
    assert c.post(f"/offers/{deal['offer_id']}/rounds/{r1['id']}/reject", headers=deal["fh"]).status_code == 409
    r2 = rounds(deal)[1]
    assert counter(deal, deal["bh"], 25, based_on_round_id=r1["id"]).status_code == 409
    assert counter(deal, deal["bh"], 25, based_on_round_id=r2["id"]).status_code == 200
    assert c.post(f"/offers/{deal['offer_id']}/rounds/9999/accept", headers=deal["fh"]).status_code == 404


def test_no_actions_after_terminal_state(deal):
    c = deal["client"]
    c.patch(f"/offers/{deal['offer_id']}/accept", headers=deal["fh"])
    r = rounds(deal)[0]
    assert counter(deal, deal["bh"], 30).status_code == 400
    assert c.post(f"/offers/{deal['offer_id']}/rounds/{r['id']}/accept", headers=deal["fh"]).status_code == 400
    assert c.post(f"/offers/{deal['offer_id']}/withdraw", headers=deal["bh"]).status_code == 400
    assert c.patch(f"/offers/{deal['offer_id']}/accept", headers=deal["fh"]).status_code == 400   # duplicate accept
    assert deal["db"].query(models.Transaction).count() == 1


def test_duplicate_sequence_is_rejected_by_database(deal):
    db = deal["db"]
    r1 = db.query(models.BuyerOfferRound).one()
    db.add(models.BuyerOfferRound(offer_id=r1.offer_id, sequence=1, sender_role="farmer", sender_id=1,
                                  receiver_role="buyer", receiver_id=1, price_per_kg=1, quantity_kg=1))
    with pytest.raises(IntegrityError):
        db.commit()
    db.rollback()


def test_concurrent_counter_integrity_error_maps_to_409(deal, monkeypatch):
    real = Session.commit
    state = {"n": 0}

    def flaky(self):
        state["n"] += 1
        raise IntegrityError("INSERT", {}, Exception("duplicate sequence"))
    monkeypatch.setattr(Session, "commit", flaky)
    r = counter(deal, deal["fh"], 27)
    monkeypatch.setattr(Session, "commit", real)
    assert r.status_code == 409 and state["n"] == 1
    assert len(rounds(deal)) == 1 and rounds(deal)[0]["status"] == "PENDING"   # nothing half-written


def test_cannot_oversell_and_sellout_closes_siblings(env):
    db, c = env["db"], env["client"]
    farmer, b1, b2, b3 = _farmer(db), _buyer(db, "b1@x.com"), _buyer(db, "b2@x.com"), _buyer(db, "b3@x.com")
    listing = _listing(db, farmer, qty=100); db.commit()
    fh = H(farmer, "farmer")
    mk = lambda b, q: c.post("/offers", json={"listing_id": listing.id, "offered_price_per_kg": 20, "quantity_kg": q}, headers=H(b, "buyer")).json()["id"]
    o1, o2, o3 = mk(b1, 60), mk(b2, 60), mk(b3, 10)
    assert c.patch(f"/offers/{o1}/accept", headers=fh).status_code == 200      # 40 left
    r = c.patch(f"/offers/{o2}/accept", headers=fh)
    assert r.status_code == 400 and "exceeds" in r.json()["detail"]            # no oversell
    assert counter({"client": c, "offer_id": o2}, H(farmer, "farmer"), 21, quantity_kg=40).status_code == 200
    r2 = c.get(f"/offers/{o2}/rounds", headers=fh).json()[-1]
    assert c.post(f"/offers/{o2}/rounds/{r2['id']}/accept", headers=H(b2, "buyer")).status_code == 200   # 0 left -> sold
    db.expire_all()
    assert db.get(models.CropListing, listing.id).status == "sold"
    assert db.get(models.BuyerOffer, o3).status == "rejected"                  # sibling closed on sell-out
    assert all(r.status != "PENDING" for r in db.query(models.BuyerOfferRound).filter_by(offer_id=o3))


# ─── withdraw ────────────────────────────────────────────────────────────────

def test_withdraw_sender_only_and_releases_lot(env):
    db, c = env["db"], env["client"]
    farmer, buyer = _farmer(db), _buyer(db)
    lot = _lot(db, farmer); db.commit()
    fh, bh = H(farmer, "farmer"), H(buyer, "buyer")
    oid = c.post("/offers", json={"lot_id": lot.id, "offered_price_per_kg": 25, "quantity_kg": 10}, headers=bh).json()["id"]
    assert c.post(f"/offers/{oid}/withdraw", headers=fh).status_code == 400       # receiver can't withdraw
    assert c.post(f"/offers/{oid}/withdraw", headers=bh).json()["withdrawn"] is True
    db.expire_all()
    assert db.get(models.BuyerOffer, oid).status == "withdrawn"
    assert db.query(models.BuyerOfferRound).one().status == "WITHDRAWN"
    assert db.get(models.Lot, lot.id).status == "AVAILABLE"
    assert c.post(f"/offers/{oid}/withdraw", headers=bh).status_code == 400


def test_farmer_can_withdraw_own_counter(deal):
    counter(deal, deal["fh"], 27)
    assert deal["client"].post(f"/offers/{deal['offer_id']}/withdraw", headers=deal["fh"]).status_code == 200
    assert deal["db"].query(models.BuyerOffer).one().status == "withdrawn"


# ─── awaiting-me list ────────────────────────────────────────────────────────

def test_awaiting_me(deal):
    c = deal["client"]
    assert [o["id"] for o in c.get("/offers/awaiting-me", headers=deal["fh"]).json()] == [deal["offer_id"]]
    assert c.get("/offers/awaiting-me", headers=deal["bh"]).json() == []
    counter(deal, deal["fh"], 27)
    assert c.get("/offers/awaiting-me", headers=deal["fh"]).json() == []
    assert [o["awaiting_role"] for o in c.get("/offers/awaiting-me", headers=deal["bh"]).json()] == ["buyer"]


# ─── backfill / legacy rows ──────────────────────────────────────────────────

def test_backfill_idempotent_and_status_mapping(env):
    db = env["db"]
    farmer, buyer = _farmer(db), _buyer(db)
    listing = _listing(db, farmer); db.flush()
    for st in ("pending", "accepted", "rejected", "withdrawn"):
        db.add(models.BuyerOffer(buyer_id=buyer.id, listing_id=listing.id, offered_price_per_kg=20, quantity_kg=5, status=st))
    db.add(models.BuyerOffer(buyer_id=buyer.id, listing_id=9999, offered_price_per_kg=20, quantity_kg=5, status="pending"))  # orphan
    db.commit()
    assert svc.backfill_offer_rounds(db) == 4
    assert svc.backfill_offer_rounds(db) == 0                       # idempotent
    got = {o.status: o.rounds[0].status for o in db.query(models.BuyerOffer).all() if o.rounds}
    assert got == {"pending": "PENDING", "accepted": "ACCEPTED", "rejected": "REJECTED", "withdrawn": "WITHDRAWN"}
    pend = [o for o in db.query(models.BuyerOffer).filter_by(status="pending") if o.rounds][0].rounds[0]
    assert (pend.sender_role, pend.receiver_role, pend.receiver_id) == ("buyer", "farmer", farmer.id)


def test_legacy_inserted_offer_is_lazily_negotiable(env):
    db, c = env["db"], env["client"]
    farmer, buyer = _farmer(db), _buyer(db)
    listing = _listing(db, farmer); db.flush()
    o = models.BuyerOffer(buyer_id=buyer.id, listing_id=listing.id, offered_price_per_kg=20, quantity_kg=5, status="pending")
    db.add(o); db.commit()
    assert db.query(models.BuyerOfferRound).count() == 0
    r = c.post(f"/offers/{o.id}/counter", json={"price_per_kg": 26}, headers=H(farmer, "farmer"))
    assert r.status_code == 200 and r.json()["sequence"] == 2
    assert len(c.get(f"/offers/{o.id}/rounds", headers=H(buyer, "buyer")).json()) == 2


# ─── notifications ───────────────────────────────────────────────────────────

def test_notifications_sent_to_counterparty(deal):
    db = deal["db"]
    counter(deal, deal["fh"], 27)
    n = db.query(models.Notification).filter_by(buyer_id=deal["buyer"].id, type="offer_countered").all()
    assert len(n) == 1
    r2 = rounds(deal)[1]
    deal["client"].post(f"/offers/{deal['offer_id']}/rounds/{r2['id']}/accept", headers=deal["bh"])
    assert db.query(models.Notification).filter_by(farmer_id=deal["farmer"].id, type="offer_accepted").count() == 1
