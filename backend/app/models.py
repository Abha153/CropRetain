import datetime as dt

from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, ForeignKey, Text, JSON,
    UniqueConstraint
)
from sqlalchemy.orm import relationship

from app.database import Base


def now():
    return dt.datetime.utcnow()


class Farmer(Base):
    __tablename__ = "farmers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    phone = Column(String, default="")
    location = Column(String, nullable=False)
    latitude = Column(Float, default=0.0)
    longitude = Column(Float, default=0.0)
    crops = Column(JSON, default=list)  # list of crop names the farmer grows
    preferred_language = Column(String, default="en")
    rating = Column(Float, default=4.5)
    fpo_group = Column(String, nullable=True)  # cooperative / FPO name if joined
    created_at = Column(DateTime, default=now)
    last_login = Column(DateTime, nullable=True)

    listings = relationship("CropListing", back_populates="farmer")
    notifications = relationship("Notification", back_populates="farmer")
    lots = relationship("Lot", back_populates="farmer")


class Buyer(Base):
    __tablename__ = "buyers"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    phone = Column(String, default="")
    location = Column(String, nullable=False)
    latitude = Column(Float, default=0.0)
    longitude = Column(Float, default=0.0)
    buyer_type = Column(String, default="wholesaler")  # wholesaler/retailer/processor/exporter/fpo
    verification_status = Column(String, default="pending")  # verified/pending -- new buyers start unverified; only the buyer-verification admin flow (or explicit seed data) should ever set this to "verified"
    reliability_score = Column(Float, default=85.0)  # 0-100
    payment_history_score = Column(Float, default=90.0)  # 0-100
    crops_of_interest = Column(JSON, default=list)
    preferred_language = Column(String, default="en")
    created_at = Column(DateTime, default=now)
    last_login = Column(DateTime, nullable=True)

    offers = relationship("BuyerOffer", back_populates="buyer")
    demands = relationship("BuyerDemand", back_populates="buyer")
    verification = relationship("BuyerVerification", back_populates="buyer", uselist=False)


class CropListing(Base):
    __tablename__ = "crop_listings"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id"))
    crop = Column(String, nullable=False)
    quantity_kg = Column(Float, nullable=False)
    quality_grade = Column(String, default="B")  # A / B / C
    quality_score = Column(Float, default=75.0)
    expected_price_per_kg = Column(Float, nullable=False)
    location = Column(String, nullable=False)
    available_date = Column(String, nullable=False)  # ISO date string
    status = Column(String, default="active")  # active/sold/expired
    min_acceptable_price = Column(Float, nullable=True)
    bidding_deadline = Column(String, nullable=True)
    image_note = Column(String, nullable=True)
    note = Column(String, nullable=True)
    language = Column(String, default="en")
    created_at = Column(DateTime, default=now)

    farmer = relationship("Farmer", back_populates="listings")
    offers = relationship("BuyerOffer", back_populates="listing")


class BuyerOffer(Base):
    __tablename__ = "buyer_offers"

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"))
    listing_id = Column(Integer, ForeignKey("crop_listings.id"), nullable=True)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=True)
    buyer_demand_id = Column(Integer, ForeignKey("buyer_demands.id"), nullable=True)
    offered_price_per_kg = Column(Float, nullable=False)
    quantity_kg = Column(Float, nullable=False)
    message = Column(String, default="")
    language = Column(String, default="en")
    status = Column(String, default="pending")  # pending/accepted/rejected/withdrawn
    created_at = Column(DateTime, default=now)
    # Multi-round negotiation (additive). `status` above remains the
    # THREAD-level commercial state ("pending" == negotiation still open).
    # `offered_price_per_kg` / `quantity_kg` MIRROR the latest round while
    # the thread is open; every historical value lives in BuyerOfferRound.
    # Once accepted, the agreed_* fields freeze the authoritative deal terms.
    updated_at = Column(DateTime, nullable=True)
    accepted_round_id = Column(Integer, nullable=True)
    agreed_price_per_kg = Column(Float, nullable=True)
    agreed_quantity_kg = Column(Float, nullable=True)
    agreed_at = Column(DateTime, nullable=True)

    buyer = relationship("Buyer", back_populates="offers")
    listing = relationship("CropListing", back_populates="offers")
    rounds = relationship("BuyerOfferRound", back_populates="offer", order_by="BuyerOfferRound.sequence")


class BuyerOfferRound(Base):
    """One immutable row per negotiation round of a crop offer (buyer <->
    farmer). Mirrors the persistent-history pattern of TransportOffer but is
    a separate table: a listing/lot has MANY buyers, so each BuyerOffer is
    its own thread. Sender/receiver identity is always derived server-side
    (JWT + listing/lot ownership), never from the client.

    status: PENDING (outstanding, awaiting receiver) / COUNTERED (replaced by
    a later round) / ACCEPTED / REJECTED / WITHDRAWN. Only `status` and
    `responded_at` ever change after creation; terms never do.
    """
    __tablename__ = "buyer_offer_rounds"

    id = Column(Integer, primary_key=True, index=True)
    offer_id = Column(Integer, ForeignKey("buyer_offers.id"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)  # 1, 2, 3... strictly increasing per offer
    sender_role = Column(String, nullable=False)     # "buyer" / "farmer"
    sender_id = Column(Integer, nullable=False)
    receiver_role = Column(String, nullable=False)
    receiver_id = Column(Integer, nullable=False)
    price_per_kg = Column(Float, nullable=False)
    quantity_kg = Column(Float, nullable=False)
    message = Column(Text, nullable=True)
    language = Column(String, default="en")
    status = Column(String, default="PENDING", nullable=False)
    created_at = Column(DateTime, default=now)
    responded_at = Column(DateTime, nullable=True)

    offer = relationship("BuyerOffer", back_populates="rounds")

    __table_args__ = (
        UniqueConstraint("offer_id", "sequence", name="uq_offer_round_sequence"),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id = Column(Integer, primary_key=True, index=True)
    listing_id = Column(Integer, ForeignKey("crop_listings.id"), nullable=True)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=True)
    offer_id = Column(Integer, ForeignKey("buyer_offers.id"), nullable=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id"))
    buyer_id = Column(Integer, ForeignKey("buyers.id"))
    final_price_per_kg = Column(Float, nullable=False)
    quantity_kg = Column(Float, nullable=False)
    total_amount = Column(Float, nullable=False)
    market_used = Column(String, default="")
    # Full lifecycle status (Phase 10)
    status = Column(String, default="OFFER_ACCEPTED")
    # Legacy -- kept for backward compat with old "completed" rows
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    events = relationship("TransactionEvent", back_populates="transaction")
    payments = relationship("Payment", back_populates="transaction")


class MarketPrice(Base):
    __tablename__ = "market_prices"

    id = Column(Integer, primary_key=True, index=True)
    crop = Column(String, index=True, nullable=False)
    market = Column(String, index=True, nullable=False)
    date = Column(String, nullable=False)
    min_price = Column(Float, nullable=False)
    max_price = Column(Float, nullable=False)
    modal_price = Column(Float, nullable=False)
    # No Python-side default here (deliberately) -- SQLAlchemy's Column
    # `default=` fires whenever the inserted value is None, which would
    # silently turn an explicit "arrivals_tonnes=None" (used by
    # _record_live_snapshot for a live row with no arrival-volume field)
    # back into 0.0, exactly the fabricated-zero bug this was meant to
    # prevent. Nullable with no default: unset really means NULL.
    arrivals_tonnes = Column(Float, nullable=True)
    data_source = Column(String, default="demo", nullable=False)
    # Multi-source attribution (nullable, additive -- see
    # run_lightweight_migrations() for the existing-table upgrade path).
    # `source` names which live provider(s) this row came from, e.g.
    # "data.gov.in", "agmarknet", or "data.gov.in+agmarknet" when both
    # agreed on the same observation -- always NULL for data_source="demo"
    # rows, since "demo" already unambiguously means no live provider was
    # involved. `source_timestamp` is the provider's own reported fetch
    # time (mandi_directory's `fetched_at`), distinct from `date` (the
    # market/observation date) and from any DB row-creation time -- it is
    # what lets a caller tell a fresh live read apart from a stale one.
    source = Column(String, nullable=True)
    source_timestamp = Column(String, nullable=True)
    # Phase 3/4 freshness fields. Deliberately THREE distinct concepts --
    # never reuse one timestamp for all of them:
    #   observed_at  -- the date the SOURCE says the price was observed, kept
    #                   verbatim as the provider reported it. If the provider
    #                   gives only a date and no clock time, that is what is
    #                   stored; a time is never manufactured to fill the gap.
    #   fetched_at   -- when CropRetain actually obtained the record (UTC,
    #                   server clock). Always known, because we did the fetch.
    # `last_successful_sync` is per-provider, not per-row, so it lives on
    # ProviderSyncState below rather than being duplicated onto every price.
    observed_at = Column(String, nullable=True)
    fetched_at = Column(DateTime, nullable=True)


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=True)
    type = Column(String, nullable=False)
    title = Column(String, nullable=False)
    message = Column(String, nullable=False)
    severity = Column(String, default="info")  # info/warning/success
    is_read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)

    farmer = relationship("Farmer", back_populates="notifications")


class GroupSellingPool(Base):
    __tablename__ = "group_selling_pools"

    id = Column(Integer, primary_key=True, index=True)
    crop = Column(String, nullable=False)
    fpo_name = Column(String, nullable=False)
    status = Column(String, default="open")  # open/matched/closed
    created_at = Column(DateTime, default=now)

    memberships = relationship("GroupPoolMembership", back_populates="pool")

    @property
    def member_farmer_ids(self):
        return [m.farmer_id for m in self.memberships]

    @property
    def total_quantity_kg(self):
        return sum(m.quantity_kg for m in self.memberships)


class GroupPoolMembership(Base):
    __tablename__ = "group_pool_memberships"

    id = Column(Integer, primary_key=True, index=True)
    pool_id = Column(Integer, ForeignKey("group_selling_pools.id"))
    farmer_id = Column(Integer, ForeignKey("farmers.id"))
    quantity_kg = Column(Float, nullable=False)
    joined_at = Column(DateTime, default=now)

    pool = relationship("GroupSellingPool", back_populates="memberships")


class LoginEvent(Base):
    __tablename__ = "login_events"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=True, index=True)
    role = Column(String, nullable=False, index=True)
    login_time = Column(DateTime, default=now, index=True)
    success = Column(Boolean, nullable=False, default=False, index=True)


# ============================================================
# NEW MODELS — Phase 1-15
# ============================================================

class BuyerDemand(Base):
    """Phase 1 — Buyer posts what they want to buy."""
    __tablename__ = "buyer_demands"

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False)
    crop = Column(String, nullable=False, index=True)
    required_quantity_kg = Column(Float, nullable=False)
    minimum_quantity_kg = Column(Float, nullable=True)
    maximum_quantity_kg = Column(Float, nullable=True)
    target_price_per_kg = Column(Float, nullable=True)  # ₹/kg (not /quintal)
    quality_grade = Column(String, nullable=True)       # A/B/C
    moisture_limit = Column(Float, nullable=True)       # %
    foreign_matter_limit = Column(Float, nullable=True) # %
    damaged_grains_limit = Column(Float, nullable=True) # %
    delivery_location = Column(String, nullable=True)
    delivery_latitude = Column(Float, nullable=True)
    delivery_longitude = Column(Float, nullable=True)
    delivery_deadline = Column(String, nullable=True)   # ISO date string
    payment_terms = Column(String, nullable=True)       # e.g. "Advance 50%, rest on delivery"
    additional_requirements = Column(Text, nullable=True)
    status = Column(String, default="ACTIVE", index=True)
    # ACTIVE / PARTIALLY_FILLED / FULFILLED / EXPIRED / CANCELLED
    expires_at = Column(String, nullable=True)          # ISO date string
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    buyer = relationship("Buyer", back_populates="demands")


class BuyerVerification(Base):
    """Phase 2 — Platform document-based buyer verification."""
    __tablename__ = "buyer_verifications"

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False, unique=True)
    business_name = Column(String, nullable=True)
    business_registration_number = Column(String, nullable=True)
    gst_number = Column(String, nullable=True)
    license_number = Column(String, nullable=True)
    document_urls = Column(JSON, default=list)
    # PENDING / UNDER_REVIEW / VERIFIED / REJECTED / SUSPENDED
    verification_status = Column(String, default="PENDING")
    # PLATFORM_VERIFIED / DOCUMENT_VERIFIED / SELF_DECLARED / PENDING
    verification_method = Column(String, default="SELF_DECLARED")
    verification_notes = Column(Text, nullable=True)
    verified_at = Column(DateTime, nullable=True)
    rejected_reason = Column(Text, nullable=True)
    submitted_at = Column(DateTime, nullable=True)   # set/updated on every buyer submission
    reviewed_at = Column(DateTime, nullable=True)     # set on approve/reject/suspend (any admin decision)
    reviewed_by = Column(String, nullable=True)       # admin identifier (email) -- no Admin DB table exists to FK to
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    buyer = relationship("Buyer", back_populates="verification")


class BuyerVerificationAuditLog(Base):
    """Every admin decision on a buyer's verification, kept even after the
    BuyerVerification row's own status is overwritten by a later decision --
    doc 11 requirement: buyer ID, old status, new status, reviewer, timestamp, note."""
    __tablename__ = "buyer_verification_audit_log"

    id = Column(Integer, primary_key=True, index=True)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False)
    old_status = Column(String, nullable=True)
    new_status = Column(String, nullable=False)
    reviewer_admin_id = Column(String, nullable=True)   # admin identifier (email) -- no Admin DB table exists to FK to
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)


class Receipt(Base):
    """Priority 8/9 — a real, persisted receipt for a completed transaction,
    with a SHA-256 integrity hash over a CANONICAL representation of its data.

    WHAT THE HASH DOES AND DOES NOT PROVE (do not overstate this anywhere
    in the UI or docs): recomputing the hash and finding it unchanged proves
    the RECEIPT CONTENT has not been altered since it was generated. It
    proves nothing about whether the underlying real-world transaction
    actually happened, whether goods moved, or whether money changed hands.
    It is tamper-evidence for a record, not proof of a trade.

    The receipt snapshots its values at generation time rather than joining
    live rows on every read -- a receipt for a completed transaction must
    not silently change if a name or price is edited later. `receipt_version`
    exists so the canonical-form algorithm can evolve without invalidating
    previously issued hashes.
    """
    __tablename__ = "receipts"

    id = Column(Integer, primary_key=True, index=True)
    receipt_id = Column(String, unique=True, nullable=False, index=True)  # e.g. CW-RCPT-000012
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False, index=True)
    receipt_version = Column(Integer, nullable=False, default=1)
    # Snapshotted transaction facts (see class docstring for why).
    payload = Column(JSON, nullable=False)
    hash_algorithm = Column(String, nullable=False, default="SHA-256")
    hash_value = Column(String, nullable=False)
    generated_at = Column(DateTime, default=now, nullable=False)

    transaction = relationship("Transaction")


class ProviderSyncState(Base):
    """Phase 3/4 — one row per external market-data provider, recording the
    last time a synchronisation with that provider actually SUCCEEDED.

    Deliberately separate from any individual price row's `fetched_at`:
    a price's fetched_at says when that record was obtained, whereas
    `last_successful_sync` answers "how current is our picture of this
    provider overall" -- including the case where the most recent sync
    attempt failed and returned nothing, so no new price rows exist to
    look at. Failure detail is kept alongside it rather than silently
    overwriting the last-good timestamp, so a stale-but-known state is
    always distinguishable from a fresh one.
    """
    __tablename__ = "provider_sync_state"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, unique=True, nullable=False, index=True)  # "data.gov.in" / "agmarknet"
    state = Column(String, nullable=True)        # e.g. "Maharashtra" -- scope of the sync
    last_successful_sync = Column(DateTime, nullable=True)
    last_attempted_sync = Column(DateTime, nullable=True)
    last_error = Column(Text, nullable=True)     # cleared on success, set on failure
    records_synced = Column(Integer, nullable=True)  # from the last SUCCESSFUL sync
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)


class Lot(Base):
    """Phase 4 — Proper agricultural lot (extends / wraps CropListing concept)."""
    __tablename__ = "lots"

    id = Column(Integer, primary_key=True, index=True)
    lot_number = Column(String, unique=True, nullable=False, index=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False)
    fpo_id = Column(Integer, ForeignKey("group_selling_pools.id"), nullable=True)
    listing_id = Column(Integer, ForeignKey("crop_listings.id"), nullable=True)
    crop = Column(String, nullable=False, index=True)
    quantity_kg = Column(Float, nullable=False)
    grade = Column(String, default="B")
    quality_score = Column(Float, default=75.0)
    quality_report = Column(JSON, nullable=True)  # full AI report
    harvest_date = Column(String, nullable=True)
    available_date = Column(String, nullable=True)
    location = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    expected_price = Column(Float, nullable=False)       # ₹/kg
    minimum_price = Column(Float, nullable=True)         # ₹/kg
    # DRAFT / AVAILABLE / UNDER_OFFER / SOLD / IN_TRANSIT / DELIVERED / CANCELLED
    status = Column(String, default="AVAILABLE", index=True)
    note = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    farmer = relationship("Farmer", back_populates="lots")


class StorageFacility(Base):
    """Phase 6 — Storage facilities (warehouses, cold storage, etc.)."""
    __tablename__ = "storage_facilities"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    # WAREHOUSE / COLD_STORAGE / FPO_STORAGE / PRIVATE_STORAGE / GOVERNMENT_STORAGE
    facility_type = Column(String, default="WAREHOUSE")
    location = Column(String, nullable=False)
    latitude = Column(Float, nullable=True)
    longitude = Column(Float, nullable=True)
    capacity_kg = Column(Float, nullable=False)
    available_capacity_kg = Column(Float, nullable=False)
    price_per_kg_per_day = Column(Float, nullable=False)
    crop_types = Column(JSON, default=list)
    temperature_controlled = Column(Boolean, default=False)
    warehouse_features = Column(JSON, default=list)
    quality_services = Column(JSON, default=list)
    contact = Column(String, nullable=True)
    # VERIFIED / UNVERIFIED / DEMO
    verification_status = Column(String, default="DEMO")
    # ACTIVE / INACTIVE
    status = Column(String, default="ACTIVE")
    is_demo = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now)

    bookings = relationship("StorageBooking", back_populates="facility")


class StorageBooking(Base):
    """Phase 6 — Farmer books storage for a lot."""
    __tablename__ = "storage_bookings"

    id = Column(Integer, primary_key=True, index=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False)
    storage_facility_id = Column(Integer, ForeignKey("storage_facilities.id"), nullable=False)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=True)
    quantity_kg = Column(Float, nullable=False)
    start_date = Column(String, nullable=False)
    end_date = Column(String, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    # REQUESTED / CONFIRMED / ACTIVE / COMPLETED / CANCELLED
    status = Column(String, default="REQUESTED")
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    facility = relationship("StorageFacility", back_populates="bookings")


class TransportRequest(Base):
    """Phase 9 — Logistics coordination for a lot."""
    __tablename__ = "transport_requests"

    id = Column(Integer, primary_key=True, index=True)
    lot_id = Column(Integer, ForeignKey("lots.id"), nullable=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=True)
    pickup_location = Column(String, nullable=False)
    destination = Column(String, nullable=False)
    pickup_date = Column(String, nullable=True)
    pickup_time = Column(String, nullable=True)
    vehicle_type = Column(String, nullable=True)
    driver_name = Column(String, nullable=True)
    driver_contact = Column(String, nullable=True)
    vehicle_capacity = Column(Float, nullable=True)
    estimated_cost = Column(Float, nullable=True)
    shared_transport = Column(Boolean, default=False)
    quantity_kg = Column(Float, nullable=True)
    # REQUESTED / MATCHED / CONFIRMED / PICKED_UP / IN_TRANSIT / DELIVERED / CANCELLED
    # This is the PHYSICAL trip's progress and is deliberately left alone --
    # quote/negotiation is a separate concern (below) so a commercial
    # back-and-forth over price can never corrupt or race with pickup/
    # transit/delivery tracking.
    status = Column(String, default="REQUESTED")
    picked_up_at = Column(DateTime, nullable=True)   # set only on transition to PICKED_UP
    delivered_at = Column(DateTime, nullable=True)   # set only on transition to DELIVERED

    # --- Transporter quote / negotiation / agreed price -----------------
    # `estimated_cost` above is CropRetain's own pre-trip estimate (from
    # transport_optimizer.py) and is never overwritten once a real quote
    # exists -- the UI shows both so a farmer never mistakes the estimate
    # for a payable amount.
    #
    # There is no separate transporter login/account in this codebase
    # (only farmer/buyer/admin roles exist in auth_utils.py) -- adding one
    # is out of scope for this MVP. `driver_name`/`driver_contact` above
    # are already plain text the farmer enters, not a real account, so the
    # quote is recorded the same way: the farmer (who owns this request)
    # logs the amount the transporter actually quoted them, and only the
    # farmer can accept/reject/counter it. This keeps quote storage and
    # authorization entirely server-side and reuses the existing
    # farmer-ownership check used by every other endpoint on this model --
    # it does not add a second, parallel identity system.
    #
    # AWAITING_QUOTE -> QUOTED -> (COUNTERED -> QUOTED)* -> ACCEPTED/REJECTED
    quote_status = Column(String, default="AWAITING_QUOTE")
    quoted_price = Column(Float, nullable=True)
    quoted_at = Column(DateTime, nullable=True)
    counter_price = Column(Float, nullable=True)
    counter_by = Column(String, nullable=True)     # "farmer" (only actor today)
    counter_at = Column(DateTime, nullable=True)
    agreed_price = Column(Float, nullable=True)
    agreed_at = Column(DateTime, nullable=True)

    # --- Real authenticated Transporter <-> Farmer workflow --------------
    # Added alongside (not replacing) the legacy farmer-recorded quote
    # fields above, which remain untouched for backward compatibility.
    # `transporter_id` is who claimed/was assigned this request; NULL means
    # it is still open to authorized transporters. `negotiation_status`
    # drives the real multi-round offer history (TransportOffer) below --
    # it is a separate state machine from the legacy `quote_status` so the
    # two flows can never collide or corrupt each other.
    # OPEN -> CLAIMED -> NEGOTIATING -> AGREED / DECLINED
    transporter_id = Column(Integer, ForeignKey("transporters.id"), nullable=True, index=True)
    negotiation_status = Column(String, default="OPEN", nullable=False)
    claimed_at = Column(DateTime, nullable=True)
    transporter_agreed_price = Column(Float, nullable=True)
    transporter_agreed_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    transporter = relationship("Transporter", back_populates="assigned_requests")
    offers = relationship("TransportOffer", back_populates="transport_request", order_by="TransportOffer.id")
    messages = relationship("TransportMessage", back_populates="transport_request", order_by="TransportMessage.id")
    farmer = relationship("Farmer")
    buyer = relationship("Buyer")


class Transporter(Base):
    """Real authenticated transporter account -- reuses the exact same
    auth pattern (bcrypt password hash + JWT) as Farmer/Buyer, added as a
    third role in auth_utils.get_current_user rather than a parallel auth
    system."""
    __tablename__ = "transporters"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    phone = Column(String, default="")
    business_name = Column(String, nullable=True)
    service_area = Column(String, nullable=True)   # free-text region/route coverage
    vehicle_types = Column(JSON, default=list)     # e.g. ["mini-truck", "truck"]
    preferred_language = Column(String, default="en")
    rating = Column(Float, default=0.0)
    rating_count = Column(Integer, default=0)
    created_at = Column(DateTime, default=now)
    last_login = Column(DateTime, nullable=True)

    assigned_requests = relationship("TransportRequest", back_populates="transporter")


class TransportOffer(Base):
    """Persistent multi-round negotiation history for the authenticated
    Farmer <-> Transporter workflow. Every offer is its own row -- never
    overwritten -- so the full back-and-forth stays auditable. Sender/
    receiver identity is always derived server-side from the authenticated
    user + the TransportRequest's farmer_id/transporter_id, never trusted
    from the request body."""
    __tablename__ = "transport_offers"

    id = Column(Integer, primary_key=True, index=True)
    transport_request_id = Column(Integer, ForeignKey("transport_requests.id"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)   # 1, 2, 3... strictly increasing per request
    sender_role = Column(String, nullable=False)     # "farmer" / "transporter"
    sender_id = Column(Integer, nullable=False)
    receiver_role = Column(String, nullable=False)
    receiver_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    message = Column(String, nullable=True)
    # PENDING -- awaiting the other party's response (outstanding offer)
    # ACCEPTED -- this exact offer was accepted; negotiation is closed
    # SUPERSEDED -- a later offer in the same request replaced this one
    # WITHDRAWN -- reserved for future use (not settable via API yet)
    status = Column(String, default="PENDING", nullable=False)
    created_at = Column(DateTime, default=now)
    responded_at = Column(DateTime, nullable=True)

    transport_request = relationship("TransportRequest", back_populates="offers")

    __table_args__ = (
        UniqueConstraint("transport_request_id", "sequence", name="uq_offer_sequence_per_request"),
    )


class TransportMessage(Base):
    """Lightweight transport-request-scoped chat between the farmer and
    the assigned transporter. Server-timestamped; sender/recipient derived
    from the authenticated user, never from the client."""
    __tablename__ = "transport_messages"

    id = Column(Integer, primary_key=True, index=True)
    transport_request_id = Column(Integer, ForeignKey("transport_requests.id"), nullable=False, index=True)
    sender_role = Column(String, nullable=False)      # "farmer" / "transporter"
    sender_id = Column(Integer, nullable=False)
    recipient_role = Column(String, nullable=False)
    recipient_id = Column(Integer, nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime, default=now)

    transport_request = relationship("TransportRequest", back_populates="messages")


class TransportReview(Base):
    """Two-sided review after a Farmer<->Transporter job COMPLETEs.
    Deliberately separate from TripReview (FarmPool shared-trip trust
    layer, reviewer is always a farmer, reviewee is a free-text driver)
    and from Rating (farmer<->buyer on a Transaction) -- neither existing
    table supports a transporter as a REVIEWER of a farmer, which this
    workflow requires. reviewer/reviewee identity is derived server-side
    from the TransportRequest's farmer_id/transporter_id + the
    authenticated caller, never trusted from the client."""
    __tablename__ = "transport_reviews"

    id = Column(Integer, primary_key=True, index=True)
    transport_request_id = Column(Integer, ForeignKey("transport_requests.id"), nullable=False, index=True)
    reviewer_role = Column(String, nullable=False)   # "farmer" / "transporter"
    reviewer_id = Column(Integer, nullable=False)
    reviewee_role = Column(String, nullable=False)
    reviewee_id = Column(Integer, nullable=False)
    rating = Column(Float, nullable=False)           # 1.0 - 5.0 overall
    punctuality = Column(Float, nullable=True)
    communication = Column(Float, nullable=True)
    handling = Column(Float, nullable=True)          # produce handling (farmer reviewing transporter)
    reliability = Column(Float, nullable=True)        # pickup readiness / payment reliability (transporter reviewing farmer)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)

    __table_args__ = (
        UniqueConstraint(
            "transport_request_id", "reviewer_role", "reviewer_id",
            name="uq_transport_review_per_reviewer",
        ),
    )


class Payment(Base):
    """Phase 11 — Payment tracking."""
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    buyer_id = Column(Integer, ForeignKey("buyers.id"), nullable=False)
    farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False)
    amount = Column(Float, nullable=False)
    currency = Column(String, default="INR")
    # PENDING / DUE / INITIATED / PAID / FAILED / DISPUTED
    payment_status = Column(String, default="PENDING")
    payment_method = Column(String, nullable=True)   # UPI/NEFT/Cash/etc.
    payment_reference = Column(String, nullable=True)
    payment_due_date = Column(String, nullable=True)
    initiated_at = Column(DateTime, nullable=True)
    received_at = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    is_demo = Column(Boolean, default=True)
    # Razorpay gateway linkage (NULL for the legacy simulated flow).
    gateway = Column(String, nullable=True)
    gateway_order_id = Column(String, nullable=True, index=True)
    gateway_payment_id = Column(String, nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)

    transaction = relationship("Transaction", back_populates="payments")


class PaymentWebhookEvent(Base):
    """One row per processed gateway webhook event id -- makes webhook
    handling idempotent (a retried delivery is acknowledged, not re-applied)."""
    __tablename__ = "payment_webhook_events"

    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False)
    event_id = Column(String, nullable=False)
    event_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=now)

    __table_args__ = (UniqueConstraint("provider", "event_id", name="uq_payment_webhook_event"),)


class TransactionEvent(Base):
    """Phase 12 — Transparent event trail for every transaction."""
    __tablename__ = "transaction_events"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    event_type = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    performed_by = Column(String, nullable=True)   # "farmer" / "buyer" / "admin" / "system"
    performed_by_id = Column(Integer, nullable=True)
    event_metadata = Column("metadata", JSON, nullable=True)
    created_at = Column(DateTime, default=now)

    transaction = relationship("Transaction", back_populates="events")


class Grievance(Base):
    """Phase 13 — Dispute / grievance system."""
    __tablename__ = "grievances"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=True)
    raised_by = Column(String, nullable=False)       # "farmer" / "buyer"
    raised_by_id = Column(Integer, nullable=False)
    against_user = Column(String, nullable=True)     # "farmer" / "buyer"
    against_user_id = Column(Integer, nullable=True)
    # PAYMENT / QUALITY / QUANTITY / PRICE / DELIVERY / LOGISTICS / BUYER / FARMER / OTHER
    category = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    evidence_urls = Column(JSON, default=list)
    # OPEN / UNDER_REVIEW / WAITING_FOR_EVIDENCE / RESOLVED / REJECTED / CLOSED
    status = Column(String, default="OPEN")
    priority = Column(String, default="MEDIUM")   # LOW / MEDIUM / HIGH
    assigned_to = Column(String, nullable=True)
    resolution = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)
    updated_at = Column(DateTime, default=now, onupdate=now)
    resolved_at = Column(DateTime, nullable=True)


class Rating(Base):
    """Phase 14 — Mutual ratings after completed transactions."""
    __tablename__ = "ratings"

    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(Integer, ForeignKey("transactions.id"), nullable=False)
    rater_role = Column(String, nullable=False)    # "farmer" / "buyer"
    rater_id = Column(Integer, nullable=False)
    ratee_role = Column(String, nullable=False)    # "farmer" / "buyer"
    ratee_id = Column(Integer, nullable=False)
    rating = Column(Float, nullable=False)         # 1.0 – 5.0
    review = Column(Text, nullable=True)
    created_at = Column(DateTime, default=now)

    __table_args__ = (
        UniqueConstraint("transaction_id", "rater_role", "rater_id", name="uq_rating_per_txn"),
    )


class TripReview(Base):
    """FarmPool / shared-logistics trust layer.

    Deliberately SEPARATE from `Rating` (which covers the farmer<->buyer
    relationship on a completed Transaction) because this covers a
    different relationship entirely: how the trip itself went. It attaches
    to a TransportRequest rather than a Transaction, since a shared
    FarmPool trip is a logistics event that may carry several farmers'
    produce and is not one-to-one with any single sale.

    It reuses TransportRequest (participants, status, shared_transport
    flag) and GroupSellingPool (fpo_name) rather than duplicating trip,
    user or FPO data.

    review_type:
      TRANSPORTER -- the driver/operator who ran the trip
      JOURNEY     -- the shared-trip experience itself (coordination,
                     pickup/drop, timeliness)
      FPO         -- the aggregator coordinating the pool, when one exists

    `verified` is set server-side ONLY after participation and completion
    are both proven; it is never accepted from the client.
    """
    __tablename__ = "trip_reviews"

    id = Column(Integer, primary_key=True, index=True)
    transport_request_id = Column(Integer, ForeignKey("transport_requests.id"), nullable=False, index=True)
    pool_id = Column(Integer, ForeignKey("group_selling_pools.id"), nullable=True, index=True)
    reviewer_farmer_id = Column(Integer, ForeignKey("farmers.id"), nullable=False, index=True)
    review_type = Column(String, nullable=False)   # TRANSPORTER / JOURNEY / FPO
    rating = Column(Float, nullable=False)         # 1.0 - 5.0 overall
    # Optional per-aspect scores; null when the reviewer skipped that aspect.
    punctuality = Column(Float, nullable=True)
    communication = Column(Float, nullable=True)
    handling = Column(Float, nullable=True)
    coordination = Column(Float, nullable=True)
    comment = Column(Text, nullable=True)
    verified = Column(Boolean, default=False)
    created_at = Column(DateTime, default=now)

    __table_args__ = (
        # One review of each type, per farmer, per trip.
        UniqueConstraint(
            "transport_request_id", "reviewer_farmer_id", "review_type",
            name="uq_trip_review_per_farmer_type",
        ),
    )
