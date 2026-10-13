"""
Marketplace trust summaries (Phase C).

Authenticated-only, read-only. Responses are explicit whitelist models
(schemas.TrustSummaryOut) built by app/services/trust_summary.py from
existing rows -- there is no second rating/review/trust system here.

Authorization: a subject the caller may not see is indistinguishable from
a subject that does not exist -- both return the identical 404.
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app import schemas
from app.auth_utils import get_current_user
from app.services import trust_summary

router = APIRouter(prefix="/trust", tags=["trust"])

NOT_FOUND_DETAIL = "Trust profile not found"


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail=NOT_FOUND_DETAIL)


def _serve(db: Session, current: dict, subject_role: str, subject_id: int) -> dict:
    viewer_role = current["role"]
    viewer_id = None if viewer_role == "admin" else current["user"].id
    if not trust_summary.can_view(db, viewer_role, viewer_id, subject_role, subject_id):
        raise _not_found()
    summary = trust_summary.build_trust_summary(db, subject_role, subject_id)
    if summary is None:
        raise _not_found()
    return summary


@router.get("/me", response_model=schemas.TrustSummaryOut)
def my_trust(current=Depends(get_current_user), db: Session = Depends(get_db)):
    """The caller's own summary. The admin account has no trust profile."""
    role = current["role"]
    if role not in trust_summary.SUBJECT_ROLES:
        raise _not_found()
    return _serve(db, current, role, current["user"].id)


@router.get("/farmers/{farmer_id}", response_model=schemas.TrustSummaryOut)
def farmer_trust(farmer_id: int, current=Depends(get_current_user),
                 db: Session = Depends(get_db)):
    return _serve(db, current, "farmer", farmer_id)


@router.get("/buyers/{buyer_id}", response_model=schemas.TrustSummaryOut)
def buyer_trust(buyer_id: int, current=Depends(get_current_user),
                db: Session = Depends(get_db)):
    return _serve(db, current, "buyer", buyer_id)


@router.get("/transporters/{transporter_id}", response_model=schemas.TrustSummaryOut)
def transporter_trust(transporter_id: int, current=Depends(get_current_user),
                      db: Session = Depends(get_db)):
    return _serve(db, current, "transporter", transporter_id)
