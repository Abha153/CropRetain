# Negotiation, trust and QoS: feature-to-file status

Status of the code at `origin/main` 2c81ea6 (inspected 2026-10-19). "Implemented" means the code and tests exist in the committed source; it does **not** mean the tests were run in this review (the review sandbox could not install FastAPI/SQLAlchemy/pytest). All negotiation, trust, rating and verification code below came in the initial commit `781278a`.

## Existing negotiation features (committed source)
| Feature | Status | Where |
|---|---|---|
| Multi-round offers: counter, accept, reject, withdraw | Implemented | `models.py` (`BuyerOffer`, `BuyerOfferRound`, UNIQUE `offer_id,sequence`); `services/offer_negotiation.py`; `routers/offer_negotiation.py` (`GET /offers/awaiting-me`, `GET /offers/{id}`, `GET /offers/{id}/rounds`, `POST .../counter`, `.../rounds/{rid}/accept`, `.../reject`, `.../withdraw`); `schemas.py`; `frontend/src/components/OfferNegotiation.jsx`, `api/client.js` |
| State rules: strict turn-taking, stale-request 409, 20-round cap, no action after terminal state, no overselling, floor price hidden from the buyer | Implemented | `services/offer_negotiation.py` (`MAX_ROUNDS_PER_OFFER`, `require_*`, `validate_terms`, `finalize_acceptance`); DB uniqueness backstop; row lock (`SELECT ... FOR UPDATE`) only takes effect on PostgreSQL |
| Backfill of legacy offers into round 1 | Implemented | `backfill_offer_rounds` (runs at startup and lazily) |
| Tests | Present, unrun here | `tests/test_offer_negotiation.py` (24), `test_offer_negotiation_contract.py` (2), `test_offer_acceptance.py` (2) |
| Transport quote negotiation (separate flow) | Implemented | `routers/transport_negotiation.py`, `TransportOffer`, `TransportMessage`; `tests/test_transport_quote.py`, `test_transporter_workflow.py` |

## Audit trail and transaction history
| Feature | Status | Where |
|---|---|---|
| Offer rounds kept with sender, receiver, price, quantity, status, timestamps | Implemented | `BuyerOfferRound` |
| Transaction created on acceptance, with timeline events (`OFFER_CREATED`, `OFFER_COUNTERED`, `OFFER_ACCEPTED`) and later status events | Implemented | `models.py` (`Transaction`, `TransactionEvent`); `services/offer_negotiation.py::finalize_acceptance`; `routers/transactions.py` (`/mine`, `/{id}`, `/{id}/timeline`, `PATCH /{id}/status`); `pages/TransactionDetail.jsx` (Timeline) |
| Buyer verification audit log | Implemented | `BuyerVerificationAuditLog`; `routers/buyer_verification.py` |
| Login activity log | Implemented | `LoginEvent`, `services/login_tracking.py` |
| Tamper-evident agreement snapshot (hash of agreed terms) | **Missing** | Specified only in the QoS patch in history (`offer_agreements`, SHA-256) |
| Rejected/withdrawn threads in a transaction timeline | Partial | They stay in `BuyerOfferRound` history but no transaction exists for them |

## Buyer/seller trust summaries
| Feature | Status | Where |
|---|---|---|
| Independent trust signals computed from source rows, never a composite score; legacy stored scores deliberately ignored | Implemented | `services/trust_summary.py`; `routers/trust.py` (`/trust/me`, `/farmers/{id}`, `/buyers/{id}`, `/transporters/{id}`); `schemas.py` (`Trust*`); `tests/test_trust_summary.py` (30) |
| Ratings (farmer to buyer, buyer to farmer), one per transaction per rater | Implemented | `Rating` (UNIQUE `transaction_id,rater_role,rater_id`); `routers/ratings.py`; transport and trip reviews: `TransportReview`, `TripReview`, `routers/trip_reviews.py`; `tests/test_trip_reviews.py` |
| Buyer verification tiers | Implemented | `BuyerVerification`; `routers/buyer_verification.py`; `components/VerificationBadge.jsx`; `tests/test_buyer_verification.py` (9) |
| Frontend display of the trust summary | **Missing** | No page calls `/trust/*` |
| Seeded demo verification not counted as verified | Fixed in this change | `trust_summary._buyer_verification` returns `NOT_VERIFIED` / tier `DEMO_SEED` for `reviewed_by == "demo-seed"` |
| Seeded rating / reliability defaults shown as scores | Fixed in this change (Profile page) | `pages/Profile.jsx`. **Still open:** `services/buyer_matcher.py` ranks buyers using the seeded `Buyer.reliability_score` |

## QoS / reputation scoring (different from negotiation)
| Feature | Status | Where |
|---|---|---|
| Evidence-based buyer and transport reputation (pickup outcome, terms as agreed, final transport charge, delivery promise, cancellations), disputes with admin review, Wilson-bound ordering, "insufficient history" under 3 outcomes, demo payments excluded | **Missing from source** | Designed only in the patches stored in Git history: `a642df5:qos_negotiation_complete.patch` (51 files) and `b287387:merged_combined.patch`. Never committed as source files |
| Feasibility of porting | Unverified | A trial apply of the 51-file patch to current main in a scratch clone applied cleanly to 31 files (all new services, routers, components and tests) and left rejected hunks in 20 (registration, i18n, README, `main.py`, `App.jsx`, `Layout.jsx`). Nothing was run |

## Recommendation
Port the QoS patch on its own branch where CI can run: apply the 31 clean files, wire up the 20 rejected hunks by hand, then run `pytest` and the frontend build. Do not merge unrun.
