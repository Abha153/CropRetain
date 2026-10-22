import datetime as dt
from typing import Optional, List, Any

from pydantic import BaseModel, EmailStr, ConfigDict, Field


# ---------- Auth ----------

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    user: dict


class FarmerRegister(BaseModel):
    name: str
    email: EmailStr
    password: str
    phone: Optional[str] = ""
    location: str
    latitude: float = 0.0
    longitude: float = 0.0
    crops: List[str] = []
    preferred_language: str = "en"


class BuyerRegister(BaseModel):
    company_name: str
    email: EmailStr
    password: str
    phone: Optional[str] = ""
    location: str
    latitude: float = 0.0
    longitude: float = 0.0
    buyer_type: str = "wholesaler"
    crops_of_interest: List[str] = []
    preferred_language: str = "en"


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# ---------- Public verification view + Trust summary (Phase C) ----------

class BuyerVerificationPublicOut(BaseModel):
    """What GET /buyer-verification/{buyer_id} may show to anyone: the
    display tier only. Never documents, GST/licence/registration numbers,
    notes, reviewer identity or the raw internal status."""
    buyer_id: int
    display_status: str
    display_label: str
    display_description: str
    verified_at: Optional[dt.datetime] = None


class TrustSubjectOut(BaseModel):
    role: str
    id: int


class TrustVerificationOut(BaseModel):
    state: str                  # VERIFIED / NOT_VERIFIED / NOT_SUPPORTED
    tier: Optional[str] = None  # buyer display tier (see buyer_verification.display_info)
    supported: bool


class TrustRatingOut(BaseModel):
    state: str                  # RATED / INSUFFICIENT_DATA
    count: int
    average: Optional[float] = None   # only when count >= min_count
    min_count: int


class TrustPaymentHistoryOut(BaseModel):
    state: str                  # AVAILABLE / INSUFFICIENT_DATA
    non_demo_paid_count: int
    min_count: int


class TrustContextOut(BaseModel):
    completed_count: int
    distinct_counterparties: int
    experience: str             # EXPERIENCE / INSUFFICIENT_DATA
    rating: TrustRatingOut
    written_review_count: int
    reviewed: str               # REVIEWED / INSUFFICIENT_DATA
    payment_history: Optional[TrustPaymentHistoryOut] = None


class TrustThresholdsOut(BaseModel):
    min_ratings_for_average: int
    min_written_reviews: int
    min_completed_for_experience: int
    min_non_demo_payments: int


class TrustReasonOut(BaseModel):
    code: str                   # i18n key; the client translates it
    params: Optional[dict] = None


class TrustSummaryOut(BaseModel):
    subject: TrustSubjectOut
    badges: List[str]           # earned: VERIFIED / RATED / REVIEWED / EXPERIENCE
    flags: List[str]            # NOT_VERIFIED / NOT_SUPPORTED / INSUFFICIENT_DATA
    verification: TrustVerificationOut
    trade: Optional[TrustContextOut] = None
    logistics: Optional[TrustContextOut] = None
    thresholds: TrustThresholdsOut
    reason_codes: List[TrustReasonOut]


# ---------- Farmer / Buyer ----------

class FarmerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    phone: str
    location: str
    latitude: float
    longitude: float
    crops: List[str]
    preferred_language: str
    rating: float
    fpo_group: Optional[str] = None
    created_at: dt.datetime
    last_login: Optional[dt.datetime] = None


class FarmerUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    crops: Optional[List[str]] = None
    preferred_language: Optional[str] = None


class BuyerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_name: str
    email: str
    phone: str
    location: str
    latitude: float
    longitude: float
    buyer_type: str
    verification_status: str
    reliability_score: float
    payment_history_score: float
    crops_of_interest: List[str]
    preferred_language: str
    created_at: dt.datetime
    last_login: Optional[dt.datetime] = None


# ---------- Public-safe profiles ----------

class FarmerPublicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    location: str
    crops: List[str]
    rating: float
    fpo_group: Optional[str] = None


class BuyerPublicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    company_name: str
    location: str
    buyer_type: str
    verification_status: str
    reliability_score: float
    crops_of_interest: List[str]


# ---------- Listings ----------

class ListingCreate(BaseModel):
    crop: str
    quantity_kg: float
    quality_grade: str = "B"
    quality_score: float = 75.0
    expected_price_per_kg: float
    location: Optional[str] = None
    available_date: str
    min_acceptable_price: Optional[float] = None
    bidding_deadline: Optional[str] = None
    image_note: Optional[str] = None
    note: Optional[str] = None
    language: str = "en"


class ListingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    farmer_id: int
    crop: str
    quantity_kg: float
    quality_grade: str
    quality_score: float
    expected_price_per_kg: float
    location: str
    available_date: str
    status: str
    min_acceptable_price: Optional[float]
    bidding_deadline: Optional[str]
    image_note: Optional[str]
    note: Optional[str] = None
    language: str = "en"
    created_at: dt.datetime


# ---------- Offers ----------

class OfferCreate(BaseModel):
    listing_id: Optional[int] = None
    lot_id: Optional[int] = None
    buyer_demand_id: Optional[int] = None
    offered_price_per_kg: float
    quantity_kg: float
    message: Optional[str] = ""
    language: str = "en"


class OfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    buyer_id: int
    listing_id: Optional[int] = None
    lot_id: Optional[int] = None
    buyer_demand_id: Optional[int] = None
    offered_price_per_kg: float
    quantity_kg: float
    message: str
    language: str = "en"
    status: str
    created_at: dt.datetime
    # Additive negotiation fields (all optional -> legacy clients unaffected).
    updated_at: Optional[dt.datetime] = None
    accepted_round_id: Optional[int] = None
    agreed_price_per_kg: Optional[float] = None
    agreed_quantity_kg: Optional[float] = None
    agreed_at: Optional[dt.datetime] = None
    awaiting_role: Optional[str] = None   # whose move it is while status == "pending"
    round_count: Optional[int] = None


class OfferCounter(BaseModel):
    """Body of a counter-offer. NO sender/receiver/buyer/farmer ids -- those
    are derived from authentication + ownership on the server."""
    price_per_kg: float = Field(..., gt=0)
    quantity_kg: Optional[float] = Field(None, gt=0)   # defaults to the current round's quantity
    message: Optional[str] = Field(None, max_length=2000)
    language: str = "en"
    # Optional stale-request guard: the round the client believed was current.
    based_on_round_id: Optional[int] = None


class OfferRoundOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    offer_id: int
    sequence: int
    sender_role: str
    sender_id: int
    receiver_role: str
    receiver_id: int
    price_per_kg: float
    quantity_kg: float
    message: Optional[str] = None
    language: str = "en"
    status: str
    created_at: dt.datetime
    responded_at: Optional[dt.datetime] = None


class OfferThreadOut(BaseModel):
    offer: OfferOut
    rounds: List[OfferRoundOut]
    awaiting_role: Optional[str] = None
    can_act: dict
    buyer: Optional[BuyerPublicOut] = None
    farmer: Optional[FarmerPublicOut] = None
    target: Optional[dict] = None
    transaction_id: Optional[int] = None


# ---------- Advisor ----------

class AdvisorRequest(BaseModel):
    crop: str
    quantity_kg: float
    quality_grade: str = "B"
    location: str
    harvest_date: Optional[str] = None


# ---------- Soil Advisor ----------

class SoilAdvisorRequest(BaseModel):
    """All soil inputs are optional individually, but at least one must be
    given (checked in the router). `quantity_kg` + `location` are an
    optional pair: when both are supplied the response also carries each
    crop's estimated net return from the existing market-comparison logic.
    Nothing here is a yield assumption -- quantity is whatever the farmer
    says they expect to sell."""
    soil_ph: Optional[float] = Field(default=None, ge=0, le=14)
    soil_texture: Optional[str] = None      # validated against TEXTURE_CLASSES in the router
    season: Optional[str] = None            # kharif | rabi | zaid
    irrigation: Optional[str] = None        # rainfed | limited | assured
    quantity_kg: Optional[float] = Field(default=None, gt=0)
    location: Optional[str] = None          # a market/location name known to CropRetain
    # Optional soil-test values (same units and bounds as SoilHealthRequest).
    # They are rated against the cited chart and returned as `soil_health`;
    # they do not change the crop-suitability checks.
    organic_carbon: Optional[float] = Field(default=None, ge=0, le=100)
    nitrogen: Optional[float] = Field(default=None, ge=0, le=10000)
    phosphorus: Optional[float] = Field(default=None, ge=0, le=10000)
    potassium: Optional[float] = Field(default=None, ge=0, le=10000)
    ec: Optional[float] = Field(default=None, ge=0, le=100)


class SoilHealthRequest(BaseModel):
    """Soil-test values as printed on a lab report / Soil Health Card. Each is
    optional; at least one is required (checked in the router). Units follow
    the cited rating chart: organic carbon in %, N/P/K in kg/ha, EC as printed
    by the chart (milli mhos/cm2)."""
    organic_carbon: Optional[float] = Field(default=None, ge=0, le=100)
    nitrogen: Optional[float] = Field(default=None, ge=0, le=10000)
    phosphorus: Optional[float] = Field(default=None, ge=0, le=10000)
    potassium: Optional[float] = Field(default=None, ge=0, le=10000)
    ph: Optional[float] = Field(default=None, ge=0, le=14)
    ec: Optional[float] = Field(default=None, ge=0, le=100)


# ---------- Profit calculator ----------

class ProfitScenario(BaseModel):
    label: str
    crop: str
    quantity_kg: float
    selling_price_per_kg: float
    transport_cost: float = 0.0
    labour_cost: float = 0.0
    packaging_cost: float = 0.0
    storage_cost: float = 0.0
    other_cost: float = 0.0


class ProfitCompareRequest(BaseModel):
    scenarios: List[ProfitScenario]


# ---------- Group selling ----------

class GroupSellingJoin(BaseModel):
    crop: str
    quantity_kg: float
    fpo_name: Optional[str] = "Independent Growers Collective"


# ---------- FarmPool ----------

class FarmPoolRequest(BaseModel):
    crop: str
    location: str
    quantity_kg: float
    destination_market: Optional[str] = None
    # Optional link to a real TransportRequest (app/models.py). When set
    # and that request has a transporter_agreed_price (i.e. negotiation is
    # AGREED), the pool's shared-cost allocation uses that real,
    # server-side price instead of the transport_optimizer estimate. The
    # estimate itself is never overwritten -- see
    # transport_optimizer.shared_transport_plan()'s `cost_basis` field.
    transport_request_id: Optional[int] = None


# ---------- Assistant ----------

class AssistantAsk(BaseModel):
    question: str
    language: str = "en"
    known_crop: Optional[str] = None
    known_quantity_kg: Optional[float] = None
    known_location: Optional[str] = None


# ---------- Quality grading ----------

class QualityGradeRequest(BaseModel):
    crop: str
    image_name: Optional[str] = None


# ---------- Buyer Demand (Phase 1) ----------

class BuyerDemandCreate(BaseModel):
    crop: str
    required_quantity_kg: float
    minimum_quantity_kg: Optional[float] = None
    maximum_quantity_kg: Optional[float] = None
    target_price_per_kg: Optional[float] = None
    quality_grade: Optional[str] = None
    moisture_limit: Optional[float] = None
    foreign_matter_limit: Optional[float] = None
    damaged_grains_limit: Optional[float] = None
    delivery_location: Optional[str] = None
    delivery_latitude: Optional[float] = None
    delivery_longitude: Optional[float] = None
    delivery_deadline: Optional[str] = None
    payment_terms: Optional[str] = None
    additional_requirements: Optional[str] = None
    expires_at: Optional[str] = None


class BuyerDemandUpdate(BaseModel):
    required_quantity_kg: Optional[float] = None
    minimum_quantity_kg: Optional[float] = None
    maximum_quantity_kg: Optional[float] = None
    target_price_per_kg: Optional[float] = None
    quality_grade: Optional[str] = None
    moisture_limit: Optional[float] = None
    foreign_matter_limit: Optional[float] = None
    damaged_grains_limit: Optional[float] = None
    delivery_location: Optional[str] = None
    delivery_deadline: Optional[str] = None
    payment_terms: Optional[str] = None
    additional_requirements: Optional[str] = None
    expires_at: Optional[str] = None
    status: Optional[str] = None


class BuyerDemandOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    buyer_id: int
    crop: str
    required_quantity_kg: float
    minimum_quantity_kg: Optional[float]
    maximum_quantity_kg: Optional[float]
    target_price_per_kg: Optional[float]
    quality_grade: Optional[str]
    moisture_limit: Optional[float]
    foreign_matter_limit: Optional[float]
    damaged_grains_limit: Optional[float]
    delivery_location: Optional[str]
    delivery_latitude: Optional[float]
    delivery_longitude: Optional[float]
    delivery_deadline: Optional[str]
    payment_terms: Optional[str]
    additional_requirements: Optional[str]
    status: str
    expires_at: Optional[str]
    created_at: dt.datetime
    updated_at: dt.datetime


# ---------- Buyer Verification (Phase 2) ----------

class BuyerVerificationCreate(BaseModel):
    business_name: Optional[str] = None
    business_registration_number: Optional[str] = None
    gst_number: Optional[str] = None
    license_number: Optional[str] = None
    document_urls: List[str] = []


class BuyerVerificationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    buyer_id: int
    business_name: Optional[str]
    business_registration_number: Optional[str]
    gst_number: Optional[str]
    license_number: Optional[str]
    document_urls: List[str]
    verification_status: str
    verification_method: str
    verification_notes: Optional[str]
    verified_at: Optional[dt.datetime]
    rejected_reason: Optional[str]
    submitted_at: Optional[dt.datetime] = None
    reviewed_at: Optional[dt.datetime] = None
    reviewed_by: Optional[str] = None
    created_at: dt.datetime
    updated_at: dt.datetime
    # Computed display fields (see app/routers/buyer_verification.py::display_info) --
    # the 4 canonical tiers, never raw internal state, shown to farmers/admins/advisor.
    display_status: Optional[str] = None
    display_label: Optional[str] = None
    display_description: Optional[str] = None


# ---------- Lot (Phase 4) ----------

class LotCreate(BaseModel):
    crop: str
    quantity_kg: float
    grade: str = "B"
    quality_score: float = 75.0
    quality_report: Optional[Any] = None
    harvest_date: Optional[str] = None
    available_date: Optional[str] = None
    location: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    expected_price: float
    minimum_price: Optional[float] = None
    note: Optional[str] = None
    fpo_id: Optional[int] = None
    listing_id: Optional[int] = None


class LotUpdate(BaseModel):
    quantity_kg: Optional[float] = None
    grade: Optional[str] = None
    quality_score: Optional[float] = None
    expected_price: Optional[float] = None
    minimum_price: Optional[float] = None
    available_date: Optional[str] = None
    status: Optional[str] = None
    note: Optional[str] = None


class LotOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lot_number: str
    farmer_id: int
    fpo_id: Optional[int]
    listing_id: Optional[int]
    crop: str
    quantity_kg: float
    grade: str
    quality_score: float
    quality_report: Optional[Any]
    harvest_date: Optional[str]
    available_date: Optional[str]
    location: str
    latitude: Optional[float]
    longitude: Optional[float]
    expected_price: float
    minimum_price: Optional[float]
    status: str
    note: Optional[str]
    created_at: dt.datetime
    updated_at: dt.datetime


# ---------- Storage (Phase 6) ----------

class StorageFacilityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    facility_type: str
    location: str
    latitude: Optional[float]
    longitude: Optional[float]
    capacity_kg: float
    available_capacity_kg: float
    price_per_kg_per_day: float
    crop_types: List[str]
    temperature_controlled: bool
    warehouse_features: List[str]
    quality_services: List[str]
    contact: Optional[str]
    verification_status: str
    status: str
    is_demo: bool
    created_at: dt.datetime


class StorageBookingCreate(BaseModel):
    storage_facility_id: int
    lot_id: Optional[int] = None
    quantity_kg: float = Field(gt=0)
    start_date: str
    end_date: Optional[str] = None


class StorageBookingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    farmer_id: int
    storage_facility_id: int
    lot_id: Optional[int]
    quantity_kg: float
    start_date: str
    end_date: Optional[str]
    estimated_cost: Optional[float]
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


# ---------- Transport (Phase 9) ----------

class TransportRequestCreate(BaseModel):
    lot_id: Optional[int] = None
    transaction_id: Optional[int] = None
    buyer_id: Optional[int] = None
    pickup_location: str
    destination: str
    pickup_date: Optional[str] = None
    pickup_time: Optional[str] = None
    vehicle_type: Optional[str] = None
    quantity_kg: Optional[float] = None
    shared_transport: bool = False
    estimated_cost: Optional[float] = None


class TransportQuoteSubmit(BaseModel):
    """A quote the transporter gave the farmer (recorded by the farmer --
    see the note on TransportRequest.quote_status for why there is no
    separate transporter login)."""
    quoted_price: float = Field(..., gt=0)


class TransportCounterOffer(BaseModel):
    counter_price: float = Field(..., gt=0)


class TransportStatusUpdate(BaseModel):
    status: str
    driver_name: Optional[str] = None
    driver_contact: Optional[str] = None
    vehicle_type: Optional[str] = None


# ---------- Transporter (real authenticated Farmer<->Transporter workflow) ----------

class TransporterRegister(BaseModel):
    name: str
    email: EmailStr
    password: str = Field(..., min_length=6)
    phone: str = ""
    business_name: Optional[str] = None
    service_area: Optional[str] = None
    vehicle_types: List[str] = Field(default_factory=list)
    preferred_language: str = "en"


class TransporterOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    email: str
    phone: str
    business_name: Optional[str]
    service_area: Optional[str]
    vehicle_types: List[str]
    preferred_language: str
    rating: float
    rating_count: int


class TransportOfferCreate(BaseModel):
    amount: float = Field(..., gt=0)
    message: Optional[str] = None


class TransportOfferOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transport_request_id: int
    sequence: int
    sender_role: str
    sender_id: int
    receiver_role: str
    receiver_id: int
    amount: float
    message: Optional[str]
    status: str
    created_at: dt.datetime
    responded_at: Optional[dt.datetime]


class TransportMessageCreate(BaseModel):
    message: str = Field(..., min_length=1, max_length=2000)


class TransportMessageOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transport_request_id: int
    sender_role: str
    sender_id: int
    recipient_role: str
    recipient_id: int
    message: str
    created_at: dt.datetime


class TransportReviewCreate(BaseModel):
    rating: float = Field(..., ge=1, le=5)
    punctuality: Optional[float] = Field(None, ge=1, le=5)
    communication: Optional[float] = Field(None, ge=1, le=5)
    handling: Optional[float] = Field(None, ge=1, le=5)
    reliability: Optional[float] = Field(None, ge=1, le=5)
    comment: Optional[str] = None


class TransportReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transport_request_id: int
    reviewer_role: str
    reviewer_id: int
    reviewee_role: str
    reviewee_id: int
    rating: float
    punctuality: Optional[float]
    communication: Optional[float]
    handling: Optional[float]
    reliability: Optional[float]
    comment: Optional[str]
    created_at: dt.datetime


class TransporterStatusUpdate(BaseModel):
    status: str


class TransportRequestOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    lot_id: Optional[int]
    farmer_id: int
    buyer_id: Optional[int]
    pickup_location: str
    destination: str
    pickup_date: Optional[str]
    pickup_time: Optional[str]
    vehicle_type: Optional[str]
    driver_name: Optional[str]
    driver_contact: Optional[str]
    vehicle_capacity: Optional[float]
    estimated_cost: Optional[float]
    shared_transport: bool
    quantity_kg: Optional[float]
    status: str
    created_at: dt.datetime
    updated_at: dt.datetime


# ---------- Transaction (Phase 10) ----------

class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    listing_id: Optional[int]
    lot_id: Optional[int]
    offer_id: Optional[int]
    farmer_id: int
    buyer_id: int
    final_price_per_kg: float
    quantity_kg: float
    total_amount: float
    market_used: str
    status: str
    created_at: dt.datetime


class TransactionStatusUpdate(BaseModel):
    status: str


# ---------- Payment (Phase 11) ----------

class PaymentCreate(BaseModel):
    transaction_id: int
    # BUGFIX: was `amount: float` (required) with no default, but the
    # actual frontend call (frontend/src/pages/TransactionDetail.jsx ->
    # api.createPayment) never sends an `amount` at all -- every real
    # payment-creation request from the app was therefore failing
    # pydantic validation (422) before even reaching the router. The
    # payment amount is authoritative server-side (Transaction.total_amount,
    # set once at offer-acceptance and never client-writable after that;
    # see app/routers/payments.py create_payment()), so `amount` here is
    # now optional and, if supplied, is only used to reject a mismatched
    # client value -- never to set the actual charged amount.
    amount: Optional[float] = None  # optional -- server derives from transaction
    payment_method: Optional[str] = None
    notes: Optional[str] = None
    payment_due_date: Optional[str] = None


class PaymentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transaction_id: int
    buyer_id: int
    farmer_id: int
    amount: float
    currency: str
    payment_status: str
    payment_method: Optional[str]
    payment_reference: Optional[str]
    payment_due_date: Optional[str]
    initiated_at: Optional[dt.datetime]
    received_at: Optional[dt.datetime]
    notes: Optional[str]
    is_demo: bool
    created_at: dt.datetime
    updated_at: dt.datetime


# ---------- Transaction Events (Phase 12) ----------

class TransactionEventOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transaction_id: int
    event_type: str
    description: Optional[str]
    performed_by: Optional[str]
    performed_by_id: Optional[int]
    event_metadata: Optional[Any] = None
    created_at: dt.datetime


# ---------- Grievance (Phase 13) ----------

class GrievanceCreate(BaseModel):
    transaction_id: Optional[int] = None
    against_user: Optional[str] = None
    against_user_id: Optional[int] = None
    category: str
    description: str
    evidence_urls: List[str] = []
    priority: str = "MEDIUM"


class GrievanceUpdate(BaseModel):
    status: Optional[str] = None
    resolution: Optional[str] = None
    priority: Optional[str] = None
    assigned_to: Optional[str] = None


class GrievanceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transaction_id: Optional[int]
    raised_by: str
    raised_by_id: int
    against_user: Optional[str]
    against_user_id: Optional[int]
    category: str
    description: str
    evidence_urls: List[str]
    status: str
    priority: str
    assigned_to: Optional[str]
    resolution: Optional[str]
    created_at: dt.datetime
    updated_at: dt.datetime
    resolved_at: Optional[dt.datetime]


# ---------- Rating (Phase 14) ----------

class RatingCreate(BaseModel):
    transaction_id: int
    rating: float = Field(ge=1.0, le=5.0)
    review: Optional[str] = ""


class RatingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    transaction_id: int
    rater_role: str
    rater_id: int
    ratee_role: str
    ratee_id: int
    rating: float
    review: Optional[str]
    created_at: dt.datetime
