"""
Razorpay integration tests. No network: order creation is monkeypatched and
signatures are computed locally with the same HMAC scheme Razorpay documents.
"""
import hashlib
import hmac
import json
import os
import sys
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import auth_utils, models
from app.config import settings
from app.database import Base, get_db
from app.routers import payments
from app.services import razorpay_service as rzp

KEY_SECRET = "test_key_secret"
WEBHOOK_SECRET = "test_webhook_secret"


def _sign(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()


@pytest.fixture()
def env(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    farmer = models.Farmer(name="F", email="f@example.com", password_hash="x", location="Bilaspur")
    buyer = models.Buyer(company_name="B", email="b@example.com", password_hash="x", location="Raipur")
    other = models.Buyer(company_name="B2", email="b2@example.com", password_hash="x", location="Raipur")
    db.add_all([farmer, buyer, other])
    db.flush()
    txn = models.Transaction(farmer_id=farmer.id, buyer_id=buyer.id, final_price_per_kg=40,
                             quantity_kg=100, total_amount=4000, status="DELIVERED")
    db.add(txn)
    db.flush()
    payment = models.Payment(transaction_id=txn.id, buyer_id=buyer.id, farmer_id=farmer.id,
                             amount=4000, payment_status="PENDING")
    db.add(payment)
    db.commit()
    ids = SimpleNamespace(buyer=buyer.id, other=other.id, txn=txn.id, payment=payment.id)

    app = FastAPI()
    app.include_router(payments.router)

    def _db():
        s = Session()
        try:
            yield s
        finally:
            s.close()

    current = {"buyer_id": ids.buyer}
    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[auth_utils.require_buyer] = lambda: SimpleNamespace(id=current["buyer_id"])
    app.dependency_overrides[auth_utils.get_current_user] = lambda: {
        "role": "buyer", "user": SimpleNamespace(id=current["buyer_id"])}

    monkeypatch.setattr(settings, "razorpay_key_id", "rzp_test_abc")
    monkeypatch.setattr(settings, "razorpay_key_secret", KEY_SECRET)
    monkeypatch.setattr(settings, "razorpay_webhook_secret", WEBHOOK_SECRET)

    calls = []

    def fake_create_order(amount, receipt, notes=None):
        calls.append(amount)
        return {"id": "order_TEST1", "amount": rzp.to_paise(amount)}

    monkeypatch.setattr(rzp, "create_order", fake_create_order)

    yield SimpleNamespace(client=TestClient(app), db=db, ids=ids, current=current, calls=calls,
                          settings=settings)
    db.close()


def _make_order(env):
    r = env.client.post(f"/payments/{env.ids.payment}/razorpay/order")
    assert r.status_code == 200, r.text
    return r.json()


def _webhook(env, order_id="order_TEST1", pay_id="pay_1", amount=400000, currency="INR",
             event="payment.captured", event_id="evt_1", secret=WEBHOOK_SECRET):
    body = json.dumps({"event": event, "payload": {"payment": {"entity": {
        "id": pay_id, "order_id": order_id, "amount": amount, "currency": currency}}}}).encode()
    return env.client.post("/payments/razorpay/webhook", content=body, headers={
        "X-Razorpay-Signature": _sign(secret, body), "X-Razorpay-Event-Id": event_id})


def _payment(env):
    env.db.expire_all()
    return env.db.query(models.Payment).get(env.ids.payment)


def test_unavailable_without_credentials(env, monkeypatch):
    monkeypatch.setattr(settings, "razorpay_key_id", "")
    r = env.client.post(f"/payments/{env.ids.payment}/razorpay/order")
    assert r.status_code == 503
    assert env.client.get("/payments/gateway/status").json()["available"] is False


def test_order_uses_server_amount_and_hides_secret(env):
    data = _make_order(env)
    assert env.calls == [4000]
    assert data["amount_paise"] == 400000 and data["currency"] == "INR"
    assert "secret" not in json.dumps(data).lower()
    assert _payment(env).payment_status == "INITIATED"


def test_order_forbidden_for_other_buyer(env):
    env.current["buyer_id"] = env.ids.other
    assert env.client.post(f"/payments/{env.ids.payment}/razorpay/order").status_code == 403


def test_verify_rejects_invalid_signature(env):
    _make_order(env)
    r = env.client.post("/payments/razorpay/verify", json={
        "razorpay_order_id": "order_TEST1", "razorpay_payment_id": "pay_1",
        "razorpay_signature": "bad"})
    assert r.status_code == 400
    assert _payment(env).payment_status == "INITIATED"


def test_verify_valid_signature_marks_paid_once(env):
    _make_order(env)
    sig = _sign(KEY_SECRET, b"order_TEST1|pay_1")
    body = {"razorpay_order_id": "order_TEST1", "razorpay_payment_id": "pay_1", "razorpay_signature": sig}
    assert env.client.post("/payments/razorpay/verify", json=body).status_code == 200
    assert env.client.post("/payments/razorpay/verify", json=body).status_code == 200
    assert _payment(env).payment_status == "PAID"
    events = env.db.query(models.TransactionEvent).filter_by(event_type="PAYMENT_RECEIVED").count()
    assert events == 1
    assert env.db.query(models.Transaction).get(env.ids.txn).status == "PAYMENT_RECEIVED"


def test_webhook_invalid_signature_rejected(env):
    _make_order(env)
    assert _webhook(env, secret="wrong").status_code == 400
    assert _payment(env).payment_status == "INITIATED"


def test_webhook_processed_and_duplicate_event_ignored(env):
    _make_order(env)
    assert _webhook(env).json()["status"] == "processed"
    assert _webhook(env).json()["status"] == "duplicate_ignored"
    assert _payment(env).payment_status == "PAID"
    assert env.db.query(models.TransactionEvent).filter_by(event_type="PAYMENT_RECEIVED").count() == 1


def test_webhook_after_verify_is_idempotent(env):
    _make_order(env)
    sig = _sign(KEY_SECRET, b"order_TEST1|pay_1")
    env.client.post("/payments/razorpay/verify", json={
        "razorpay_order_id": "order_TEST1", "razorpay_payment_id": "pay_1", "razorpay_signature": sig})
    assert _webhook(env, event_id="evt_2").json()["status"] == "already_processed"
    assert env.db.query(models.TransactionEvent).filter_by(event_type="PAYMENT_RECEIVED").count() == 1


def test_webhook_amount_or_currency_mismatch_not_paid(env):
    _make_order(env)
    assert _webhook(env, amount=100, event_id="e_a").json()["status"] == "rejected_amount_mismatch"
    assert _webhook(env, currency="USD", event_id="e_b").json()["status"] == "rejected_amount_mismatch"
    assert _payment(env).payment_status == "INITIATED"


def test_webhook_failed_event_does_not_change_state(env):
    _make_order(env)
    _webhook(env, event="payment.failed", event_id="e_f")
    assert _payment(env).payment_status == "INITIATED"


def test_create_payment_amount_is_server_derived(env):
    env.db.query(models.Payment).delete()
    env.db.commit()
    bad = env.client.post("/payments", json={"transaction_id": env.ids.txn, "amount": 1})
    assert bad.status_code == 400
    ok = env.client.post("/payments", json={"transaction_id": env.ids.txn})
    assert ok.status_code == 200 and ok.json()["amount"] == 4000


def test_simulated_initiate_blocked_when_gateway_enabled(env):
    r = env.client.patch(f"/payments/{env.ids.payment}/initiate")
    assert r.status_code == 409
