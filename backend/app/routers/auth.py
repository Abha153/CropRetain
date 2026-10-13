from fastapi import APIRouter, Depends
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models, schemas
from app.auth_utils import hash_password, verify_password, create_access_token, get_current_user
from app.services.login_tracking import record_login_event
from app.errors import AppError

router = APIRouter(prefix="/auth", tags=["auth"])


def _farmer_dict(f: models.Farmer) -> dict:
    return {
        "id": f.id, "name": f.name, "email": f.email, "location": f.location,
        "crops": f.crops, "rating": f.rating, "phone": f.phone,
        "preferred_language": f.preferred_language, "fpo_group": f.fpo_group,
    }


def _buyer_dict(b: models.Buyer) -> dict:
    return {
        "id": b.id, "company_name": b.company_name, "email": b.email,
        "location": b.location, "buyer_type": b.buyer_type,
        "verification_status": b.verification_status,
        "reliability_score": b.reliability_score,
        "preferred_language": b.preferred_language,
    }


def _transporter_dict(t: models.Transporter) -> dict:
    return {
        "id": t.id, "name": t.name, "email": t.email, "phone": t.phone,
        "business_name": t.business_name, "service_area": t.service_area,
        "vehicle_types": t.vehicle_types, "preferred_language": t.preferred_language,
        "rating": t.rating, "rating_count": t.rating_count,
    }


@router.post("/register/farmer", response_model=schemas.Token)
def register_farmer(payload: schemas.FarmerRegister, db: Session = Depends(get_db)):
    if db.query(models.Farmer).filter(models.Farmer.email == payload.email).first():
        raise AppError(status_code=400, code="ACCOUNT_EMAIL_EXISTS", detail="An account with this email already exists")
    farmer = models.Farmer(
        name=payload.name, email=payload.email,
        password_hash=hash_password(payload.password),
        phone=payload.phone, location=payload.location,
        latitude=payload.latitude, longitude=payload.longitude,
        crops=payload.crops, preferred_language=payload.preferred_language,
    )
    db.add(farmer)
    db.commit()
    db.refresh(farmer)
    token = create_access_token(subject=farmer.email, role="farmer")
    return {"access_token": token, "role": "farmer", "user": _farmer_dict(farmer)}


@router.post("/register/buyer", response_model=schemas.Token)
def register_buyer(payload: schemas.BuyerRegister, db: Session = Depends(get_db)):
    if db.query(models.Buyer).filter(models.Buyer.email == payload.email).first():
        raise AppError(status_code=400, code="ACCOUNT_EMAIL_EXISTS", detail="An account with this email already exists")
    buyer = models.Buyer(
        company_name=payload.company_name, email=payload.email,
        password_hash=hash_password(payload.password),
        phone=payload.phone, location=payload.location,
        latitude=payload.latitude, longitude=payload.longitude,
        buyer_type=payload.buyer_type, crops_of_interest=payload.crops_of_interest,
        verification_status="pending", reliability_score=60.0, payment_history_score=60.0,
        preferred_language=payload.preferred_language,
    )
    db.add(buyer)
    db.commit()
    db.refresh(buyer)
    token = create_access_token(subject=buyer.email, role="buyer")
    return {"access_token": token, "role": "buyer", "user": _buyer_dict(buyer)}


@router.post("/register/transporter", response_model=schemas.Token)
def register_transporter(payload: schemas.TransporterRegister, db: Session = Depends(get_db)):
    """Reuses the existing Farmer/Buyer registration pattern exactly --
    bcrypt hash + JWT with role='transporter'. No new auth mechanism."""
    if db.query(models.Transporter).filter(models.Transporter.email == payload.email).first():
        raise AppError(status_code=400, code="ACCOUNT_EMAIL_EXISTS", detail="An account with this email already exists")
    transporter = models.Transporter(
        name=payload.name, email=payload.email,
        password_hash=hash_password(payload.password),
        phone=payload.phone, business_name=payload.business_name,
        service_area=payload.service_area, vehicle_types=payload.vehicle_types,
        preferred_language=payload.preferred_language,
    )
    db.add(transporter)
    db.commit()
    db.refresh(transporter)
    token = create_access_token(subject=transporter.email, role="transporter")
    return {"access_token": token, "role": "transporter", "user": _transporter_dict(transporter)}


@router.post("/login", response_model=schemas.Token)
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    """
    Existing auth decision logic below is UNCHANGED. The only additions are
    calls to record_login_event() for activity tracking (see
    app/services/login_tracking.py) -- each call is best-effort and cannot
    raise, alter the response, or affect who is allowed to log in. The
    success-path response (token + user dict) is fully built *before* the
    event is recorded, so even a database hiccup while logging the event
    can never change what a legitimate login returns.
    """
    email = form_data.username
    farmer = db.query(models.Farmer).filter(models.Farmer.email == email).first()
    if farmer and verify_password(form_data.password, farmer.password_hash):
        token = create_access_token(subject=farmer.email, role="farmer")
        response = {"access_token": token, "role": "farmer", "user": _farmer_dict(farmer)}
        record_login_event(db, user_id=farmer.id, role="farmer", success=True, touch_last_login_on=farmer)
        return response

    buyer = db.query(models.Buyer).filter(models.Buyer.email == email).first()
    if buyer and verify_password(form_data.password, buyer.password_hash):
        token = create_access_token(subject=buyer.email, role="buyer")
        response = {"access_token": token, "role": "buyer", "user": _buyer_dict(buyer)}
        record_login_event(db, user_id=buyer.id, role="buyer", success=True, touch_last_login_on=buyer)
        return response

    transporter = db.query(models.Transporter).filter(models.Transporter.email == email).first()
    if transporter and verify_password(form_data.password, transporter.password_hash):
        token = create_access_token(subject=transporter.email, role="transporter")
        response = {"access_token": token, "role": "transporter", "user": _transporter_dict(transporter)}
        record_login_event(db, user_id=transporter.id, role="transporter", success=True, touch_last_login_on=transporter)
        return response

    # Failed login. Identify the targeted account when possible (by numeric
    # id + role only -- never by storing the email/username that was typed
    # or the password) so the admin dashboard can distinguish "wrong
    # password against a real account" from "attempt against an email that
    # doesn't exist at all".
    if farmer:
        record_login_event(db, user_id=farmer.id, role="farmer", success=False)
    elif buyer:
        record_login_event(db, user_id=buyer.id, role="buyer", success=False)
    elif transporter:
        record_login_event(db, user_id=transporter.id, role="transporter", success=False)
    else:
        record_login_event(db, user_id=None, role="unknown", success=False)

    raise AppError(status_code=401, code="INVALID_LOGIN_CREDENTIALS", detail="Incorrect email or password")


@router.post("/admin/login", response_model=schemas.Token)
def admin_login(form_data: OAuth2PasswordRequestForm = Depends()):
    """
    Single-operator admin login. Credentials come from environment
    configuration (see app/config.py) -- never hard-coded, never a normal
    user account, and never reachable via the farmer/buyer registration
    flow.
    """
    if form_data.username != settings.admin_username or form_data.password != settings.admin_password:
        raise AppError(status_code=401, code="INVALID_ADMIN_CREDENTIALS", detail="Incorrect admin credentials")
    token = create_access_token(subject=settings.admin_username, role="admin")
    return {"access_token": token, "role": "admin", "user": {"username": settings.admin_username}}


@router.get("/me")
def me(current=Depends(get_current_user)):
    user, role = current["user"], current["role"]
    if role == "farmer":
        return {"role": role, "user": _farmer_dict(user)}
    if role == "transporter":
        return {"role": role, "user": _transporter_dict(user)}
    if role == "admin":
        return {"role": role, "user": user}
    return {"role": role, "user": _buyer_dict(user)}
