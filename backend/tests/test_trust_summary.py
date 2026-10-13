"""
Phase C -- marketplace trust summaries.

Self-contained: each test gets a fresh in-memory database and overrides the
get_db dependency, so it does not depend on (or disturb) the shared test DB.
The TestClient is deliberately NOT used as a context manager, so the app's
startup seeding does not run.
"""
import datetime as dt
import itertools
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app import models
from app.auth_utils import create_access_token
from app.config import settings
from app.database import Base, get_db
from app.main import app
from app.seed_data import DEMO_BUYERS, ensure_demo_buyer_verification_records
from app.services import trust_summary

_counter = itertools.count(1)


class Env:
    def __init__(self, db, client):
        self.db = db
        self.client = client

    # ---- users ----
    def _add(self, obj):
        self.db.add(obj)
        self.db.commit()
        self.db.refresh(obj)
        return obj

    def farmer(self, **kw):
        n = next(_counter)
        kw.setdefault("name", f"Farmer {n}")
        kw.setdefault("email", f"farmer{n}@example.test")
        return self._add(models.Farmer(password_hash="x", location="Bilaspur", **kw))

    def buyer(self, **kw):
        n = next(_counter)
        kw.setdefault("company_name", f"Buyer Co {n}")
        kw.setdefault("email", f"buyer{n}@example.test")
        return self._add(models.Buyer(password_hash="x", location="Raipur", **kw))

    def transporter(self, **kw):
        n = next(_counter)
        kw.setdefault("name", f"Transporter {n}")
        kw.setdefault("email", f"transporter{n}@example.test")
        return self._add(models.Transporter(password_hash="x", **kw))

    # ---- records ----
    def txn(self, farmer, buyer, status="COMPLETED", total=1000.0):
        return self._add(models.Transaction(
            farmer_id=farmer.id, buyer_id=buyer.id, final_price_per_kg=10.0,
            quantity_kg=100.0, total_amount=total, status=status))

    def rate(self, txn, rater_role, rater, ratee_role, ratee, rating=5.0, review=None):
        return self._add(models.Rating(
            transaction_id=txn.id, rater_role=rater_role, rater_id=rater.id,
            ratee_role=ratee_role, ratee_id=ratee.id, rating=rating, review=review))

    def trip(self, farmer, transporter=None, buyer=None, status="DELIVERED"):
        return self._add(models.TransportRequest(
            farmer_id=farmer.id, buyer_id=buyer.id if buyer else None,
            transporter_id=transporter.id if transporter else None,
            pickup_location="A", destination="B", status=status))

    def transport_review(self, trip, reviewer_role, reviewer, reviewee_role, reviewee,
                         rating=5.0, comment=None):
        return self._add(models.TransportReview(
            transport_request_id=trip.id, reviewer_role=reviewer_role, reviewer_id=reviewer.id,
            reviewee_role=reviewee_role, reviewee_id=reviewee.id, rating=rating, comment=comment))

    def trip_review(self, trip, farmer, review_type="TRANSPORTER", rating=5.0, comment=None):
        return self._add(models.TripReview(
            transport_request_id=trip.id, reviewer_farmer_id=farmer.id,
            review_type=review_type, rating=rating, comment=comment, verified=True))

    def payment(self, txn, buyer, farmer, status="PAID", is_demo=False):
        return self._add(models.Payment(
            transaction_id=txn.id, buyer_id=buyer.id, farmer_id=farmer.id,
            amount=txn.total_amount, payment_status=status, is_demo=is_demo))

    def verification(self, buyer, status, **kw):
        return self._add(models.BuyerVerification(
            buyer_id=buyer.id, verification_status=status, **kw))

    # ---- http ----
    @staticmethod
    def auth(user, role):
        return {"Authorization": "Bearer " + create_access_token(subject=user.email, role=role)}

    @staticmethod
    def admin_auth():
        return {"Authorization": "Bearer " + create_access_token(
            subject=settings.admin_username, role="admin")}

    def get(self, path, headers=None):
        return self.client.get(path, headers=headers)

    def admin_get(self, path):
        return self.client.get(path, headers=self.admin_auth())

    def summary(self, role, subject):
        r = self.admin_get(f"/trust/{role}s/{subject.id}")
        assert r.status_code == 200, r.text
        return r.json()


@pytest.fixture()
def env():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def override_get_db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    db = Session()
    yield Env(db, TestClient(app))
    db.close()
    app.dependency_overrides.pop(get_db, None)
    engine.dispose()


def rated_txns(env, farmer, buyer, n, ratee_role="farmer", rating=4.0, review=None, status="DELIVERED"):
    """n distinct transactions, each rated once by the counterparty."""
    for _ in range(n):
        t = env.txn(farmer, buyer, status=status)
        if ratee_role == "farmer":
            env.rate(t, "buyer", buyer, "farmer", farmer, rating, review)
        else:
            env.rate(t, "farmer", farmer, "buyer", buyer, rating, review)


# ===========================================================================
# Legacy defaults are never evidence
# ===========================================================================

def test_new_farmer_with_legacy_rating_has_insufficient_data(env):
    f = env.farmer()                       # model default Farmer.rating == 4.5
    assert f.rating == 4.5
    s = env.summary("farmer", f)
    assert s["badges"] == []
    assert s["flags"] == ["NOT_SUPPORTED", "INSUFFICIENT_DATA"]
    assert s["verification"] == {"state": "NOT_SUPPORTED", "tier": None, "supported": False}
    assert s["trade"]["rating"] == {"state": "INSUFFICIENT_DATA", "count": 0,
                                    "average": None, "min_count": 3}
    assert s["logistics"]["rating"]["average"] is None
    assert "4.5" not in json.dumps(s)


@pytest.mark.parametrize("reliability,payment", [(85.0, 90.0), (60.0, 60.0), (100.0, 100.0)])
def test_new_buyer_with_legacy_scores_has_insufficient_data(env, reliability, payment):
    b = env.buyer(reliability_score=reliability, payment_history_score=payment)
    s = env.summary("buyer", b)
    assert s["badges"] == []
    assert s["flags"] == ["NOT_VERIFIED", "INSUFFICIENT_DATA"]
    assert s["trade"]["payment_history"]["state"] == "INSUFFICIENT_DATA"
    assert s["logistics"] is None
    assert str(reliability) not in json.dumps(s)


def test_new_transporter_has_insufficient_data_even_with_stored_rating(env):
    t = env.transporter()
    s = env.summary("transporter", t)
    assert s["badges"] == [] and s["flags"] == ["NOT_SUPPORTED", "INSUFFICIENT_DATA"]
    assert s["trade"] is None
    # Stored aggregate is ignored: only real review rows count.
    t2 = env.transporter(rating=4.9, rating_count=80)
    s2 = env.summary("transporter", t2)
    assert s2["badges"] == []
    assert s2["logistics"]["rating"]["count"] == 0
    assert s2["logistics"]["rating"]["average"] is None


# ===========================================================================
# Threshold boundaries
# ===========================================================================

@pytest.mark.parametrize("n,rated", [(0, False), (1, False), (2, False), (3, True), (4, True)])
def test_rating_threshold_boundary(env, n, rated):
    f, b = env.farmer(), env.buyer()
    rated_txns(env, f, b, n, rating=4.0)
    s = env.summary("farmer", f)
    r = s["trade"]["rating"]
    assert r["count"] == n
    assert ("RATED" in s["badges"]) is rated
    if rated:
        assert r["state"] == "RATED" and r["average"] == 4.0
    else:
        assert r["state"] == "INSUFFICIENT_DATA" and r["average"] is None


def test_rating_average_is_rounded_mean_of_real_ratings(env):
    f, b = env.farmer(), env.buyer()
    for v in (5.0, 4.0, 4.0):
        t = env.txn(f, b, "DELIVERED")
        env.rate(t, "buyer", b, "farmer", f, v)
    assert env.summary("farmer", f)["trade"]["rating"]["average"] == 4.33


def test_review_threshold_boundary(env):
    f, b = env.farmer(), env.buyer()
    for text in (None, "", "   \n"):
        t = env.txn(f, b, "DELIVERED")
        env.rate(t, "buyer", b, "farmer", f, 4.0, text)
    s = env.summary("farmer", f)
    assert s["trade"]["written_review_count"] == 0
    assert s["trade"]["reviewed"] == "INSUFFICIENT_DATA"
    assert "REVIEWED" not in s["badges"]

    t = env.txn(f, b, "DELIVERED")
    env.rate(t, "buyer", b, "farmer", f, 4.0, "Prompt and honest")
    s = env.summary("farmer", f)
    assert s["trade"]["written_review_count"] == 1
    assert s["trade"]["reviewed"] == "REVIEWED"
    assert "REVIEWED" in s["badges"]
    assert "RATED" in s["badges"]           # 4 genuine ratings in total


def test_review_without_enough_ratings_is_reviewed_but_not_rated(env):
    f, b = env.farmer(), env.buyer()
    t = env.txn(f, b, "DELIVERED")
    env.rate(t, "buyer", b, "farmer", f, 5.0, "Great produce")
    s = env.summary("farmer", f)
    assert s["badges"] == ["REVIEWED"]
    assert s["trade"]["rating"]["average"] is None


def test_experience_threshold_and_completed_vs_incomplete_transactions(env):
    f, b = env.farmer(), env.buyer()
    for status in ("OFFER_ACCEPTED", "ORDER_CONFIRMED", "IN_TRANSIT", "DELIVERED",
                   "PAYMENT_PENDING", "PAYMENT_RECEIVED", "CANCELLED"):
        env.txn(f, b, status)
    s = env.summary("farmer", f)
    assert s["trade"]["completed_count"] == 0
    assert s["trade"]["experience"] == "INSUFFICIENT_DATA"
    assert "EXPERIENCE" not in s["badges"]

    env.txn(f, b, "COMPLETED")
    s = env.summary("farmer", f)
    assert s["trade"]["completed_count"] == 1
    assert s["trade"]["experience"] == "EXPERIENCE"
    assert s["badges"] == ["EXPERIENCE"]

    # Legacy lowercase rows count as COMPLETED, like transactions._normalize_status.
    env.txn(f, env.buyer(), "completed")
    s = env.summary("farmer", f)
    assert s["trade"]["completed_count"] == 2
    assert s["trade"]["distinct_counterparties"] == 2
    assert env.summary("buyer", b)["trade"]["completed_count"] == 1


def test_completed_vs_incomplete_trips(env):
    f, t, t_other = env.farmer(), env.transporter(), env.transporter()
    for status in ("REQUESTED", "MATCHED", "CONFIRMED", "PICKED_UP", "IN_TRANSIT", "CANCELLED"):
        env.trip(f, t, status=status)
    for who in (f, t):
        s = env.summary("farmer" if who is f else "transporter", who)
        assert s["logistics"]["completed_count"] == 0
        assert s["logistics"]["experience"] == "INSUFFICIENT_DATA"

    env.trip(f, t, status="DELIVERED")
    env.trip(f, t, status="COMPLETED")
    env.trip(f, t_other, status="DELIVERED")
    env.trip(f, None, status="DELIVERED")        # legacy trip with no transporter
    sf = env.summary("farmer", f)["logistics"]
    assert sf["completed_count"] == 4
    assert sf["distinct_counterparties"] == 2    # NULL transporter is not a counterparty
    st = env.summary("transporter", t)
    assert st["logistics"]["completed_count"] == 2
    assert st["logistics"]["distinct_counterparties"] == 1
    assert st["badges"] == ["EXPERIENCE"]


# ===========================================================================
# Role / id collisions (farmer 1, buyer 1 and transporter 1 all exist)
# ===========================================================================

def test_role_id_collisions_do_not_mix_signals(env):
    f, b, t = env.farmer(), env.buyer(), env.transporter()
    assert f.id == b.id == t.id == 1
    # Three ratings about BUYER 1 only.
    rated_txns(env, f, b, 3, ratee_role="buyer", rating=5.0, status="COMPLETED")
    sb = env.summary("buyer", b)
    sf = env.summary("farmer", f)
    assert sb["trade"]["rating"]["count"] == 3 and sb["trade"]["rating"]["state"] == "RATED"
    assert sf["trade"]["rating"]["count"] == 0
    # Transport review about TRANSPORTER 1 only; trip owned by farmer 1 but
    # served by transporter 2.
    t2 = env.transporter()
    trip = env.trip(f, t2, status="DELIVERED")
    env.transport_review(trip, "farmer", f, "transporter", t2, 5.0, "good")
    env.transport_review(env.trip(f, t, status="DELIVERED"), "farmer", f, "transporter", t, 3.0)
    assert env.summary("transporter", t)["logistics"]["rating"]["count"] == 1
    assert env.summary("transporter", t2)["logistics"]["rating"]["count"] == 1
    # TransportReview whose reviewee is transporter #1 must not count for farmer #1.
    assert env.summary("farmer", f)["logistics"]["rating"]["count"] == 0
    # Completed trips: farmer 1 owns both; transporter 1 only served one.
    assert env.summary("farmer", f)["logistics"]["completed_count"] == 2
    assert env.summary("transporter", t)["logistics"]["completed_count"] == 1


# ===========================================================================
# TransportReview / TripReview de-duplication
# ===========================================================================

def test_transport_review_and_trip_review_are_deduplicated(env):
    t, t2 = env.transporter(), env.transporter()
    f1, f2 = env.farmer(), env.farmer()
    r1 = env.trip(f1, t)      # reviewed through BOTH systems by the same farmer
    r2 = env.trip(f1, t)      # TripReview only
    r3 = env.trip(f2, t)      # TransportReview only
    env.transport_review(r1, "farmer", f1, "transporter", t, 5.0, "on time")
    env.trip_review(r1, f1, "TRANSPORTER", 1.0, "duplicate of the above")
    env.trip_review(r2, f1, "TRANSPORTER", 4.0, "careful handling")
    env.transport_review(r3, "farmer", f2, "transporter", t, 3.0)
    # Must NOT count: other review types, and another transporter's trip.
    env.trip_review(r3, f2, "JOURNEY", 1.0, "journey, not transporter")
    env.trip_review(r2, f1, "FPO", 1.0, "fpo")
    env.trip_review(env.trip(f2, t2), f2, "TRANSPORTER", 1.0, "someone else's transporter")

    s = env.summary("transporter", t)["logistics"]
    assert s["rating"]["count"] == 3
    assert s["rating"] == {"state": "RATED", "count": 3, "average": 4.0, "min_count": 3}
    assert s["written_review_count"] == 2          # "on time" + "careful handling"
    assert env.summary("transporter", t2)["logistics"]["rating"]["count"] == 1


def test_farmer_logistics_reviews_come_from_transporter_reviews_only(env):
    f, t = env.farmer(), env.transporter()
    trip = env.trip(f, t)
    env.transport_review(trip, "transporter", t, "farmer", f, 4.0, "Ready at pickup")
    env.trip_review(trip, f, "TRANSPORTER", 1.0, "farmer's own review is not about the farmer")
    s = env.summary("farmer", f)["logistics"]
    assert s["rating"]["count"] == 1 and s["written_review_count"] == 1
    assert s["reviewed"] == "REVIEWED"


# ===========================================================================
# Buyer verification
# ===========================================================================

@pytest.mark.parametrize("internal,tier,state", [
    ("PENDING", "INSUFFICIENT_VERIFICATION_EVIDENCE", "NOT_VERIFIED"),
    ("UNDER_REVIEW", "SELF_DECLARED", "NOT_VERIFIED"),
    ("VERIFIED", "PLATFORM_VERIFIED", "VERIFIED"),
    ("REJECTED", "VERIFICATION_REJECTED", "NOT_VERIFIED"),
    ("SUSPENDED", "VERIFICATION_REJECTED", "NOT_VERIFIED"),
])
def test_buyer_verification_state_mapping(env, internal, tier, state):
    b = env.buyer(verification_status="verified" if internal == "VERIFIED" else "pending")
    env.verification(b, internal)
    s = env.summary("buyer", b)
    assert s["verification"] == {"state": state, "tier": tier, "supported": True}
    assert ("VERIFIED" in s["badges"]) is (state == "VERIFIED")
    assert ("NOT_VERIFIED" in s["flags"]) is (state != "VERIFIED")
    # The raw internal value must never leak: a suspended buyer shows as rejected.
    assert "SUSPENDED" not in json.dumps(s)


def test_buyer_without_any_record_is_not_verified(env):
    s = env.summary("buyer", env.buyer())
    assert s["verification"]["tier"] == "INSUFFICIENT_VERIFICATION_EVIDENCE"
    assert s["flags"] == ["NOT_VERIFIED", "INSUFFICIENT_DATA"]


def test_legacy_verified_flag_without_backing_record_is_not_honoured(env):
    b = env.buyer(verification_status="verified")      # no BuyerVerification row
    s = env.summary("buyer", b)
    assert s["verification"]["state"] == "NOT_VERIFIED"
    assert "VERIFIED" not in s["badges"]


def test_admin_approve_and_suspend_flow_drives_trust_state(env):
    b = env.buyer()
    r = env.client.post("/buyer-verification", headers=env.auth(b, "buyer"),
                        json={"business_name": "B", "gst_number": "22GSTSECRET1Z5"})
    assert r.status_code == 200
    assert env.summary("buyer", b)["verification"]["tier"] == "SELF_DECLARED"
    assert env.client.patch(f"/buyer-verification/{b.id}/approve", headers=env.admin_auth()).status_code == 200
    assert env.summary("buyer", b)["badges"] == ["VERIFIED"]
    assert env.client.patch(f"/buyer-verification/{b.id}/suspend", headers=env.admin_auth()).status_code == 200
    s = env.summary("buyer", b)
    assert s["verification"]["state"] == "NOT_VERIFIED" and "VERIFIED" not in s["badges"]


def test_seeded_verified_buyer_gets_a_proper_backing_record(env):
    backed = env.buyer(email="seed-ok@demo", verification_status="verified")
    pending = env.buyer(email="seed-pending@demo", verification_status="pending")
    already = env.buyer(email="seed-has-row@demo", verification_status="verified")
    non_demo = env.buyer(email="real-user@example.test", verification_status="verified")
    env.verification(already, "VERIFIED", reviewed_by="real-admin")

    demo = {"seed-ok@demo", "seed-pending@demo", "seed-has-row@demo"}
    assert ensure_demo_buyer_verification_records(env.db, demo_emails=demo) == 1
    assert ensure_demo_buyer_verification_records(env.db, demo_emails=demo) == 0   # idempotent

    env.db.expire_all()
    rec = env.db.query(models.BuyerVerification).filter_by(buyer_id=backed.id).one()
    assert (rec.verification_status, rec.verification_method) == ("VERIFIED", "PLATFORM_VERIFIED")
    assert rec.reviewed_by == "demo-seed" and "Demo" in rec.verification_notes
    audit = env.db.query(models.BuyerVerificationAuditLog).filter_by(buyer_id=backed.id).one()
    assert audit.new_status == "VERIFIED"
    # untouched: pending demo buyer, buyer who already had a row, non-demo buyer
    assert env.db.query(models.BuyerVerification).filter_by(buyer_id=pending.id).first() is None
    assert env.db.query(models.BuyerVerification).filter_by(buyer_id=non_demo.id).first() is None
    assert env.db.query(models.BuyerVerification).filter_by(buyer_id=already.id).one().reviewed_by == "real-admin"

    assert env.summary("buyer", backed)["badges"] == ["VERIFIED"]
    assert env.summary("buyer", non_demo)["verification"]["state"] == "NOT_VERIFIED"


def test_default_demo_buyers_all_get_backing_records(env):
    for i, d in enumerate(DEMO_BUYERS):
        env.buyer(email=d["email"], company_name=d["company_name"],
                  verification_status=d["verification_status"])
    ensure_demo_buyer_verification_records(env.db)
    for b in env.db.query(models.Buyer).all():
        has = env.db.query(models.BuyerVerification).filter_by(buyer_id=b.id).first() is not None
        assert has is (b.verification_status == "verified")
        assert (env.summary("buyer", b)["verification"]["state"] == "VERIFIED") is (b.verification_status == "verified")


# ===========================================================================
# Payment history evidence
# ===========================================================================

def test_demo_payments_are_excluded_from_payment_history(env):
    f, b, other = env.farmer(), env.buyer(), env.buyer()
    for _ in range(5):
        env.payment(env.txn(f, b), b, f, "PAID", is_demo=True)
    ph = env.summary("buyer", b)["trade"]["payment_history"]
    assert ph == {"state": "INSUFFICIENT_DATA", "non_demo_paid_count": 0, "min_count": 3}

    env.payment(env.txn(f, b), b, f, "PAID", is_demo=False)
    env.payment(env.txn(f, b), b, f, "INITIATED", is_demo=False)     # not PAID
    env.payment(env.txn(f, other), other, f, "PAID", is_demo=False)  # someone else's
    assert env.summary("buyer", b)["trade"]["payment_history"]["non_demo_paid_count"] == 1
    env.payment(env.txn(f, b), b, f, "PAID", is_demo=False)
    assert env.summary("buyer", b)["trade"]["payment_history"]["state"] == "INSUFFICIENT_DATA"
    env.payment(env.txn(f, b), b, f, "PAID", is_demo=False)
    ph = env.summary("buyer", b)["trade"]["payment_history"]
    assert ph == {"state": "AVAILABLE", "non_demo_paid_count": 3, "min_count": 3}
    assert env.summary("farmer", f)["trade"]["payment_history"] is None


# ===========================================================================
# Privacy whitelist
# ===========================================================================

ALLOWED_KEYS = {
    "subject", "role", "id", "badges", "flags", "verification", "state", "tier", "supported",
    "trade", "logistics", "thresholds", "reason_codes", "code", "params",
    "completed_count", "distinct_counterparties", "experience", "rating", "count", "average",
    "min_count", "written_review_count", "reviewed", "payment_history", "non_demo_paid_count",
    "min_ratings_for_average", "min_written_reviews", "min_completed_for_experience",
    "min_non_demo_payments", "context", "min",
}


def _keys(node, acc):
    if isinstance(node, dict):
        for k, v in node.items():
            acc.add(k)
            _keys(v, acc)
    elif isinstance(node, list):
        for v in node:
            _keys(v, acc)
    return acc


def test_privacy_whitelist_and_no_secret_values(env):
    f = env.farmer(email="secret-farmer@leak.test", phone="+91-SECRETPHONE", rating=4.123)
    b = env.buyer(email="secret-buyer@leak.test", phone="+91-BUYERPHONE",
                  reliability_score=77.7, payment_history_score=66.6)
    t = env.transporter(email="secret-trans@leak.test", phone="+91-TRANSPHONE",
                        business_name="SecretHaulage", rating=3.21, rating_count=17)
    env.verification(b, "VERIFIED", gst_number="22SECRETGSTZ5", license_number="LIC-SECRET",
                     business_registration_number="CIN-SECRET", document_urls=["demo://secret.pdf"],
                     verification_notes="SECRET-ADMIN-NOTE", reviewed_by="secret-admin")
    for i in range(3):
        tx = env.txn(f, b, "COMPLETED", total=54321.0 + i)
        env.rate(tx, "buyer", b, "farmer", f, 4.0, "SECRET-REVIEW-TEXT")
        env.rate(tx, "farmer", f, "buyer", b, 5.0, "SECRET-REVIEW-TEXT-2")
        env.payment(tx, b, f, "PAID", is_demo=False)
        trip = env.trip(f, t, b)
        env.transport_review(trip, "farmer", f, "transporter", t, 5.0, "SECRET-TRANSPORT-COMMENT")
        env.transport_review(trip, "transporter", t, "farmer", f, 4.0, "SECRET-TRANSPORT-COMMENT-2")
    for role, who in (("farmer", f), ("buyer", b), ("transporter", t)):
        r = env.admin_get(f"/trust/{role}s/{who.id}")
        assert r.status_code == 200
        body = r.json()
        assert _keys(body, set()) <= ALLOWED_KEYS, _keys(body, set()) - ALLOWED_KEYS
        for secret in ("SECRET", "leak.test", "PHONE", "54321", "4.123", "77.7", "66.6", "3.21",
                       "password", "token", "email", "gst", "document", "transaction", "reviewer"):
            assert secret.lower() not in r.text.lower(), secret


# ===========================================================================
# Authentication / authorization
# ===========================================================================

def test_unauthenticated_requests_get_401(env):
    f = env.farmer()
    for path in ("/trust/me", f"/trust/farmers/{f.id}", "/trust/buyers/1", "/trust/transporters/1"):
        assert env.get(path).status_code == 401
        assert env.get(path, {"Authorization": "Bearer not-a-token"}).status_code == 401


def test_me_returns_own_summary_and_admin_has_none(env):
    f, b, t = env.farmer(), env.buyer(), env.transporter()
    for role, who in (("farmer", f), ("buyer", b), ("transporter", t)):
        r = env.get("/trust/me", env.auth(who, role))
        assert r.status_code == 200
        assert r.json()["subject"] == {"role": role, "id": who.id}
    r = env.get("/trust/me", env.admin_auth())
    assert r.status_code == 404 and r.json()["detail"] == "Trust profile not found"


def test_unauthorized_is_identical_to_nonexistent(env):
    fA, tB = env.farmer(), env.transporter()
    unauthorized = env.get(f"/trust/farmers/{fA.id}", env.auth(tB, "transporter"))
    nonexistent = env.get("/trust/farmers/9999", env.auth(tB, "transporter"))
    assert unauthorized.status_code == nonexistent.status_code == 404
    assert unauthorized.json() == nonexistent.json() == {"detail": "Trust profile not found"}
    # Same for a nonexistent subject the viewer would otherwise be allowed to see.
    assert env.get("/trust/buyers/9999", env.auth(fA, "farmer")).json() == nonexistent.json()


def test_full_visibility_matrix(env):
    fA, fB = env.farmer(), env.farmer()
    bA, bB = env.buyer(), env.buyer()
    t1, t2 = env.transporter(), env.transporter()
    env.trip(fA, t1, bA, status="CONFIRMED")          # the only relationship
    viewers = {"admin": None, "fA": (fA, "farmer"), "fB": (fB, "farmer"), "bA": (bA, "buyer"),
               "bB": (bB, "buyer"), "t1": (t1, "transporter"), "t2": (t2, "transporter")}
    subjects = {"fA": ("farmer", fA), "fB": ("farmer", fB), "bA": ("buyer", bA),
                "bB": ("buyer", bB), "t1": ("transporter", t1), "t2": ("transporter", t2)}
    allowed = {
        "admin": {"fA", "fB", "bA", "bB", "t1", "t2"},
        "fA": {"fA", "fB", "bA", "bB", "t1"},
        "fB": {"fA", "fB", "bA", "bB"},
        "bA": {"fA", "fB", "bA", "t1"},
        "bB": {"fA", "fB", "bB"},
        "t1": {"fA", "t1"},
        "t2": {"t2"},
    }
    for vname, viewer in viewers.items():
        headers = env.admin_auth() if viewer is None else env.auth(*viewer)
        for sname, (role, subj) in subjects.items():
            r = env.get(f"/trust/{role}s/{subj.id}", headers)
            expected = 200 if sname in allowed[vname] else 404
            assert r.status_code == expected, (vname, sname, r.status_code)
            if expected == 404:
                assert r.json() == {"detail": "Trust profile not found"}
            else:
                assert r.json()["subject"] == {"role": role, "id": subj.id}


def test_id_overlap_cannot_be_used_to_reach_another_role(env):
    """Buyer #1 and transporter #1 share an id; passing as one must not
    grant the other's relationship-based visibility."""
    f, t = env.farmer(), env.transporter()
    b = env.buyer()
    assert t.id == b.id == 1
    env.trip(f, t, None, status="DELIVERED")           # t is assigned to f; b is not related
    assert env.get(f"/trust/farmers/{f.id}", env.auth(t, "transporter")).status_code == 200
    # buyer #1 may see farmers (public directory) but NOT transporter #1.
    assert env.get(f"/trust/transporters/{t.id}", env.auth(b, "buyer")).status_code == 404


def test_trust_summary_service_is_read_only_and_none_for_unknown(env):
    assert trust_summary.build_trust_summary(env.db, "farmer", 12345) is None
    assert trust_summary.build_trust_summary(env.db, "admin", 1) is None


# ===========================================================================
# Regression: existing verification / rating endpoints
# ===========================================================================

def test_public_buyer_verification_no_longer_leaks_private_details(env):
    b = env.buyer(verification_status="verified")
    env.verification(
        b, "VERIFIED", business_name="Secret Biz Pvt", gst_number="22GSTSECRET1Z5",
        license_number="LIC-SECRET", business_registration_number="CIN-SECRET",
        document_urls=["demo://secret-doc.pdf"], verification_notes="SECRET-ADMIN-NOTE",
        verification_method="PLATFORM_VERIFIED", reviewed_by="secret-admin",
        verified_at=dt.datetime(2026, 1, 2, 3, 4, 5))
    r = env.get(f"/buyer-verification/{b.id}")           # no auth: still public
    assert r.status_code == 200
    body = r.json()
    assert set(body) == {"buyer_id", "display_status", "display_label",
                         "display_description", "verified_at"}
    assert body["display_status"] == "PLATFORM_VERIFIED" and body["verified_at"] is not None
    for secret in ("SECRET", "GST", "LIC-", "CIN-", "demo://", "document", "reviewed_by"):
        assert secret.lower() not in r.text.lower(), secret


def test_public_buyer_verification_hides_suspension_and_stale_verified_at(env):
    b = env.buyer()
    env.verification(b, "SUSPENDED", verified_at=dt.datetime(2026, 1, 2), verification_notes="fraud?")
    body = env.get(f"/buyer-verification/{b.id}").json()
    assert body["display_status"] == "VERIFICATION_REJECTED"
    assert body["verified_at"] is None
    assert "SUSPENDED" not in json.dumps(body) and "fraud" not in json.dumps(body)
    assert env.get("/buyer-verification/9999").status_code == 404


def test_owner_and_admin_verification_views_remain_complete(env):
    b = env.buyer()
    env.verification(b, "UNDER_REVIEW", gst_number="22GSTSECRET1Z5", document_urls=["demo://d.pdf"])
    mine = env.get("/buyer-verification/me", env.auth(b, "buyer"))
    assert mine.status_code == 200
    assert mine.json()["gst_number"] == "22GSTSECRET1Z5" and mine.json()["document_urls"] == ["demo://d.pdf"]
    listing = env.get("/buyer-verification?status=UNDER_REVIEW", env.admin_auth())
    assert listing.status_code == 200 and listing.json()[0]["gst_number"] == "22GSTSECRET1Z5"
    assert env.get("/buyer-verification", env.auth(b, "buyer")).status_code == 403
    badge = env.get(f"/buyer-verification/{b.id}/badge").json()
    assert set(badge) == {"buyer_id", "status", "label", "description"}


def test_existing_rating_endpoints_unchanged(env):
    f, b = env.farmer(), env.buyer()
    done, early = env.txn(f, b, "COMPLETED"), env.txn(f, b, "OFFER_ACCEPTED")
    h = env.auth(f, "farmer")
    ok = env.client.post("/ratings/farmer-rates-buyer", headers=h,
                         json={"transaction_id": done.id, "rating": 4, "review": "fine"})
    assert ok.status_code == 200 and ok.json()["ratee_role"] == "buyer"
    assert env.client.post("/ratings/farmer-rates-buyer", headers=h,
                           json={"transaction_id": done.id, "rating": 4}).status_code == 409
    assert env.client.post("/ratings/farmer-rates-buyer", headers=h,
                           json={"transaction_id": early.id, "rating": 4}).status_code == 400
    listing = env.get(f"/ratings/for-buyer/{b.id}").json()
    assert set(listing) == {"buyer_id", "total_ratings", "average_rating", "ratings"}
    assert listing["total_ratings"] == 1 and listing["average_rating"] == 4.0
    # ...and the new summary sees the same row without any write having happened.
    assert env.summary("buyer", b)["trade"]["rating"]["count"] == 1
