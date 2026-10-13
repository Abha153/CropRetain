"""
Session-wide pytest setup.

The MVP's real database is PostgreSQL (Supabase) -- see backend/.env.example
-- and app/database.py now deliberately raises at import time if
DATABASE_URL isn't set, rather than silently falling back to a local
cropwise.db file. The test suite must never require a live Supabase
connection (or any real credentials) to run, so this sets a harmless
in-memory SQLite DATABASE_URL *before* any test module imports app.*,
satisfying that startup check without touching a real database.

Individual test files that need their own isolated engine (most of them)
already create one explicitly with create_engine("sqlite:///:memory:")
and don't touch app.database.engine at all -- this fixture only exists so
importing app.database (and anything that imports it) doesn't crash for
the handful of tests that go through the app's real engine/get_db.
"""
import os

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
