import datetime as dt
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import jwt, JWTError
from passlib.context import CryptContext
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app import models

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(subject: str, role: str) -> str:
    expire = dt.datetime.utcnow() + dt.timedelta(minutes=settings.access_token_expire_minutes)
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.secret_key, algorithm=settings.algorithm)


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return None


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not token:
        raise credentials_exception
    payload = decode_token(token)
    if payload is None:
        raise credentials_exception
    email: str = payload.get("sub")
    role: str = payload.get("role")
    if email is None or role is None:
        raise credentials_exception

    if role == "farmer":
        user = db.query(models.Farmer).filter(models.Farmer.email == email).first()
    elif role == "buyer":
        user = db.query(models.Buyer).filter(models.Buyer.email == email).first()
    elif role == "transporter":
        user = db.query(models.Transporter).filter(models.Transporter.email == email).first()
    elif role == "admin":
        # Admin isn't backed by a DB row -- it's a single configured
        # operator account (see app/config.py). The token subject IS the
        # admin username in this case.
        if email != settings.admin_username:
            raise credentials_exception
        return {"user": {"username": email}, "role": "admin"}
    else:
        raise credentials_exception

    if user is None:
        raise credentials_exception
    return {"user": user, "role": role}


def require_farmer(current=Depends(get_current_user)):
    if current["role"] != "farmer":
        raise HTTPException(status_code=403, detail="Farmer account required")
    return current["user"]


def require_buyer(current=Depends(get_current_user)):
    if current["role"] != "buyer":
        raise HTTPException(status_code=403, detail="Buyer account required")
    return current["user"]


def require_admin(current=Depends(get_current_user)):
    if current["role"] != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return current["user"]


def require_transporter(current=Depends(get_current_user)):
    if current["role"] != "transporter":
        raise HTTPException(status_code=403, detail="Transporter account required")
    return current["user"]


def require_farmer_or_transporter(current=Depends(get_current_user)):
    """For endpoints (negotiation, chat, reviews) shared by both
    participants of a transport request -- returns (user, role) so the
    caller can derive identity/authorization from whichever it is."""
    if current["role"] not in ("farmer", "transporter"):
        raise HTTPException(status_code=403, detail="Farmer or transporter account required")
    return current["user"], current["role"]


def require_farmer_or_buyer(current=Depends(get_current_user)):
    """For crop-offer negotiation endpoints shared by both participants of
    an offer thread -- returns (user, role) so the caller derives identity
    and authorization from whichever it is (never from the request body)."""
    if current["role"] not in ("farmer", "buyer"):
        raise HTTPException(status_code=403, detail="Farmer or buyer account required")
    return current["user"], current["role"]
