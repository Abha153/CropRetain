"""
Priority 8/9 — receipt generation and SHA-256 integrity.

CANONICAL FORM
--------------
The hash is computed over a canonical JSON serialisation of the receipt
payload: keys sorted, no insignificant whitespace, UTF-8, `ensure_ascii`
off so text is byte-identical regardless of how it was entered. This
matters because a hash is only useful if the SAME logical receipt always
produces the SAME bytes -- otherwise verification fails spuriously on a
dict-ordering difference and the whole mechanism is worthless.

`receipt_version` is part of the hashed payload. If the canonical form
ever changes, previously issued receipts keep verifying against the
algorithm they were generated with, rather than all silently breaking.

WHAT SHA-256 PROVES HERE
------------------------
That the stored receipt content has not been modified since generation.
NOT that the underlying transaction genuinely occurred. Any UI or
document wording must preserve that distinction -- see `INTEGRITY_NOTE`.
"""
import datetime as dt
import hashlib
import json
from typing import Optional

from sqlalchemy.orm import Session

from app import models

RECEIPT_VERSION = 1
HASH_ALGORITHM = "SHA-256"

INTEGRITY_NOTE = (
    "This SHA-256 hash proves that the contents of this receipt have not "
    "been altered since it was generated. It does not, on its own, prove "
    "that the underlying transaction took place."
)


def _iso(value: Optional[dt.datetime]) -> Optional[str]:
    """UTC ISO-8601. Presentation formatting (e.g. '15 Sep 2026, 3:15 PM')
    is the frontend's job -- a localised string must never enter the hashed
    payload, or the same receipt would hash differently per locale."""
    return value.isoformat() + "Z" if value else None


def canonical_json(payload: dict) -> str:
    """Deterministic serialisation -- the exact bytes that get hashed."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def compute_hash(payload: dict) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def build_payload(db: Session, txn: models.Transaction) -> dict:
    """Snapshot the real transaction facts. Nothing here is invented: any
    value the database genuinely doesn't have is recorded as None rather
    than filled with a plausible-looking default."""
    farmer = db.query(models.Farmer).filter_by(id=txn.farmer_id).first()
    buyer = db.query(models.Buyer).filter_by(id=txn.buyer_id).first()
    payment = (
        db.query(models.Payment)
        .filter_by(transaction_id=txn.id)
        .order_by(models.Payment.id.desc())
        .first()
    )
    transport = (
        db.query(models.TransportRequest)
        .filter_by(transaction_id=txn.id)
        .order_by(models.TransportRequest.id.desc())
        .first()
    )
    # Prefer the negotiated/agreed transport price over any earlier
    # estimate -- the receipt must record what was actually agreed.
    transport_cost = None
    if transport is not None:
        transport_cost = (
            transport.agreed_price
            if transport.agreed_price is not None
            else transport.estimated_cost
        )

    events = (
        db.query(models.TransactionEvent)
        .filter_by(transaction_id=txn.id)
        .order_by(models.TransactionEvent.created_at.asc(), models.TransactionEvent.id.asc())
        .all()
    )

    return {
        "receipt_version": RECEIPT_VERSION,
        "transaction_id": txn.id,
        "supplier": {"id": txn.farmer_id, "name": farmer.name if farmer else None},
        "buyer": {"id": txn.buyer_id, "name": buyer.company_name if buyer else None},
        "commodity": txn.crop if hasattr(txn, "crop") else None,
        "quantity_kg": txn.quantity_kg,
        "agreed_price_per_kg": txn.final_price_per_kg,
        "sale_amount": txn.total_amount,
        "transport_cost": transport_cost,
        "total_amount": (
            round(txn.total_amount + transport_cost, 2)
            if transport_cost is not None else txn.total_amount
        ),
        "market_used": txn.market_used or None,
        "transaction_status": txn.status,
        "payment_status": payment.status if payment else None,
        "transaction_created_at": _iso(txn.created_at),
        "events": [
            {
                "event_type": e.event_type,
                "performed_by": e.performed_by,
                "created_at": _iso(e.created_at),
            }
            for e in events
        ],
    }


def generate_receipt(db: Session, txn: models.Transaction) -> models.Receipt:
    """Create and persist a receipt for a transaction.

    Idempotent per transaction: an existing receipt is returned unchanged
    rather than regenerated, because reissuing would produce a new
    `generated_at` (and therefore a new hash) for what is supposed to be a
    fixed, already-issued document.
    """
    existing = db.query(models.Receipt).filter_by(transaction_id=txn.id).first()
    if existing:
        return existing

    payload = build_payload(db, txn)
    generated_at = dt.datetime.utcnow()
    seq = db.query(models.Receipt).count() + 1
    receipt_id = f"CW-RCPT-{seq:06d}"

    # generated_at and receipt_id are part of the hashed payload so they
    # are covered by the integrity check too -- a receipt whose issue time
    # or identifier was altered must fail verification.
    payload["receipt_id"] = receipt_id
    payload["generated_at"] = _iso(generated_at)

    receipt = models.Receipt(
        receipt_id=receipt_id,
        transaction_id=txn.id,
        receipt_version=RECEIPT_VERSION,
        payload=payload,
        hash_algorithm=HASH_ALGORITHM,
        hash_value=compute_hash(payload),
        generated_at=generated_at,
    )
    db.add(receipt)
    db.flush()

    db.add(models.TransactionEvent(
        transaction_id=txn.id,
        event_type="RECEIPT_GENERATED",
        description=f"Receipt {receipt_id} generated",
        performed_by="system",
        event_metadata={"receipt_id": receipt_id, "hash_algorithm": HASH_ALGORITHM},
    ))
    db.commit()
    db.refresh(receipt)
    return receipt


def verify_receipt(receipt: models.Receipt) -> dict:
    """Recompute the hash over the stored payload and compare.

    A mismatch means the stored receipt content no longer matches the hash
    recorded when it was issued -- i.e. the record was altered after the
    fact (or was written by a different canonical-form version).
    """
    recomputed = compute_hash(receipt.payload)
    ok = recomputed == receipt.hash_value
    return {
        "receipt_id": receipt.receipt_id,
        "transaction_id": receipt.transaction_id,
        "hash_algorithm": receipt.hash_algorithm,
        "stored_hash": receipt.hash_value,
        "recomputed_hash": recomputed,
        "integrity_verified": ok,
        "result": "INTEGRITY_VERIFIED" if ok else "INTEGRITY_MISMATCH",
        "note": INTEGRITY_NOTE,
    }


def render_receipt_text(receipt: models.Receipt) -> str:
    """Plain-text downloadable receipt document.

    Deliberately text/plain rather than a PDF: adding a PDF engine would
    mean a new runtime dependency for no gain in what the receipt actually
    has to do (be readable, be downloadable, and be exactly the content
    that was hashed). The hash covers the JSON payload, not this rendering.
    """
    p = receipt.payload
    lines = [
        "CropRetain Transaction Receipt",
        "=" * 46,
        f"Receipt ID        : {p.get('receipt_id')}",
        f"Transaction ID    : {p.get('transaction_id')}",
        f"Generated at (UTC): {p.get('generated_at')}",
        "",
        f"Supplier          : {(p.get('supplier') or {}).get('name') or '-'}",
        f"Buyer             : {(p.get('buyer') or {}).get('name') or '-'}",
        f"Commodity         : {p.get('commodity') or '-'}",
        f"Quantity (kg)     : {p.get('quantity_kg')}",
        f"Agreed price/kg   : {p.get('agreed_price_per_kg')}",
        f"Sale amount       : {p.get('sale_amount')}",
        f"Transport cost    : {p.get('transport_cost') if p.get('transport_cost') is not None else 'Not recorded'}",
        f"Total amount      : {p.get('total_amount')}",
        f"Market used       : {p.get('market_used') or '-'}",
        f"Transaction status: {p.get('transaction_status')}",
        f"Payment status    : {p.get('payment_status') or 'Not recorded'}",
        "",
        "Transaction events",
        "-" * 46,
    ]
    for e in p.get("events", []):
        lines.append(f"  {e.get('created_at')}  {e.get('event_type')}  ({e.get('performed_by') or '-'})")
    if not p.get("events"):
        lines.append("  (no events recorded)")
    lines += [
        "",
        f"{receipt.hash_algorithm}: {receipt.hash_value}",
        "",
        INTEGRITY_NOTE,
    ]
    return "\n".join(lines)
