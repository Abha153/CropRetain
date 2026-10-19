from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config import settings

if not settings.database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. CropRetain's MVP database is PostgreSQL "
        "(Supabase) -- there is no local SQLite fallback anymore. Copy "
        "backend/.env.example to backend/.env and set DATABASE_URL to your "
        "Supabase connection string (Project Settings -> Database -> "
        "Connect in the Supabase dashboard)."
    )

_is_sqlite = settings.database_url.startswith("sqlite")
connect_args = {"check_same_thread": False} if _is_sqlite else {}

# pool_pre_ping guards against stale connections from a hosted Postgres
# provider (e.g. Supabase) closing idle connections -- SQLAlchemy will
# transparently reconnect instead of raising on the next query. It's a
# no-op for SQLite (single file, no connection pool to go stale).
engine = create_engine(
    settings.database_url,
    connect_args=connect_args,
    pool_pre_ping=not _is_sqlite,
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def run_lightweight_migrations():
    """
    Additive-only migrations for existing tables -- never drops a column,
    a table, or rewrites existing row data.

    Two independent additive paths, for two different histories:

    1. SQLite-specific (PRAGMA table_info / ALTER TABLE ... ADD COLUMN),
       from before the project moved to PostgreSQL (Supabase) as its MVP
       database. Only ever applies to a pre-existing local cropwise.db
       file.
    2. Postgres-specific (ALTER TABLE ... ADD COLUMN IF NOT EXISTS, which
       SQLite doesn't support but Postgres does natively), for columns
       added to a model AFTER a Supabase database was already
       initialized -- e.g. `market_prices.source`/`source_timestamp`,
       added for multi-source (data.gov.in + Agmarknet) attribution. A
       BRAND NEW Supabase database never needs this path at all: its
       first `Base.metadata.create_all()` already includes every current
       column in one shot. This path exists only for a Supabase database
       that was seeded before a given column existed.

    Safe to run on every startup either way -- no-op once columns already
    exist, never deletes rows.
    """
    from sqlalchemy import text

    if _is_sqlite:
        with engine.connect() as conn:
            def add_column_if_missing(table: str, column: str, ddl_type: str):
                rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
                if not rows:
                    return  # table doesn't exist yet -- create_all will handle it
                cols = [row[1] for row in rows]
                if column not in cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl_type}"))
                    conn.commit()

            # Legacy columns
            add_column_if_missing("market_prices", "data_source", "VARCHAR NOT NULL DEFAULT 'demo'")
            # Phase 3/4 freshness columns
            add_column_if_missing("market_prices", "observed_at", "VARCHAR")
            add_column_if_missing("market_prices", "fetched_at", "DATETIME")
            add_column_if_missing("farmers", "last_login", "DATETIME")
            add_column_if_missing("buyers", "last_login", "DATETIME")

            # Phase 10: Transaction lifecycle columns
            add_column_if_missing("transactions", "lot_id", "INTEGER")
            add_column_if_missing("transactions", "offer_id", "INTEGER")
            add_column_if_missing("transactions", "updated_at", "DATETIME")

            # Phase 16: buyer notifications
            add_column_if_missing("notifications", "buyer_id", "INTEGER")

            # Integration pass: link transport requests to the transaction they
            # fulfil, so transport status can drive transaction status instead
            # of the transport module being an isolated island.
            add_column_if_missing("transport_requests", "transaction_id", "INTEGER")

            # Integration pass: let a buyer offer be made directly on a Lot
            # (Phase 4 sellable unit) instead of only the legacy CropListing,
            # and optionally record which BuyerDemand it fulfils -- this is
            # what actually connects Buyer Demand -> Lot -> Match -> Offer.
            add_column_if_missing("buyer_offers", "lot_id", "INTEGER")
            add_column_if_missing("buyer_offers", "buyer_demand_id", "INTEGER")

            # Transporter quote / negotiation / agreed price + delivered_at,
            # added to the TransportRequest model in this pass.
            add_column_if_missing("transport_requests", "picked_up_at", "DATETIME")
            add_column_if_missing("transport_requests", "delivered_at", "DATETIME")
            add_column_if_missing("transport_requests", "quote_status", "VARCHAR NOT NULL DEFAULT 'AWAITING_QUOTE'")
            add_column_if_missing("transport_requests", "quoted_price", "FLOAT")
            add_column_if_missing("transport_requests", "quoted_at", "DATETIME")
            add_column_if_missing("transport_requests", "counter_price", "FLOAT")
            add_column_if_missing("transport_requests", "counter_by", "VARCHAR")
            add_column_if_missing("transport_requests", "counter_at", "DATETIME")
            add_column_if_missing("transport_requests", "agreed_price", "FLOAT")
            add_column_if_missing("transport_requests", "agreed_at", "DATETIME")

            add_column_if_missing("buyer_verifications", "submitted_at", "DATETIME")
            add_column_if_missing("buyer_verifications", "reviewed_at", "DATETIME")
            add_column_if_missing("buyer_verifications", "reviewed_by", "VARCHAR")

            # Real authenticated Transporter <-> Farmer workflow. New
            # tables (transporters, transport_offers, transport_messages,
            # transport_reviews) are created by Base.metadata.create_all()
            # automatically -- only NEW COLUMNS on the pre-existing
            # transport_requests table need an explicit ADD COLUMN here.
            add_column_if_missing("transport_requests", "transporter_id", "INTEGER")
            add_column_if_missing("transport_requests", "negotiation_status", "VARCHAR NOT NULL DEFAULT 'OPEN'")
            add_column_if_missing("transport_requests", "claimed_at", "DATETIME")
            add_column_if_missing("transport_requests", "transporter_agreed_price", "FLOAT")
            add_column_if_missing("transport_requests", "transporter_agreed_at", "DATETIME")
            add_column_if_missing("transport_requests", "completed_at", "DATETIME")

            # Multi-round crop-offer negotiation. The new table
            # (buyer_offer_rounds) is created by create_all(); only new
            # COLUMNS on the pre-existing buyer_offers table need ADD COLUMN.
            add_column_if_missing("buyer_offers", "updated_at", "DATETIME")
            add_column_if_missing("buyer_offers", "accepted_round_id", "INTEGER")
            add_column_if_missing("buyer_offers", "agreed_price_per_kg", "FLOAT")
            add_column_if_missing("buyer_offers", "agreed_quantity_kg", "FLOAT")
            add_column_if_missing("buyer_offers", "agreed_at", "DATETIME")

            # Razorpay gateway linkage on payments.
            add_column_if_missing("payments", "gateway", "VARCHAR")
            add_column_if_missing("payments", "gateway_order_id", "VARCHAR")
            add_column_if_missing("payments", "gateway_payment_id", "VARCHAR")
        return

    # Postgres path: only the columns added after the Supabase migration.
    with engine.connect() as conn:
        # Razorpay gateway linkage on payments (table itself pre-exists).
        conn.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway VARCHAR"))
        conn.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_order_id VARCHAR"))
        conn.execute(text("ALTER TABLE payments ADD COLUMN IF NOT EXISTS gateway_payment_id VARCHAR"))
        conn.execute(text(
            "ALTER TABLE market_prices ADD COLUMN IF NOT EXISTS source VARCHAR"
        ))
        conn.execute(text(
            "ALTER TABLE market_prices ADD COLUMN IF NOT EXISTS source_timestamp VARCHAR"
        ))
        # Phase 3/4 freshness columns
        conn.execute(text(
            "ALTER TABLE market_prices ADD COLUMN IF NOT EXISTS observed_at VARCHAR"
        ))
        conn.execute(text(
            "ALTER TABLE market_prices ADD COLUMN IF NOT EXISTS fetched_at TIMESTAMP"
        ))
        # Transporter quote / negotiation / agreed price + delivered_at.
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS picked_up_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS delivered_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS quote_status VARCHAR NOT NULL DEFAULT 'AWAITING_QUOTE'"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS quoted_price DOUBLE PRECISION"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS quoted_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS counter_price DOUBLE PRECISION"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS counter_by VARCHAR"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS counter_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS agreed_price DOUBLE PRECISION"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS agreed_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE buyer_verifications ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE buyer_verifications ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE buyer_verifications ADD COLUMN IF NOT EXISTS reviewed_by VARCHAR"
        ))
        # Real authenticated Transporter <-> Farmer workflow. New tables
        # (transporters, transport_offers, transport_messages,
        # transport_reviews) are created by Base.metadata.create_all()
        # automatically on a fresh or already-migrated Supabase database --
        # only the new columns on the pre-existing transport_requests
        # table need an explicit ADD COLUMN IF NOT EXISTS here.
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS transporter_id INTEGER"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS negotiation_status VARCHAR NOT NULL DEFAULT 'OPEN'"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS transporter_agreed_price DOUBLE PRECISION"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS transporter_agreed_at TIMESTAMP"
        ))
        conn.execute(text(
            "ALTER TABLE transport_requests ADD COLUMN IF NOT EXISTS completed_at TIMESTAMP"
        ))
        # Multi-round crop-offer negotiation columns (table is created by create_all).
        conn.execute(text("ALTER TABLE buyer_offers ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP"))
        conn.execute(text("ALTER TABLE buyer_offers ADD COLUMN IF NOT EXISTS accepted_round_id INTEGER"))
        conn.execute(text("ALTER TABLE buyer_offers ADD COLUMN IF NOT EXISTS agreed_price_per_kg DOUBLE PRECISION"))
        conn.execute(text("ALTER TABLE buyer_offers ADD COLUMN IF NOT EXISTS agreed_quantity_kg DOUBLE PRECISION"))
        conn.execute(text("ALTER TABLE buyer_offers ADD COLUMN IF NOT EXISTS agreed_at TIMESTAMP"))
        conn.commit()
