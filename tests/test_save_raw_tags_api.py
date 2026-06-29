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
    """Create a test client with mocked processors to allow dependency resolution."""
    from unittest.mock import MagicMock
    from app.services.status_manager import StatusManager
    from app.services.job_processor import JobProcessor
    from app.api import routes

    mock_status_manager = MagicMock(spec=StatusManager)
    mock_status_manager.health_check.return_value = True
    
    # We also need default behavior for validate_channels and book_channels
    mock_status_manager.validate_channels.return_value = None
    mock_status_manager.book_channels.return_value = {
        "booked_channels": [1, 2, 3],
        "booking_time": "2026-06-25T11:42:06",
    }
    
    mock_job_processor = MagicMock(spec=JobProcessor)

    # Set up dependency overrides
    app.dependency_overrides[routes.get_status_manager] = lambda: mock_status_manager
    app.dependency_overrides[routes.get_job_processor] = lambda: mock_job_processor
    routes.set_processors(mock_job_processor, mock_status_manager)

    client = TestClient(app)
    yield client

    app.dependency_overrides.clear()


class TestSaveRawTagsValidationErrors:
    """Test HTTP 422 validation error responses for save-raw-tags endpoint.

    Demonstrates that:
    1. Missing required fields return HTTP 422 with descriptive error messages
    2. Invalid field types return HTTP 422 without interrupting the service
    3. The service continues operating normally after validation errors
    """

    import pytest

    @pytest.mark.parametrize(
        "invalid_payload, expected_error_field",
        [
            (
                {"metadata": {"channel_list": [1, 2, 3], "target_file_path": "C:\\test.dat"}},
                "duration_seconds",
            ),
            (
                {"duration_seconds": 30},
                "metadata",
            ),
            (
                {
                    "duration_seconds": 30,
                    "metadata": {"target_file_path": "C:\\test.dat"},
                },
                "channel_list",
            ),
            (
                {"duration_seconds": 30, "metadata": {"channel_list": [1, 2, 3]}},
                "target_file_path",
            ),
            (
                {
                    "duration_seconds": 30,
                    "metadata": {
                        "channel_list": "1,2,3",
                        "target_file_path": "C:\\test.dat",
                    },
                },
                "channel_list",
            ),
            (
                {
                    "duration_seconds": 30,
                    "metadata": {
                        "channel_list": [1, 2, 3],
                        "target_file_path": 12345,
                    },
                },
                "target_file_path",
            ),
            (
                {
                    "duration_seconds": "thirty",
                    "metadata": {"channel_list": [1, 2, 3], "target_file_path": "C:\\test.dat"},
                },
                "duration_seconds",
            ),
            (
                {
                    "duration_seconds": 30,
                    "metadata": "not_a_dict",
                },
                "metadata",
            ),
            (
                {
                    "duration_seconds": 30,
                    "metadata": {},
                },
                "channel_list",  # Either channel_list or target_file_path will be in the errors
            ),
        ],
    )
    def test_save_raw_tags_validation_errors(self, client, invalid_payload, expected_error_field):
        """Should return HTTP 422 for invalid payloads."""
        response = client.post(
            "/api/v1/measurements/save-raw-tags",
            json=invalid_payload,
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert any(expected_error_field in str(error) for error in data["detail"])

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
