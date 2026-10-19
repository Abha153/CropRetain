"""
Razorpay integration (backend only).

* No SDK: Orders API is one authenticated POST, signatures are HMAC-SHA256,
  so ``httpx`` + ``hmac`` (already dependencies / stdlib) are enough.
* Unavailable until RAZORPAY_KEY_ID and RAZORPAY_KEY_SECRET are set.
* Amounts are integers in paise; callers pass rupees computed server-side.
"""
import hashlib
import hmac
import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger("cropretain.razorpay")

CURRENCY = "INR"


class RazorpayUnavailable(Exception):
    """Credentials not configured."""


class RazorpayError(Exception):
    """Provider call failed."""


def is_configured() -> bool:
    return bool(settings.razorpay_key_id and settings.razorpay_key_secret)


def mode() -> str:
    """'test', 'live' or 'unavailable' -- derived from the key id prefix only."""
    if not is_configured():
        return "unavailable"
    return "test" if settings.razorpay_key_id.startswith("rzp_test_") else "live"


def to_paise(amount_rupees: float) -> int:
    return int(round(float(amount_rupees) * 100))


def create_order(amount_rupees: float, receipt: str, notes: Optional[dict] = None) -> dict:
    if not is_configured():
        raise RazorpayUnavailable("Razorpay is not configured")
    paise = to_paise(amount_rupees)
    if paise < 100:
        raise ValueError("Amount must be at least ₹1")
    body = {"amount": paise, "currency": CURRENCY, "receipt": receipt[:40], "notes": notes or {}}
    try:
        resp = httpx.post(
            f"{settings.razorpay_api_base}/orders",
            json=body,
            auth=(settings.razorpay_key_id, settings.razorpay_key_secret),
            timeout=15.0,
        )
    except httpx.HTTPError as exc:
        logger.warning("Razorpay order request failed: %s", type(exc).__name__)
        raise RazorpayError("Could not reach Razorpay") from exc
    if resp.status_code == 429:
        raise RazorpayError("Razorpay rate limit reached; try again shortly")
    if resp.status_code >= 400:
        logger.warning("Razorpay order rejected: HTTP %s", resp.status_code)
        raise RazorpayError(f"Razorpay rejected the order (HTTP {resp.status_code})")
    data = resp.json()
    if not data.get("id") or data.get("amount") != paise:
        raise RazorpayError("Unexpected response from Razorpay")
    return data


def _hmac_hex(secret: str, message: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()


def verify_checkout_signature(order_id: str, payment_id: str, signature: str) -> bool:
    """Checkout callback: HMAC_SHA256(order_id|payment_id, key_secret)."""
    if not (is_configured() and order_id and payment_id and signature):
        return False
    expected = _hmac_hex(settings.razorpay_key_secret, f"{order_id}|{payment_id}".encode("utf-8"))
    return hmac.compare_digest(expected, signature)


def verify_webhook_signature(raw_body: bytes, signature: str) -> bool:
    """Webhook: HMAC_SHA256(raw request body, webhook secret)."""
    if not (settings.razorpay_webhook_secret and signature):
        return False
    expected = _hmac_hex(settings.razorpay_webhook_secret, raw_body)
    return hmac.compare_digest(expected, signature)
