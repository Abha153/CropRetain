"""
Trust summary -- ONE reusable, read-only service that turns existing rows
into explainable marketplace trust signals.

Design rules (Phase C):
  * Independent signals, never a composite "trust score".
  * Everything is recomputed from source rows (Rating, TransportReview,
    TripReview, Transaction, TransportRequest, Payment, BuyerVerification).
  * The legacy stored fields -- Farmer.rating, Buyer.reliability_score,
    Buyer.payment_history_score, Transporter.rating / rating_count -- are
    NEVER read here. They carry model/seed defaults (4.5, 60/85, 60/90, 0.0)
    that look like a track record without any history behind them.
  * No new tables, no writes. Output contains only counts, averages and
    state labels -- no identities, ids of other records, amounts or text.

Definitions (single source of truth; change them here only):
  completed transaction : Transaction.status == COMPLETED (case-insensitive,
                          so legacy lowercase "completed" rows count).
  completed trip        : TransportRequest.status in DELIVERED / COMPLETED
                          (the two statuses on which transport reviews are
                          accepted in transport_negotiation.submit_review).
  genuine rating        : a Rating / TransportReview / TripReview row. All
                          three are only creatable by a participant of a
                          finished transaction/trip (enforced by their
                          routers), so no extra filtering is needed.
  written review        : a non-blank Rating.review / comment.
"""
from typing import Dict, List, Optional

from sqlalchemy import distinct, exists, func
from sqlalchemy.orm import Session

from app import models

# ---------------------------------------------------------------------------
# Product thresholds (approved for Phase C)
# ---------------------------------------------------------------------------
MIN_RATINGS_FOR_AVERAGE = 3
MIN_WRITTEN_REVIEWS = 1
MIN_COMPLETED_FOR_EXPERIENCE = 1
# Not specified by product; chosen to match the rating threshold.
MIN_NON_DEMO_PAYMENTS = 3

COMPLETED_TRANSACTION_STATUS = "COMPLETED"
COMPLETED_TRIP_STATUSES = ("DELIVERED", "COMPLETED")

SUBJECT_ROLES = ("farmer", "buyer", "transporter")

THRESHOLDS = {
    "min_ratings_for_average": MIN_RATINGS_FOR_AVERAGE,
    "min_written_reviews": MIN_WRITTEN_REVIEWS,
    "min_completed_for_experience": MIN_COMPLETED_FOR_EXPERIENCE,
    "min_non_demo_payments": MIN_NON_DEMO_PAYMENTS,
}


# ---------------------------------------------------------------------------
# Visibility
# ---------------------------------------------------------------------------

def can_view(db: Session, viewer_role: str, viewer_id: Optional[int],
             subject_role: str, subject_id: int) -> bool:
    """Who may see whose trust summary. Callers must answer a False here
    with the SAME response as a nonexistent subject (404)."""
    if viewer_role == "admin":
        return True
    if viewer_role == subject_role and viewer_id == subject_id:
        return True

    if subject_role == "buyer":
        # Buyers are a public marketplace directory for farmers.
        return viewer_role == "farmer"

    if subject_role == "farmer":
        if viewer_role in ("farmer", "buyer"):
            return True
        if viewer_role == "transporter":
            # Farmer identity is withheld from transporters until they have
            # claimed one of that farmer's requests (see transporters.py).
            return db.query(models.TransportRequest.id).filter(
                models.TransportRequest.farmer_id == subject_id,
                models.TransportRequest.transporter_id == viewer_id,
            ).first() is not None
        return False

    if subject_role == "transporter":
        # Only counterparties who actually have a request with them.
        if viewer_role == "farmer":
            party = models.TransportRequest.farmer_id
        elif viewer_role == "buyer":
            party = models.TransportRequest.buyer_id
        else:
            return False
        return db.query(models.TransportRequest.id).filter(
            party == viewer_id,
            models.TransportRequest.transporter_id == subject_id,
        ).first() is not None

    return False


# ---------------------------------------------------------------------------
# Signal builders
# ---------------------------------------------------------------------------

def _rating_signal(values: List[float]) -> dict:
    count = len(values)
    if count >= MIN_RATINGS_FOR_AVERAGE:
        return {
            "state": "RATED",
            "count": count,
            "average": round(sum(values) / count, 2),
            "min_count": MIN_RATINGS_FOR_AVERAGE,
        }
    # Below the threshold the average is withheld on purpose: one or two
    # ratings are anecdotes (and can identify the rater).
    return {
        "state": "INSUFFICIENT_DATA",
        "count": count,
        "average": None,
        "min_count": MIN_RATINGS_FOR_AVERAGE,
    }


def _context(ratings: List[float], written: int, completed: int,
             distinct_counterparties: int,
             payment_history: Optional[dict] = None) -> dict:
    return {
        "completed_count": completed,
        "distinct_counterparties": distinct_counterparties,
        "experience": ("EXPERIENCE" if completed >= MIN_COMPLETED_FOR_EXPERIENCE
                       else "INSUFFICIENT_DATA"),
        "rating": _rating_signal(ratings),
        "written_review_count": written,
        "reviewed": ("REVIEWED" if written >= MIN_WRITTEN_REVIEWS
                     else "INSUFFICIENT_DATA"),
        "payment_history": payment_history,
    }


def _is_written(text: Optional[str]) -> bool:
    return bool(text and text.strip())


def _trade_context(db: Session, role: str, subject_id: int) -> dict:
    """Farmer<->buyer trade: Rating rows received + completed Transactions."""
    rows = db.query(models.Rating.rating, models.Rating.review).filter(
        models.Rating.ratee_role == role,          # role-scoped: ids overlap across tables
        models.Rating.ratee_id == subject_id,
    ).all()
    ratings = [r.rating for r in rows]
    written = sum(1 for r in rows if _is_written(r.review))

    own = models.Transaction.farmer_id if role == "farmer" else models.Transaction.buyer_id
    other = models.Transaction.buyer_id if role == "farmer" else models.Transaction.farmer_id
    completed, counterparties = db.query(
        func.count(models.Transaction.id), func.count(distinct(other)),
    ).filter(
        own == subject_id,
        func.upper(models.Transaction.status) == COMPLETED_TRANSACTION_STATUS,
    ).one()

    payment = _payment_history(db, subject_id) if role == "buyer" else None
    return _context(ratings, written, completed or 0, counterparties or 0, payment)


def _payment_history(db: Session, buyer_id: int) -> dict:
    """Only genuine (non-demo) PAID payments count. Payment.is_demo is True
    for every payment the app can currently create, so today this is
    INSUFFICIENT_DATA by construction -- which is the honest answer."""
    paid = db.query(func.count(models.Payment.id)).filter(
        models.Payment.buyer_id == buyer_id,
        models.Payment.is_demo.is_(False),
        models.Payment.payment_status == "PAID",
    ).scalar() or 0
    return {
        "state": "AVAILABLE" if paid >= MIN_NON_DEMO_PAYMENTS else "INSUFFICIENT_DATA",
        "non_demo_paid_count": paid,
        "min_count": MIN_NON_DEMO_PAYMENTS,
    }


def _logistics_context(db: Session, role: str, subject_id: int) -> dict:
    """Farmer<->transporter logistics: TransportReview (+ de-duplicated
    TripReview TRANSPORTER rows for transporters) + completed trips."""
    TR = models.TransportRequest
    tr_rows = db.query(models.TransportReview.rating, models.TransportReview.comment).filter(
        models.TransportReview.reviewee_role == role,
        models.TransportReview.reviewee_id == subject_id,
    ).all()
    ratings = [r.rating for r in tr_rows]
    written = sum(1 for r in tr_rows if _is_written(r.comment))

    if role == "transporter":
        # A farmer may have filed BOTH a TransportReview and a TripReview
        # (TRANSPORTER) for the same job. Count that farmer/job once, with
        # the TransportReview taking precedence.
        already_counted = exists().where(
            models.TransportReview.transport_request_id == models.TripReview.transport_request_id,
            models.TransportReview.reviewer_role == "farmer",
            models.TransportReview.reviewer_id == models.TripReview.reviewer_farmer_id,
            models.TransportReview.reviewee_role == "transporter",
        ).correlate(models.TripReview)
        trip_rows = (
            db.query(models.TripReview.rating, models.TripReview.comment)
            .join(TR, TR.id == models.TripReview.transport_request_id)
            .filter(
                models.TripReview.review_type == "TRANSPORTER",
                TR.transporter_id == subject_id,
                ~already_counted,
            )
            .all()
        )
        ratings += [r.rating for r in trip_rows]
        written += sum(1 for r in trip_rows if _is_written(r.comment))
        own, other = TR.transporter_id, TR.farmer_id
    else:
        own, other = TR.farmer_id, TR.transporter_id

    completed, counterparties = db.query(
        func.count(TR.id), func.count(distinct(other)),   # COUNT(DISTINCT) skips NULL
    ).filter(
        own == subject_id,
        func.upper(TR.status).in_(COMPLETED_TRIP_STATUSES),
    ).one()
    return _context(ratings, written, completed or 0, counterparties or 0)


def _buyer_verification(db: Session, buyer_id: int) -> dict:
    # Imported here (not at module top) to keep the service importable
    # without the router layer; display_info is THE verification mapping.
    from app.routers.buyer_verification import display_info

    v = db.query(models.BuyerVerification).filter(
        models.BuyerVerification.buyer_id == buyer_id
    ).first()
    tier = display_info(v)["status"]
    # BuyerVerification is the source of truth. A legacy Buyer.verification_status
    # == "verified" with no backing record is deliberately NOT honoured.
    return {
        "state": "VERIFIED" if tier == "PLATFORM_VERIFIED" else "NOT_VERIFIED",
        "tier": tier,
        "supported": True,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def _subject_exists(db: Session, role: str, subject_id: int) -> bool:
    model = {"farmer": models.Farmer, "buyer": models.Buyer,
             "transporter": models.Transporter}[role]
    return db.query(model.id).filter(model.id == subject_id).first() is not None


def build_trust_summary(db: Session, role: str, subject_id: int) -> Optional[Dict]:
    """Returns the whitelisted summary dict, or None if the subject does not
    exist. Performs NO authorization -- callers must use can_view() first."""
    if role not in SUBJECT_ROLES or not _subject_exists(db, role, subject_id):
        return None

    if role == "buyer":
        verification = _buyer_verification(db, subject_id)
    else:
        # No verification process exists for farmers or transporters.
        verification = {"state": "NOT_SUPPORTED", "tier": None, "supported": False}

    trade = _trade_context(db, role, subject_id) if role in ("farmer", "buyer") else None
    logistics = _logistics_context(db, role, subject_id) if role in ("farmer", "transporter") else None
    contexts = {"trade": trade, "logistics": logistics}

    badges: List[str] = []
    if verification["state"] == "VERIFIED":
        badges.append("VERIFIED")
    live = [c for c in contexts.values() if c]
    if any(c["rating"]["state"] == "RATED" for c in live):
        badges.append("RATED")
    if any(c["reviewed"] == "REVIEWED" for c in live):
        badges.append("REVIEWED")
    if any(c["experience"] == "EXPERIENCE" for c in live):
        badges.append("EXPERIENCE")

    flags: List[str] = []
    if verification["state"] == "NOT_VERIFIED":
        flags.append("NOT_VERIFIED")
    if verification["state"] == "NOT_SUPPORTED":
        flags.append("NOT_SUPPORTED")
    if not any(b in badges for b in ("RATED", "REVIEWED", "EXPERIENCE")):
        flags.append("INSUFFICIENT_DATA")

    reasons: List[dict] = []
    if verification["state"] == "VERIFIED":
        reasons.append({"code": "VERIFIED_BY_PLATFORM_ADMIN", "params": None})
    elif verification["state"] == "NOT_SUPPORTED":
        reasons.append({"code": "VERIFICATION_NOT_SUPPORTED", "params": {"role": role}})
    for name, ctx in contexts.items():
        if not ctx:
            continue
        rating = ctx["rating"]
        reasons.append({
            "code": "RATINGS_SUFFICIENT" if rating["state"] == "RATED" else "RATINGS_BELOW_THRESHOLD",
            "params": {"context": name, "count": rating["count"], "min": rating["min_count"]},
        })
        reasons.append({
            "code": "COMPLETED_ACTIVITY" if ctx["experience"] == "EXPERIENCE" else "NO_COMPLETED_ACTIVITY",
            "params": {"context": name, "count": ctx["completed_count"]},
        })
        reasons.append({
            "code": "WRITTEN_REVIEWS_PRESENT" if ctx["reviewed"] == "REVIEWED" else "NO_WRITTEN_REVIEWS",
            "params": {"context": name, "count": ctx["written_review_count"]},
        })
        ph = ctx["payment_history"]
        if ph and ph["state"] != "AVAILABLE":
            reasons.append({
                "code": "PAYMENT_HISTORY_INSUFFICIENT",
                "params": {"count": ph["non_demo_paid_count"], "min": ph["min_count"]},
            })

    return {
        "subject": {"role": role, "id": subject_id},
        "badges": badges,
        "flags": flags,
        "verification": verification,
        "trade": trade,
        "logistics": logistics,
        "thresholds": dict(THRESHOLDS),
        "reason_codes": reasons,
    }
