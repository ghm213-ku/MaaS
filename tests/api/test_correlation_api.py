"""Tests for correlation measurement API endpoints."""

import pytest
from unittest.mock import MagicMock, AsyncMock
from fastapi.testclient import TestClient
from datetime import datetime

from main import app
from app.services.status_manager import StatusManager, MeasurementStatus
from app.services.job_processor import JobProcessor
from app.api import channels, dependencies


@pytest.fixture
def test_client():
    """Create a test client with mocked dependencies."""
    measurements = {}
    booked_channels = {}

    def create_mock_status_manager():
        """Create a mock status manager that tracks state."""
        mock_status_manager = MagicMock(spec=StatusManager)

        def create_status_side_effect(
            status_id, measurement_type, duration_seconds, metadata
        ):
            measurements[status_id] = {
                "status_id": status_id,
                "status": MeasurementStatus.QUEUED.value,
                "measurement_type": measurement_type,
                "started_at": datetime.utcnow().isoformat(),
                "message": "Measurement queued",
                "metadata": metadata or {},
                "results": None,
            }
            return measurements[status_id]

        def get_status_side_effect(status_id):
            if status_id not in measurements:
                return None
            return measurements[status_id]

        def get_metadata_side_effect(status_id):
            if status_id not in measurements:
                return None
            return measurements[status_id].get("metadata", {})

        def validate_channels_side_effect(channels):
            """Check if channels are available."""
            for ch in channels:
                if ch in booked_channels:
                    raise ValueError(
                        f"Channel {ch} is already booked by {booked_channels[ch]}"
                    )

        def book_channels_side_effect(channels, user_name):
            """Book channels."""
            for ch in channels:
                booked_channels[ch] = user_name
            return {
                "booked_channels": channels,
                "booking_time": datetime.utcnow().isoformat(),
            }

        def release_channels_side_effect(user_name):
            """Release channels."""
            to_release = [
                ch for ch, owner in booked_channels.items() if owner == user_name
            ]
            for ch in to_release:
                del booked_channels[ch]

        mock_status_manager.get_booked_channels.return_value = {i: "test_user" for i in range(1, 201)}
        mock_status_manager.health_check.return_value = True
        mock_status_manager.create_status.side_effect = create_status_side_effect
        mock_status_manager.get_status.side_effect = get_status_side_effect
        mock_status_manager.get_metadata.side_effect = get_metadata_side_effect
        mock_status_manager.validate_channels.side_effect = (
            validate_channels_side_effect
        )
        mock_status_manager.book_channels.side_effect = book_channels_side_effect
        mock_status_manager.release_channels.side_effect = release_channels_side_effect

        return mock_status_manager

    mock_status_manager = create_mock_status_manager()
    mock_job_processor = MagicMock(spec=JobProcessor)
    mock_job_processor.enqueue_job = MagicMock()

    dependencies.set_services(mock_job_processor, mock_status_manager, None)

    return TestClient(app), mock_status_manager, mock_job_processor


class TestCorrelationMeasurementAPI:
    """Test correlation measurement API endpoints."""

    def test_post_correlation_measurement_success(self, test_client):
        """Should successfully start correlation measurement."""
        client, _, _ = test_client

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 1,
                "channel2": 2,
                "binwidth": 1000000000,
                "n_values": 100,
                "target_location": "desktop/MaasData/test",
            },
        }

        response = client.post("/api/v1/measurements/correlation", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["measurement_type"] == "correlation"
        assert data["status"] == "queued"
        assert "measurement_id" in data
        assert "message" in data

    def test_post_correlation_measurement_with_minimal_metadata(self, test_client):
        """Should accept correlation with only required channel fields."""
        client, _, _ = test_client

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 30,
            "metadata": {"user_name": "test_user", 
                "channel1": 1,
                "channel2": 2,
            },
        }

        response = client.post("/api/v1/measurements/correlation", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert data["measurement_type"] == "correlation"

    import pytest

    @pytest.mark.parametrize(
        "invalid_payload, expected_error_field",
        [
            (
                {
                    "measurement_type": "correlation",
                    "duration_seconds": 60,
                    "metadata": {"user_name": "test_user", "channel2": 2},
                },
                "channel1",
            ),
            (
                {
                    "measurement_type": "correlation",
                    "duration_seconds": 60,
                    "metadata": {"user_name": "test_user", "channel1": 1},
                },
                "channel2",
            ),
            (
                {
                    "measurement_type": "correlation",
                    "duration_seconds": 60,
                    "metadata": {"user_name": "test_user", "channel1": "not_int", "channel2": 2},
                },
                "channel1",
            ),
            (
                {
                    "measurement_type": "correlation",
                    "metadata": {"user_name": "test_user", "channel1": 1, "channel2": 2},
                },
                "duration_seconds",
            ),
            (
                {
                    "measurement_type": "correlation",
                    "duration_seconds": 60,
                },
                "metadata",
            ),
        ],
    )
    def test_post_correlation_measurement_validation_errors(
        self, test_client, invalid_payload, expected_error_field
    ):
        """Should reject payload with missing or invalid required fields."""
        client, _, _ = test_client

        response = client.post("/api/v1/measurements/correlation", json=invalid_payload)

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data
        assert any(expected_error_field in str(error) for error in data["detail"])

    def test_post_correlation_measurement_enqueues_job(self, test_client):
        """Should enqueue job for backend processing."""
        client, _, mock_processor = test_client

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 1,
                "channel2": 2,
            },
        }

        response = client.post("/api/v1/measurements/correlation", json=payload)

        assert response.status_code == 201
        assert mock_processor.enqueue_job.called

    def test_post_correlation_measurement_creates_status(self, test_client):
        """Should create status record in manager."""
        client, mock_manager, _ = test_client

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 1,
                "channel2": 2,
            },
        }

        response = client.post("/api/v1/measurements/correlation", json=payload)

        assert response.status_code == 201
        assert mock_manager.create_status.called

    def test_post_correlation_measurement_returns_measurement_id(self, test_client):
        """Should return unique measurement_id."""
        client, _, _ = test_client

        payload1 = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 1,
                "channel2": 2,
            },
        }

        payload2 = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 3,
                "channel2": 4,
            },
        }

        response1 = client.post("/api/v1/measurements/correlation", json=payload1)
        response2 = client.post("/api/v1/measurements/correlation", json=payload2)

        id1 = response1.json()["measurement_id"]
        id2 = response2.json()["measurement_id"]

        assert id1 != id2

    def test_post_correlation_measurement_with_custom_binwidth(self, test_client):
        """Should accept custom binwidth."""
        client, _, _ = test_client

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 1,
                "channel2": 2,
                "binwidth": 500000000,
            },
        }

        response = client.post("/api/v1/measurements/correlation", json=payload)

        assert response.status_code == 201

    def test_post_correlation_measurement_with_custom_n_values(self, test_client):
        """Should accept custom n_values."""
        client, _, _ = test_client

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 1,
                "channel2": 2,
                "n_values": 50,
            },
        }

        response = client.post("/api/v1/measurements/correlation", json=payload)

        assert response.status_code == 201

    def test_post_correlation_measurement_with_custom_target_location(
        self, test_client
    ):
        """Should accept custom target_location."""
        client, _, _ = test_client

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 1,
                "channel2": 2,
                "target_location": "custom/path/for/data",
            },
        }

        response = client.post("/api/v1/measurements/correlation", json=payload)

        assert response.status_code == 201

    def test_post_correlation_measurement_response_includes_started_at(
        self, test_client
    ):
        """Response should include started_at timestamp."""
        client, _, _ = test_client

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 1,
                "channel2": 2,
            },
        }

        response = client.post("/api/v1/measurements/correlation", json=payload)

        data = response.json()
        assert "started_at" in data

    def test_post_correlation_measurement_large_channel_numbers(self, test_client):
        """Should accept large channel numbers."""
        client, _, _ = test_client

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "channel1": 101,
                "channel2": 102,
            },
        }

        response = client.post("/api/v1/measurements/correlation", json=payload)

        assert response.status_code == 201
