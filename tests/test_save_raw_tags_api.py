"""Tests for SaveRawTags API endpoint with validation.

These tests demonstrate that HTTP 422 validation errors are properly returned
when required fields are missing or have invalid types. The errors are handled
at the Pydantic validation layer without interrupting the service.
"""

import pytest
from fastapi.testclient import TestClient

from main import app


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


class TestSaveRawTagsValidationErrors:
    """Test HTTP 422 validation error responses for save-raw-tags endpoint.

    Demonstrates that:
    1. Missing required fields return HTTP 422 with descriptive error messages
    2. Invalid field types return HTTP 422 without interrupting the service
    3. The service continues operating normally after validation errors
    """

    def test_missing_duration_seconds_returns_422(self, client):
        """Should return HTTP 422 when duration_seconds is missing."""
        payload = {
            "metadata": {"channel_list": [1, 2, 3], "target_file_path": "C:\\test.dat"}
        }

        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        error_details = data["detail"]
        assert any("duration_seconds" in str(error) for error in error_details)

    def test_missing_metadata_returns_422(self, client):
        """Should return HTTP 422 when metadata is missing."""
        payload = {"duration_seconds": 30}

        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        error_details = data["detail"]
        assert any("metadata" in str(error) for error in error_details)

    def test_missing_channel_list_returns_422(self, client):
        """Should return HTTP 422 when channel_list is missing from metadata."""
        payload = {
            "duration_seconds": 30,
            "metadata": {"target_file_path": "C:\\test.dat"},
        }

        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        error_details = data["detail"]
        assert any("channel_list" in str(error) for error in error_details)

    def test_missing_target_file_path_returns_422(self, client):
        """Should return HTTP 422 when target_file_path is missing from metadata."""
        payload = {"duration_seconds": 30, "metadata": {"channel_list": [1, 2, 3]}}

        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        error_details = data["detail"]
        assert any("target_file_path" in str(error) for error in error_details)

    def test_invalid_channel_list_type_returns_422(self, client):
        """Should return HTTP 422 when channel_list is not a list."""
        payload = {
            "duration_seconds": 30,
            "metadata": {
                "channel_list": "1,2,3",  # String instead of list
                "target_file_path": "C:\\test.dat",
            },
        }

        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_invalid_target_file_path_type_returns_422(self, client):
        """Should return HTTP 422 when target_file_path is not a string."""
        payload = {
            "duration_seconds": 30,
            "metadata": {
                "channel_list": [1, 2, 3],
                "target_file_path": 12345,  # Int instead of string
            },
        }

        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_invalid_duration_seconds_type_returns_422(self, client):
        """Should return HTTP 422 when duration_seconds is not an integer."""
        payload = {
            "duration_seconds": "thirty",  # String instead of int
            "metadata": {"channel_list": [1, 2, 3], "target_file_path": "C:\\test.dat"},
        }

        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_metadata_not_dict_returns_422(self, client):
        """Should return HTTP 422 when metadata is not a dict/object."""
        payload = {
            "duration_seconds": 30,
            "metadata": "not_a_dict",  # String instead of object
        }

        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_empty_metadata_returns_422(self, client):
        """Should return HTTP 422 when metadata is empty dict."""
        payload = {
            "duration_seconds": 30,
            "metadata": {},  # Empty dict missing both required fields
        }

        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    def test_service_continues_after_multiple_validation_errors(self, client):
        """Demonstrate service continues after multiple validation errors (no interruption)."""
        # Send multiple bad requests
        errors = []
        for bad_payload in [
            {"metadata": {"channel_list": [1, 2]}},  # Missing duration and path
            {"duration_seconds": 30},  # Missing metadata
            {
                "duration_seconds": "bad",
                "metadata": {"channel_list": [1]},
            },  # Wrong type
        ]:
            response = client.post(
                "/api/v1/measurements/save-raw-tags",
                json=bad_payload,
            )
            assert response.status_code == 422
            errors.append(response)

        # Verify service is still responsive
        health_response = client.get("/health")
        assert health_response.status_code == 200
        assert health_response.json()["status"] == "healthy"
