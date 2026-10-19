"""
Central configuration for the CropRetain backend.

All values have safe defaults so the API runs immediately in demo mode
without requiring a .env file. Copy .env.example to .env to override them.
"""
import os
import secrets
import logging

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger("cropretain")

_PLACEHOLDER_SECRET = "cropwise-hackathon-demo-secret-key-change-me"
_PLACEHOLDER_ADMIN_USERNAME = "admin"
_PLACEHOLDER_ADMIN_PASSWORD = "cropwise-admin-demo-2026"


class Settings(BaseSettings):
    app_name: str = "CropRetain API"
    # "development" (default) keeps the local first-run demo seeding. Set
    # APP_ENV=production on every real deployment: it turns OFF automatic
    # demo seeding and refuses to create demo accounts.
    app_env: str = "development"
    # Password for the opt-in demo accounts (python -m app.demo_accounts).
    # Deliberately has NO default and is never stored in the repo.
    demo_account_password: str = ""
    secret_key: str = _PLACEHOLDER_SECRET
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    # CropRetain's MVP database is PostgreSQL, hosted on Supabase -- there is
    # deliberately no SQLite default here anymore. A real deployment (or a
    # local run) must set DATABASE_URL explicitly via backend/.env (see
    # backend/.env.example for the exact Supabase connection-string shape).
    # Left unset, database.py raises a clear startup error rather than
    # silently falling back to a local file the MVP no longer depends on.
    database_url: str = ""
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173,http://localhost:4173,http://127.0.0.1:4173,http://localhost:4174,http://127.0.0.1:4174"

    # Admin console credentials. In production, ALWAYS set these via
    # environment variables -- never rely on the defaults below.
    admin_username: str = "admin"
    admin_password: str = "cropwise-admin-demo-2026"

    # Real government mandi-price data (data.gov.in "Current Daily Price of
    # Various Commodities from Various Markets" API). If unset, CropRetain
    # runs entirely on its seeded demo dataset, clearly labeled as such
    # everywhere in the UI. If set, the market router attempts a live fetch
    # FIRST and falls back to the demo dataset (with honest labeling of
    # which source was actually used for that request) if the live call
    # fails, times out, or returns no rows for that crop/market/date.
    data_gov_in_api_key: str = ""
    data_gov_in_resource_id: str = "9ef84268-d588-465a-a308-a864a43d0070"
    # Second, complementary data.gov.in resource: "Variety-wise Daily Market
    # Prices Data of Commodity". Different shape (District, not Market; and
    # capitalized field names) -- see app/services/district_market_data.py
    # and app/services/mandi_directory.py::fetch_price_result for how the
    # two resources are tried in order (market-specific first, district
    # aggregate second, demo dataset last) with honest per-source labeling.
    data_gov_in_district_resource_id: str = "35985678-0d79-46b4-9ed6-6f13308a1d24"
    market_data_source: str = "demo"  # data.gov.in mode; CEDA is enabled by its API key
    ceda_api_key: str = ""

    # Pan-India architecture: CropRetain is not restricted to any one state.
    # This is only the fallback used when neither an explicit request
    # parameter nor (on the frontend) the user's saved profile location /
    # browser GPS supplies a state. It exists so the SIH/PS-26132 demo can
    # default to Maharashtra without that value being hardcoded into every
    # function signature across the backend -- change it via the
    # DEFAULT_DEMO_STATE env var, never by editing business logic.
    default_demo_state: str = "Maharashtra"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def admin_credentials_are_default(self) -> bool:
        """True when the admin login would accept the publicly documented
        demo credentials (or an empty password)."""
        return (not self.admin_password
                or (self.admin_username == _PLACEHOLDER_ADMIN_USERNAME
                    and self.admin_password == _PLACEHOLDER_ADMIN_PASSWORD))

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

# Security hardening: never run with the publicly-visible placeholder secret.
# If the operator hasn't set SECRET_KEY via the environment/.env, generate a
# random one at process startup instead. This means auth tokens won't survive
# a server restart in that case (acceptable for a demo), but it guarantees a
# hard-coded, publicly-known secret can never sign a real token.
if settings.secret_key == _PLACEHOLDER_SECRET:
    settings.secret_key = secrets.token_hex(32)
    logger.warning(
        "SECRET_KEY not set in environment -- generated a random secret for "
        "this process. Set SECRET_KEY in backend/.env for a stable, "
        "production-grade deployment."
    )

# Same spirit as the SECRET_KEY check above, but the admin username/password
# can't be silently regenerated the way the JWT secret can -- a human has
# to type it in to sign in. So instead of rotating it, just make it loud:
# warn on every startup if the deployment is still running on the
# publicly-known demo default (which is documented in this repo's own
# .env.example / README, so it must never be relied on in a reachable
# deployment). Login behavior itself is unchanged either way -- this is
# observability only, not an auth-flow change.
if settings.admin_username == _PLACEHOLDER_ADMIN_USERNAME and settings.admin_password == _PLACEHOLDER_ADMIN_PASSWORD:
    logger.warning(
        "ADMIN_USERNAME/ADMIN_PASSWORD not set in environment -- running "
        "with the publicly-documented demo default. Set both in your "
        "environment (e.g. Render's dashboard, or backend/.env locally) "
        "before this deployment is reachable by anyone else."
    )

# In production the default admin credentials are not merely logged: admin
# login is refused until real ones are set (see routers/auth.py::admin_login).
from app.demo_policy import is_production  # noqa: E402  (stdlib-only module)

if is_production(settings.app_env) and settings.admin_credentials_are_default:
    logger.error(
        "APP_ENV=production but ADMIN_USERNAME/ADMIN_PASSWORD are unset or still the "
        "publicly documented defaults -- admin login is DISABLED until they are set."
    )
