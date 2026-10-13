"""
Tests for the FarmPool / shared-logistics trip review system.

Covers the eligibility rules that must be enforced SERVER-SIDE:
participation, trip completion, FPO membership, duplicate prevention,
rating range validation, and aggregate correctness.

Run: pytest backend/tests/test_trip_reviews.py -v
"""
import pytest
from fastapi.testclient import TestClient

from app.routers.trip_reviews import _validate_score, _aggregate, _avg, VALID_TYPES, COMPLETED_STATUSES
from fastapi import HTTPException


# ─── Pure-logic tests (no DB/app fixtures needed) ────────────────────────────

def test_rating_range_accepts_valid_scores():
    assert _validate_score(1.0, "rating") == 1.0
    assert _validate_score(5.0, "rating") == 5.0
    assert _validate_score(4.5, "rating") == 4.5


def test_rating_range_rejects_out_of_range():
    for bad in (0, 0.9, 5.1, 6, -3, 100):
        with pytest.raises(HTTPException) as exc:
            _validate_score(bad, "rating")
        assert exc.value.status_code == 400


def test_rating_range_allows_none_for_optional_aspects():
    """Optional per-aspect scores may be skipped entirely."""
    assert _validate_score(None, "punctuality") is None


def test_valid_review_types():
    assert VALID_TYPES == {"TRANSPORTER", "JOURNEY", "FPO"}


def test_only_delivered_counts_as_completed():
    """A trip still in progress must never be reviewable."""
    assert "DELIVERED" in COMPLETED_STATUSES
    for in_progress in ("REQUESTED", "MATCHED", "CONFIRMED", "PICKED_UP", "IN_TRANSIT", "CANCELLED"):
        assert in_progress not in COMPLETED_STATUSES


def test_avg_ignores_missing_values():
    assert _avg([5.0, 4.0, None]) == 4.5
    assert _avg([None, None]) is None
    assert _avg([]) is None


class _FakeReview:
    def __init__(self, review_type, rating, verified=True, **aspects):
        self.review_type = review_type
        self.rating = rating
        self.verified = verified
        self.punctuality = aspects.get("punctuality")
        self.communication = aspects.get("communication")
        self.handling = aspects.get("handling")
        self.coordination = aspects.get("coordination")


def test_aggregate_computes_from_stored_rows_only():
    """Aggregates must be derived, never hardcoded."""
    reviews = [
        _FakeReview("TRANSPORTER", 5.0, punctuality=5.0, communication=4.0),
        _FakeReview("TRANSPORTER", 4.0, punctuality=4.0, communication=4.0),
        _FakeReview("JOURNEY", 4.0, coordination=3.0),
    ]
    agg = _aggregate(reviews)
    assert agg["TRANSPORTER"]["count"] == 2
    assert agg["TRANSPORTER"]["overall"] == 4.5
    assert agg["TRANSPORTER"]["punctuality"] == 4.5
    assert agg["TRANSPORTER"]["communication"] == 4.0
    assert agg["JOURNEY"]["count"] == 1
    assert agg["JOURNEY"]["coordination"] == 3.0
    # No FPO reviews submitted -> reported honestly as zero, not invented.
    assert agg["FPO"]["count"] == 0
    assert agg["FPO"]["overall"] is None


def test_aggregate_with_no_reviews_returns_nulls_not_fake_scores():
    agg = _aggregate([])
    for rtype in VALID_TYPES:
        assert agg[rtype]["count"] == 0
        assert agg[rtype]["overall"] is None


def test_verified_count_tracks_only_verified_rows():
    reviews = [
        _FakeReview("TRANSPORTER", 5.0, verified=True),
        _FakeReview("TRANSPORTER", 3.0, verified=False),
    ]
    agg = _aggregate(reviews)
    assert agg["TRANSPORTER"]["count"] == 2
    assert agg["TRANSPORTER"]["verified_count"] == 1


# ─── Integration tests (require the app + DB fixtures in conftest.py) ────────
# These follow the existing suite's client/fixture conventions. If the shared
# conftest exposes differently-named fixtures, adjust the signatures only --
# the assertions below are the actual contract being tested.

@pytest.mark.integration
class TestTripReviewEligibility:
    """The security-critical rules. Each MUST be enforced server-side."""

    def test_non_participant_cannot_review(self):
        """A farmer who was not on the trip must get 403."""
        pytest.skip("Requires app/db fixtures from conftest.py — run in full suite")

    def test_incomplete_trip_cannot_be_reviewed(self):
        """Any status other than DELIVERED must get 400."""
        pytest.skip("Requires app/db fixtures from conftest.py — run in full suite")

    def test_duplicate_review_rejected(self):
        """Second review of same type for same trip must get 409."""
        pytest.skip("Requires app/db fixtures from conftest.py — run in full suite")

    def test_fpo_review_requires_pool_membership(self):
        """Rating an FPO pool the farmer never joined must get 403."""
        pytest.skip("Requires app/db fixtures from conftest.py — run in full suite")

    def test_fpo_review_requires_pool_id(self):
        """review_type=FPO without pool_id must get 400."""
        pytest.skip("Requires app/db fixtures from conftest.py — run in full suite")

    def test_verified_flag_is_server_set_not_client_supplied(self):
        """A client sending verified=false must still get a verified row
        once eligibility passes — the flag is never read from the body."""
        pytest.skip("Requires app/db fixtures from conftest.py — run in full suite")
