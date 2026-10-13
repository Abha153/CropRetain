import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.services import agmarknet_service


def _response(status_code=200, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def test_prices_use_documented_bearer_auth_and_body():
    original_key = settings.ceda_api_key
    settings.ceda_api_key = "test-key"
    try:
        with patch("httpx.Client.request") as request:
            request.return_value = _response(200, {"data": []})
            agmarknet_service.get_prices(
                1, 8, "2026-01-01", "2026-01-31",
                district_id=104, market_id=[255, 3149],
            )
            kwargs = request.call_args.kwargs
            assert kwargs["headers"] == {"Authorization": "Bearer test-key"}
            assert kwargs["json"] == {
                "commodity_id": 1,
                "state_id": 8,
                "district_id": [104],
                "market_id": [255, 3149],
                "from_date": "2026-01-01",
                "to_date": "2026-01-31",
            }
    finally:
        settings.ceda_api_key = original_key


def test_unauthorized_response_is_not_exposed():
    original_key = settings.ceda_api_key
    settings.ceda_api_key = "test-key"
    try:
        with patch("httpx.Client.request", return_value=_response(401, {})):
            try:
                agmarknet_service.get_commodities()
                assert False, "expected AgmarknetError"
            except agmarknet_service.AgmarknetError as exc:
                assert "test-key" not in str(exc)
                assert "Bearer" not in str(exc)
    finally:
        settings.ceda_api_key = original_key


def test_missing_key_fails_without_making_a_request():
    original_key = settings.ceda_api_key
    settings.ceda_api_key = ""
    try:
        with patch("httpx.Client.request") as request:
            try:
                agmarknet_service.get_commodities()
                assert False, "expected AgmarknetError"
            except agmarknet_service.AgmarknetError as exc:
                assert "not configured" in str(exc)
            request.assert_not_called()
    finally:
        settings.ceda_api_key = original_key


def test_rate_limit_and_malformed_json_are_safe_errors():
    original_key = settings.ceda_api_key
    settings.ceda_api_key = "test-key"
    try:
        with patch("httpx.Client.request", return_value=_response(429, {})):
            try:
                agmarknet_service.get_geographies()
                assert False, "expected AgmarknetError"
            except agmarknet_service.AgmarknetError as exc:
                assert str(exc) == "CEDA rate limit exceeded"

        bad_response = _response(200, None)
        bad_response.json.side_effect = ValueError("bad json")
        with patch("httpx.Client.request", return_value=bad_response):
            try:
                agmarknet_service._request("GET", "/agmarknet/geographies")
                assert False, "expected AgmarknetError"
            except agmarknet_service.AgmarknetError as exc:
                assert str(exc) == "CEDA returned invalid JSON"
    finally:
        settings.ceda_api_key = original_key
