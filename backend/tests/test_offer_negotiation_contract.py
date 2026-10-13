"""
Contract test: every /offers/... call in frontend/src/api/client.js must map
to a real route (path + HTTP method) registered by the backend. Guards
against the frontend and backend drifting apart.
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI

from app.routers import offers as offers_router
from app.routers import offer_negotiation as neg_router

CLIENT = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "src", "api", "client.js")


def _backend_routes():
    app = FastAPI()
    app.include_router(offers_router.router)
    app.include_router(neg_router.router)
    return [(re.sub(r"\{[^}]+\}", "{}", r.path), m) for r in app.routes if hasattr(r, "methods") for m in r.methods]


def _frontend_calls():
    src = open(CLIENT, encoding="utf-8").read()
    calls = []
    for m in re.finditer(r"request\(\s*[`'](/offers[^`']*)[`'](?:\s*,\s*\{([^}]*)\})?", src):
        path = re.sub(r"\$\{[^}]+\}", "{}", m.group(1))
        opts = m.group(2) or ""
        method = re.search(r"method:\s*'(\w+)'", opts)
        calls.append((path, method.group(1) if method else "GET"))
    return calls


def test_frontend_offer_calls_match_backend_routes():
    routes = set(_backend_routes())
    calls = _frontend_calls()
    assert len(calls) >= 12, calls      # legacy 7 + 7 negotiation methods (create/list share paths)
    missing = [c for c in calls if c not in routes]
    assert not missing, f"frontend calls with no backend route: {missing}"


def test_negotiation_methods_present_in_client():
    src = open(CLIENT, encoding="utf-8").read()
    for name in ("offersAwaitingMe", "offerThread", "offerRounds", "counterOffer",
                 "acceptOfferRound", "rejectOfferRound", "withdrawOffer"):
        assert re.search(rf"\b{name}:", src), name
