"""
Priority 8/9 — receipt endpoints.

Access is restricted to the two parties on the transaction (and admins):
a receipt contains counterparty names and amounts, so it is not public.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.auth_utils import get_current_user
from app.services import receipt_service

router = APIRouter(prefix="/receipts", tags=["receipts"])

# Receipts are issued for transactions that have actually reached a
# settled state. Generating one for an in-flight transaction would produce
# a "receipt" for something that hasn't happened yet.
RECEIPTABLE_STATUSES = {"COMPLETED", "PAYMENT_RECEIVED", "DELIVERED"}


def _txn_or_404(db: Session, transaction_id: int) -> models.Transaction:
    txn = db.query(models.Transaction).filter_by(id=transaction_id).first()
    if not txn:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return txn


def _authorize(current, txn: models.Transaction):
    """Only the farmer, the buyer, or an admin may see this receipt."""
    role, user = current["role"], current["user"]
    if role == "admin":
        return
    if role == "farmer" and txn.farmer_id == user.id:
        return
    if role == "buyer" and txn.buyer_id == user.id:
        return
    raise HTTPException(status_code=403, detail="Not a party to this transaction")


@router.post("/transaction/{transaction_id}")
def generate(transaction_id: int, db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Generate (or return the existing) receipt for a completed transaction."""
    txn = _txn_or_404(db, transaction_id)
    _authorize(current, txn)
    if txn.status not in RECEIPTABLE_STATUSES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Transaction is '{txn.status}' -- a receipt is only issued once it "
                f"reaches one of: {', '.join(sorted(RECEIPTABLE_STATUSES))}."
            ),
        )
    receipt = receipt_service.generate_receipt(db, txn)
    return _out(receipt)


@router.get("/transaction/{transaction_id}")
def get_for_transaction(transaction_id: int, db: Session = Depends(get_db), current=Depends(get_current_user)):
    txn = _txn_or_404(db, transaction_id)
    _authorize(current, txn)
    receipt = db.query(models.Receipt).filter_by(transaction_id=transaction_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="No receipt generated for this transaction yet")
    return _out(receipt)


@router.get("/{receipt_id}/download", response_class=PlainTextResponse)
def download(receipt_id: str, db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Downloadable receipt document (text/plain) -- a real file, not a UI card."""
    receipt = db.query(models.Receipt).filter_by(receipt_id=receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    _authorize(current, _txn_or_404(db, receipt.transaction_id))
    return PlainTextResponse(
        receipt_service.render_receipt_text(receipt),
        headers={"Content-Disposition": f'attachment; filename="{receipt_id}.txt"'},
    )


@router.get("/{receipt_id}/verify")
def verify(receipt_id: str, db: Session = Depends(get_db), current=Depends(get_current_user)):
    """Recompute the SHA-256 over the stored canonical payload and compare
    it with the hash recorded at generation time."""
    receipt = db.query(models.Receipt).filter_by(receipt_id=receipt_id).first()
    if not receipt:
        raise HTTPException(status_code=404, detail="Receipt not found")
    _authorize(current, _txn_or_404(db, receipt.transaction_id))
    return receipt_service.verify_receipt(receipt)


def _out(receipt: models.Receipt) -> dict:
    return {
        "receipt_id": receipt.receipt_id,
        "transaction_id": receipt.transaction_id,
        "receipt_version": receipt.receipt_version,
        "hash_algorithm": receipt.hash_algorithm,
        "hash_value": receipt.hash_value,
        "generated_at": receipt.generated_at.isoformat() + "Z" if receipt.generated_at else None,
        "payload": receipt.payload,
        "note": receipt_service.INTEGRITY_NOTE,
    }
