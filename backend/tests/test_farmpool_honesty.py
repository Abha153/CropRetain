"""
Regression test for the FarmPool data-honesty fix: shared_transport_plan()
must clearly flag that pool_partners are simulated, not real platform
users, so the frontend can render an honest disclaimer instead of
presenting fabricated farmer names as if they were real people.
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.services.transport_optimizer import shared_transport_plan, find_nearby_pool_partners


def test_shared_transport_plan_flags_simulated_partners():
    plan = shared_transport_plan("Tomato", "Bilaspur", 500, "Raipur")
    assert plan["pool_partners_are_simulated"] is True
    assert "disclaimer" in plan["pool_partners_disclaimer"].lower() or "simulated" in plan["pool_partners_disclaimer"].lower()
    assert len(plan["pool_partners"]) >= 2


def test_pool_partners_still_deterministic_after_fix():
    # The honesty fix must not change the underlying deterministic
    # simulation -- same crop+location must still produce the same
    # partner list across calls.
    a = find_nearby_pool_partners("Tomato", "Bilaspur", 500)
    b = find_nearby_pool_partners("Tomato", "Bilaspur", 500)
    assert a == b


def test_transport_cost_fields_still_labelled_estimated():
    # Preserve the existing "label": "ESTIMATED" honesty field -- the fix
    # must be additive, not a replacement of prior honesty work.
    plan = shared_transport_plan("Tomato", "Bilaspur", 500, "Raipur")
    assert plan["label"] == "ESTIMATED"
    assert plan["your_individual_transport_cost"] > 0
    assert plan["your_shared_transport_cost"] > 0
