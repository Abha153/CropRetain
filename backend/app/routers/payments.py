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
import secrets
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import models, schemas
from app.auth_utils import require_farmer, require_buyer, require_admin, get_current_user
from app.routers.transactions import _add_event, _normalize_status

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

    payment = models.Payment(
        transaction_id=payload.transaction_id,
        buyer_id=buyer.id,
        farmer_id=txn.farmer_id,
        amount=payload.amount,
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


