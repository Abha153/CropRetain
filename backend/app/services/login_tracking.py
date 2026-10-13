"""
Login activity tracking.

Records every attempt to authenticate through POST /auth/login (farmer or
buyer) into the `login_events` table, so the admin dashboard can answer
"did registered users actually log in" -- as opposed to "how many accounts
exist", which `farmers`/`buyers` row counts already answer on their own.

Hard rule, enforced by what this module accepts as arguments: it can never
be handed a password, password hash, JWT/access token, or API key, because
those types don't appear in its function signature at all. It also never
receives or stores the raw email/username that was typed -- only the
already-resolved `user_id` (when the attempt matched a real account) and
`role`. See app/models.py::LoginEvent for the full column-level rationale.

Recording activity must never be able to break or change the outcome of an
actual login attempt (see the IMPORTANT note in app/routers/auth.py), so
every write here is isolated in its own try/except and swallows failures
silently rather than propagating them.
"""
import datetime as dt
from typing import Optional

from sqlalchemy.orm import Session

from app import models


def record_login_event(
    db: Session,
    *,
    user_id: Optional[int],
    role: str,
    success: bool,
    touch_last_login_on=None,
) -> None:
    """
    Insert one login_events row.

    Args:
        db: active SQLAlchemy session (same one the login endpoint is using).
        user_id: the farmer/buyer id if the attempt matched a real account,
            else None (e.g. the email didn't match any account).
        role: "farmer", "buyer", or "unknown" (email matched no account).
        success: whether authentication actually succeeded.
        touch_last_login_on: optional Farmer/Buyer ORM instance -- when
            provided and `success` is True, its `last_login` column is
            updated in the same commit. Pass the instance itself, never an
            id, so no extra query is needed here.
    """
    try:
        db.add(models.LoginEvent(user_id=user_id, role=role, success=success))
        if success and touch_last_login_on is not None:
            touch_last_login_on.last_login = dt.datetime.utcnow()
        db.commit()
    except Exception:
        # Activity tracking is best-effort and must never be the reason a
        # legitimate login fails or a failed login's response changes.
        db.rollback()
