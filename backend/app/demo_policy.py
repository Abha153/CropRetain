"""
Pure rules for demo data. No database or framework imports, so they are
cheap to test and safe to import anywhere.

* A demo account is any account whose e-mail ends in ".demo" (the existing
  seed data already uses @cropwise.demo; new demo accounts use
  @cropretain.demo). The API reports this as `is_demo` so the UI can label
  it -- there is no schema change.
* Demo data must never be created automatically on a production deployment.
"""
from typing import Optional

DEMO_EMAIL_SUFFIX = ".demo"
MIN_DEMO_PASSWORD_LEN = 12
_PRODUCTION_VALUES = {"production", "prod"}


def is_demo_email(email: Optional[str]) -> bool:
    return bool(email) and email.strip().lower().endswith(DEMO_EMAIL_SUFFIX)


def is_production(app_env: Optional[str]) -> bool:
    return (app_env or "").strip().lower() in _PRODUCTION_VALUES


def auto_seed_allowed(app_env: Optional[str]) -> bool:
    """Automatic first-run demo seeding is for local/dev only."""
    return not is_production(app_env)


def demo_accounts_allowed(app_env: Optional[str]) -> bool:
    return not is_production(app_env)


def demo_password_problem(password: Optional[str]) -> Optional[str]:
    """None when acceptable, otherwise a short reason. The password itself is
    never included in the message."""
    if not password:
        return "DEMO_ACCOUNT_PASSWORD is not set."
    if len(password) < MIN_DEMO_PASSWORD_LEN:
        return f"DEMO_ACCOUNT_PASSWORD must be at least {MIN_DEMO_PASSWORD_LEN} characters."
    return None
