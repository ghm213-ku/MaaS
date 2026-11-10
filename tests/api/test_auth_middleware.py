import pytest
from fastapi.testclient import TestClient
from main import app
from app.services.auth_service import create_access_token
from app.api.dependencies import get_status_manager, get_job_processor

client = TestClient(app)

def mock_get_status_manager():
    from unittest.mock import MagicMock
    return MagicMock()

def mock_get_job_processor():
    from unittest.mock import MagicMock
    return MagicMock()

app.dependency_overrides[get_status_manager] = mock_get_status_manager
app.dependency_overrides[get_job_processor] = mock_get_job_processor

def test_protected_route_without_token():
    response = client.get("/api/v1/channels/")
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

def test_protected_route_with_valid_token():
    token = create_access_token(user_id=1, role="viewer")
    
    response = client.get(
        "/api/v1/channels/",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code != 401
    assert response.status_code != 403

def test_protected_route_invalid_token():
    response = client.get(
        "/api/v1/channels/",
        headers={"Authorization": "Bearer not.a.real.token"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid token"}

def test_unprotected_route():
    response = client.get("/docs")
    assert response.status_code == 200

def test_protected_route_missing_bearer_scheme():
    response = client.get(
        "/api/v1/channels/",
        headers={"Authorization": "Basic some_base64_string"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Not authenticated"}

def test_protected_route_expired_token():
    import jwt
    from datetime import datetime, timedelta, timezone
    from app.services.auth_service import JWT_SECRET, ALGORITHM
    
    # Manually create an expired token
    now = int(datetime.now(timezone.utc).timestamp())
    exp = now - 3600  # Expired an hour ago
    
    payload = {
        "sub": 1,
        "role": "viewer",
        "iat": now - 7200,
        "exp": exp
    }
    
    expired_token = jwt.encode(payload, JWT_SECRET, algorithm=ALGORITHM)
    
    response = client.get(
        "/api/v1/channels/",
        headers={"Authorization": f"Bearer {expired_token}"}
    )
    assert response.status_code == 401
    assert response.json() == {"detail": "Token expired"}

def test_audit_logger_called_on_state_change():
    from unittest.mock import patch
    token = create_access_token(user_id=1, role="operator")
    
    with patch("app.api.audit_route.log_audit_event") as mock_log:
        response = client.post(
            "/api/v1/channels/book",
            json={"booked_by": "test_user", "channels": [1, 2]},
            headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code in [200, 202, 400, 422] # It might be 422 if payload is incomplete, but it still gets logged
        mock_log.assert_called_once()
        
        # Verify the args passed to the logger
        kwargs = mock_log.call_args.kwargs
        assert kwargs["user_id"] == 1
        assert kwargs["role"] == "operator"
        assert kwargs["action"] == "book"
        assert kwargs["http_method"] == "POST"


def test_audit_logs_422_for_validation_errors():
    """The audit log records the 422 the client receives, not 500."""
    from unittest.mock import patch
    token = create_access_token(user_id=1, role="operator")

    with patch("app.api.audit_route.log_audit_event") as mock_log:
        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json={"duration_seconds": "bad", "metadata": {}},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 422
        mock_log.assert_called_once()
        kwargs = mock_log.call_args.kwargs
        assert kwargs["status"] == 422
        assert "Field required" in kwargs["message"]
        assert kwargs["target_hardware_id"] == "system"


def test_audit_target():
    from app.services.audit_logger import audit_target

    assert audit_target("DELETE", "/api/v1/measurements/abc-123") == "abc-123"
    assert audit_target("POST", "/api/v1/measurements/count-rate-live") == "system"
    assert audit_target("POST", "/api/v1/measurements/histogram-live") == "system"
    assert audit_target("POST", "/api/v1/channels/book") == "system"
