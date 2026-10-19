"""
Payment tracking — Phase 11.

Simulated payment system for hackathon demo.
All payments are explicitly labelled as demo/simulated.
No real payment gateway is integrated.

Payment lifecycle:
    PENDING → DUE → INITIATED → PAID
    PENDING → FAILED
    PENDING/DUE → DISPUTED
"""
import datetime as dt
import json
import logging
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer, require_buyer, require_admin, get_current_user
from app.routers.transactions import _add_event, _normalize_status
from app.services import razorpay_service as rzp

logger = logging.getLogger("cropretain.payments")

router = APIRouter(prefix="/payments", tags=["payments"])

DEMO_DISCLAIMER = "Demo simulated payment — not a real financial transaction."


def _payment_ref() -> str:
    return f"CW-PAY-{dt.date.today().year}-{secrets.token_hex(4).upper()}"


@router.get("/mine")
def my_payments(current=Depends(get_current_user), db: Session = Depends(get_db)):
    """Both farmers and buyers can see payments they are party to."""
    role = current["role"]
    user = current["user"]
    if role == "farmer":
        payments = (db.query(models.Payment)
                    .filter(models.Payment.farmer_id == user.id)
                    .order_by(models.Payment.created_at.desc()).all())
    elif role == "buyer":
        payments = (db.query(models.Payment)
                    .filter(models.Payment.buyer_id == user.id)
                    .order_by(models.Payment.created_at.desc()).all())
    else:
        payments = []
    return payments


@router.get("/transaction/{txn_id}", response_model=Optional[schemas.PaymentOut])
def payment_for_transaction(
    txn_id: int,
    current=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get the current payment record for a transaction."""
    txn = db.query(models.Transaction).filter(models.Transaction.id == txn_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    role, user = current["role"], current["user"]
    if role == "farmer" and txn.farmer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if role == "buyer" and txn.buyer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")

    return (db.query(models.Payment)
            .filter(models.Payment.transaction_id == txn_id)
            .order_by(models.Payment.created_at.desc())
            .first())


@router.get("/{payment_id}", response_model=schemas.PaymentOut)
def get_payment(payment_id: int, current=Depends(get_current_user), db: Session = Depends(get_db)):
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    role, user = current["role"], current["user"]
    if role == "farmer" and payment.farmer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if role == "buyer" and payment.buyer_id != user.id:
        raise HTTPException(status_code=403, detail="Access denied")
    return payment


@router.post("", response_model=schemas.PaymentOut)
def create_payment(
    payload: schemas.PaymentCreate,
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    """Buyer creates a payment record for a transaction."""
    txn = db.query(models.Transaction).filter(models.Transaction.id == payload.transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if txn.buyer_id != buyer.id:
        raise HTTPException(status_code=403, detail="You can only create payments for your own transactions")

    existing = db.query(models.Payment).filter(
        models.Payment.transaction_id == payload.transaction_id,
        models.Payment.payment_status.notin_(["FAILED", "DISPUTED"])
    ).first()
    if existing:
        raise HTTPException(status_code=400, detail="A payment record already exists for this transaction")

    # The charged amount is always the server-side transaction total. A
    # client-supplied amount is only accepted if it matches (never used to set it).
    if payload.amount is not None and abs(float(payload.amount) - float(txn.total_amount)) > 0.01:
        raise HTTPException(status_code=400, detail="Amount does not match the transaction total")

    payment = models.Payment(
        transaction_id=payload.transaction_id,
        buyer_id=buyer.id,
        farmer_id=txn.farmer_id,
        amount=txn.total_amount,
        payment_method=payload.payment_method,
        notes=f"{payload.notes or ''} {DEMO_DISCLAIMER}".strip(),
        payment_due_date=payload.payment_due_date,
        payment_status="PENDING",
        is_demo=True,
    )
    db.add(payment)
    db.commit()
    db.refresh(payment)
    return payment


@router.patch("/{payment_id}/initiate", response_model=schemas.PaymentOut)
def initiate_payment(
    payment_id: int,
    payment_method: str = "UPI",
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    """Buyer marks payment as initiated (simulated)."""
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.buyer_id != buyer.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if payment.payment_status not in ("PENDING", "DUE"):
        raise HTTPException(status_code=400, detail=f"Cannot initiate from {payment.payment_status} status")
    if rzp.is_configured():
        raise HTTPException(
            status_code=409,
            detail="Razorpay is enabled: pay via POST /payments/{id}/razorpay/order instead of the simulated flow",
        )

    payment.payment_status = "INITIATED"
    payment.payment_method = payment_method
    payment.payment_reference = _payment_ref()
    payment.initiated_at = dt.datetime.utcnow()
    payment.notes = f"{payment.notes or ''} {DEMO_DISCLAIMER}".strip()

    # Advance transaction status
    txn = db.query(models.Transaction).filter(models.Transaction.id == payment.transaction_id).first()
    if txn and _normalize_status(txn.status) in ("DELIVERED", "PAYMENT_PENDING"):
        txn.status = "PAYMENT_INITIATED"
        txn.updated_at = dt.datetime.utcnow()
        _add_event(db, txn.id, "PAYMENT_INITIATED",
                   f"Payment of ₹{payment.amount:,.0f} initiated via {payment_method} (Demo simulated)",
                   "buyer", buyer.id)
    db.commit()
    db.refresh(payment)
    return payment


@router.patch("/{payment_id}/confirm-received", response_model=schemas.PaymentOut)
def confirm_payment_received(
    payment_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Farmer confirms they received the payment (simulated)."""
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.farmer_id != farmer.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if payment.payment_status != "INITIATED":
        raise HTTPException(status_code=400, detail=f"Cannot confirm from {payment.payment_status} status")

    payment.payment_status = "PAID"
    payment.received_at = dt.datetime.utcnow()

    # Advance transaction to PAYMENT_RECEIVED then COMPLETED
    txn = db.query(models.Transaction).filter(models.Transaction.id == payment.transaction_id).first()
    if txn:
        txn.status = "PAYMENT_RECEIVED"
        txn.updated_at = dt.datetime.utcnow()
        _add_event(db, txn.id, "PAYMENT_RECEIVED",
                   f"Payment of ₹{payment.amount:,.0f} confirmed received by farmer (Demo simulated)",
                   "farmer", farmer.id)
    db.commit()
    db.refresh(payment)
    return payment


@router.patch("/{payment_id}/complete-transaction")
def complete_transaction(
    payment_id: int,
    farmer: models.Farmer = Depends(require_farmer),
    db: Session = Depends(get_db),
):
    """Farmer marks transaction as fully completed after payment."""
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.farmer_id != farmer.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if payment.payment_status != "PAID":
        raise HTTPException(status_code=400, detail="Payment must be PAID before completing transaction")

    txn = db.query(models.Transaction).filter(models.Transaction.id == payment.transaction_id).first()
    if txn and txn.status == "PAYMENT_RECEIVED":
        txn.status = "COMPLETED"
        txn.updated_at = dt.datetime.utcnow()
        _add_event(db, txn.id, "COMPLETED",
                   "Transaction completed. All parties fulfilled their obligations.",
                   "farmer", farmer.id)
    db.commit()
    return {"completed": True, "transaction_id": payment.transaction_id}


# ---------------------------------------------------------------------------
# Razorpay gateway (test mode when rzp_test_* credentials are configured)
# ---------------------------------------------------------------------------

_PAYABLE_TXN_STATUSES = ("DELIVERED", "PAYMENT_PENDING", "PAYMENT_INITIATED")


class RazorpayVerifyIn(BaseModel):
    razorpay_order_id: str = Field(min_length=1, max_length=64)
    razorpay_payment_id: str = Field(min_length=1, max_length=64)
    razorpay_signature: str = Field(min_length=1, max_length=256)


def _amount_matches_transaction(payment: models.Payment, txn: models.Transaction) -> bool:
    return rzp.to_paise(payment.amount) == rzp.to_paise(txn.total_amount)


def _mark_gateway_paid(db: Session, payment: models.Payment, gateway_payment_id: str, source: str) -> bool:
    """Idempotently mark a gateway payment PAID. Returns True only if this call
    changed state; a repeat (verify then webhook, or a webhook retry) is a no-op."""
    if payment.payment_status == "PAID":
        return False
    payment.payment_status = "PAID"
    payment.gateway_payment_id = gateway_payment_id
    payment.payment_method = payment.payment_method or "Razorpay"
    payment.received_at = dt.datetime.utcnow()
    txn = db.query(models.Transaction).filter(models.Transaction.id == payment.transaction_id).first()
    if txn and _normalize_status(txn.status) in _PAYABLE_TXN_STATUSES:
        txn.status = "PAYMENT_RECEIVED"
        txn.updated_at = dt.datetime.utcnow()
        _add_event(db, txn.id, "PAYMENT_RECEIVED",
                   f"Payment of ₹{payment.amount:,.0f} confirmed by Razorpay ({rzp.mode()} mode, via {source})",
                   "system", None)
    return True


@router.get("/gateway/status")
def gateway_status(current=Depends(get_current_user)):
    """Whether Razorpay is available -- never exposes the secret."""
    return {
        "provider": "razorpay",
        "available": rzp.is_configured(),
        "mode": rzp.mode(),
        "key_id": settings.razorpay_key_id if rzp.is_configured() else None,
        "webhook_configured": bool(settings.razorpay_webhook_secret),
    }


@router.post("/{payment_id}/razorpay/order")
def create_razorpay_order(
    payment_id: int,
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    """Create (or reuse) a Razorpay order for a payment. Amount is server-side."""
    if not rzp.is_configured():
        raise HTTPException(status_code=503, detail="Razorpay is not configured (payments unavailable)")
    payment = db.query(models.Payment).filter(models.Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    if payment.buyer_id != buyer.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if payment.payment_status not in ("PENDING", "DUE", "INITIATED"):
        raise HTTPException(status_code=400, detail=f"Cannot pay from {payment.payment_status} status")
    txn = db.query(models.Transaction).filter(models.Transaction.id == payment.transaction_id).first()
    if not txn or txn.buyer_id != buyer.id:
        raise HTTPException(status_code=403, detail="Access denied")
    if _normalize_status(txn.status) not in _PAYABLE_TXN_STATUSES:
        raise HTTPException(status_code=400, detail=f"Transaction is not payable in status {txn.status}")
    if not _amount_matches_transaction(payment, txn):
        raise HTTPException(status_code=409, detail="Payment amount no longer matches the transaction total")

    if not (payment.gateway == "razorpay" and payment.gateway_order_id):
        try:
            order = rzp.create_order(
                payment.amount,
                receipt=f"cr-pay-{payment.id}",
                notes={"payment_id": str(payment.id), "transaction_id": str(txn.id)},
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        except rzp.RazorpayError as exc:
            raise HTTPException(status_code=502, detail=str(exc))
        payment.gateway = "razorpay"
        payment.gateway_order_id = order["id"]
        payment.payment_status = "INITIATED"
        payment.payment_method = "Razorpay"
        payment.initiated_at = dt.datetime.utcnow()
        payment.is_demo = False
        if _normalize_status(txn.status) in ("DELIVERED", "PAYMENT_PENDING"):
            txn.status = "PAYMENT_INITIATED"
            txn.updated_at = dt.datetime.utcnow()
            _add_event(db, txn.id, "PAYMENT_INITIATED",
                       f"Razorpay order created for ₹{payment.amount:,.0f} ({rzp.mode()} mode)",
                       "buyer", buyer.id)
        db.commit()
        db.refresh(payment)

    return {
        "payment_id": payment.id,
        "order_id": payment.gateway_order_id,
        "amount_paise": rzp.to_paise(payment.amount),
        "currency": rzp.CURRENCY,
        "key_id": settings.razorpay_key_id,
        "mode": rzp.mode(),
    }


@router.post("/razorpay/verify", response_model=schemas.PaymentOut)
def verify_razorpay_payment(
    payload: RazorpayVerifyIn,
    buyer: models.Buyer = Depends(require_buyer),
    db: Session = Depends(get_db),
):
    """Verify the checkout signature server-side. State changes only if the
    HMAC is valid for an order this buyer owns -- the client's say-so alone
    never marks anything paid."""
    payment = (db.query(models.Payment)
               .filter(models.Payment.gateway_order_id == payload.razorpay_order_id,
                       models.Payment.gateway == "razorpay").first())
    if not payment or payment.buyer_id != buyer.id:
        raise HTTPException(status_code=404, detail="Payment not found")
    if not rzp.verify_checkout_signature(payload.razorpay_order_id, payload.razorpay_payment_id,
                                         payload.razorpay_signature):
        raise HTTPException(status_code=400, detail="Invalid payment signature")
    txn = db.query(models.Transaction).filter(models.Transaction.id == payment.transaction_id).first()
    if not txn or not _amount_matches_transaction(payment, txn):
        raise HTTPException(status_code=409, detail="Payment amount no longer matches the transaction total")
    if payment.payment_status in ("FAILED", "DISPUTED"):
        raise HTTPException(status_code=400, detail=f"Cannot verify from {payment.payment_status} status")
    _mark_gateway_paid(db, payment, payload.razorpay_payment_id, "checkout verification")
    db.commit()
    db.refresh(payment)
    return payment


@router.post("/razorpay/webhook")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    """Razorpay webhook. Signature is checked against the RAW body; events are
    deduplicated by X-Razorpay-Event-Id so retries never re-apply."""
    raw = await request.body()
    signature = request.headers.get("X-Razorpay-Signature", "")
    if not rzp.verify_webhook_signature(raw, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
    try:
        event = json.loads(raw)
    except ValueError:
        raise HTTPException(status_code=400, detail="Malformed webhook body")

    event_id = request.headers.get("X-Razorpay-Event-Id", "")
    event_type = event.get("event", "") if isinstance(event, dict) else ""
    if not event_id:
        raise HTTPException(status_code=400, detail="Missing event id")

    try:
        db.add(models.PaymentWebhookEvent(provider="razorpay", event_id=event_id, event_type=event_type))
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"status": "duplicate_ignored"}

    entity = (((event.get("payload") or {}).get("payment") or {}).get("entity") or {})
    order_id = entity.get("order_id")
    pay_id = entity.get("id")
    if event_type not in ("payment.captured", "order.paid", "payment.failed") or not (order_id and pay_id):
        db.commit()
        return {"status": "ignored"}

    payment = (db.query(models.Payment)
               .filter(models.Payment.gateway_order_id == order_id,
                       models.Payment.gateway == "razorpay").first())
    if not payment:
        db.commit()
        return {"status": "unknown_order"}

    if event_type == "payment.failed":
        # Never downgrade a settled payment; a failed attempt can be retried on the same order.
        db.commit()
        return {"status": "failure_recorded_no_state_change"}

    txn = db.query(models.Transaction).filter(models.Transaction.id == payment.transaction_id).first()
    if (entity.get("currency") != rzp.CURRENCY
            or entity.get("amount") != rzp.to_paise(payment.amount)
            or not txn or not _amount_matches_transaction(payment, txn)):
        logger.warning("Razorpay webhook amount/currency mismatch for payment %s", payment.id)
        db.commit()
        return {"status": "rejected_amount_mismatch"}

    changed = _mark_gateway_paid(db, payment, pay_id, "webhook")
    db.commit()
    return {"status": "processed" if changed else "already_processed"}
