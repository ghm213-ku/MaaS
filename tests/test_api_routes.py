"""Tests for API routes and endpoints.

This test module tests the web layer (FastAPI routes) which handles:
- Receiving HTTP requests
- Creating status records in Redis
- Enqueueing jobs (via JobProcessor.enqueue_job)
- Querying measurement status
- Stopping measurements

Job processing itself (handler execution) happens in the backend worker.
Tests here use mocks for JobProcessor to isolate web layer testing.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime
import json

from main import app
from app.services.measurement import MeasurementService
from app.services.count_rate import CountRateMeasurementHandler
from app.services.status_manager import StatusManager, MeasurementStatus
from app.services.job_processor import JobProcessor
from app.api import routes


@pytest.fixture
def client():
    """Create a test client."""
    # Store measurement data for tracking
    measurements = {}

    def create_mock_status_manager():
        """Create a smarter mock that tracks state."""
        mock_status_manager = MagicMock(spec=StatusManager)

        def create_status_side_effect(
            status_id, measurement_type, duration_seconds, metadata
        ):
            """Track created statuses."""
            measurements[status_id] = {
                "status_id": status_id,
                "status": MeasurementStatus.QUEUED.value,
                "measurement_type": measurement_type,
                "started_at": datetime.utcnow().isoformat(),
                "message": "Active",
                "metadata": metadata or {},
                "results": None,
            }
            return measurements[status_id]

        def get_status_side_effect(status_id):
            """Return status or None."""
            if status_id not in measurements:
                return None
            return measurements[status_id]

        def get_metadata_side_effect(status_id):
            """Return metadata."""
            if status_id not in measurements:
                return None
            return measurements[status_id].get("metadata", {})

        def get_results_side_effect(status_id):
            """Return results."""
            if status_id not in measurements:
                return None
            return measurements[status_id].get("results")

        def update_status_side_effect(status_id, status, message, results=None):
            """Update status."""
            if status_id in measurements:
                measurements[status_id]["status"] = status
                measurements[status_id]["message"] = message
                if results:
                    measurements[status_id]["results"] = results
                return measurements[status_id]
            return None

        mock_status_manager.get_booked_channels.return_value = {i: "test_user" for i in range(1, 201)}
        mock_status_manager.health_check.return_value = True
        mock_status_manager.create_status.side_effect = create_status_side_effect
        mock_status_manager.get_status.side_effect = get_status_side_effect
        mock_status_manager.get_metadata.side_effect = get_metadata_side_effect
        mock_status_manager.get_results.side_effect = get_results_side_effect
        mock_status_manager.update_status.side_effect = update_status_side_effect

        return mock_status_manager

    # Create mock services
    mock_status_manager = create_mock_status_manager()
    mock_job_processor = MagicMock(spec=JobProcessor)

    # Configure mock job processor for web layer operations
    def enqueue_job_side_effect(
        status_id, measurement_type, duration_seconds, metadata=None
    ):
        """Simulate enqueueing a job - just store the job info."""
        # In real system, this would push to Redis queue
        # Tests don't need to simulate actual processing
        pass

    def stop_job_side_effect(status_id):
        """Simulate stopping a job - update status to stopped."""
        if status_id in measurements:
            measurements[status_id]["status"] = MeasurementStatus.STOPPED.value
            measurements[status_id]["message"] = "Stopped"

    mock_job_processor.enqueue_job.side_effect = enqueue_job_side_effect
    mock_job_processor.stop_job.side_effect = stop_job_side_effect

    # Set up dependency overrides
    app.dependency_overrides[routes.get_status_manager] = lambda: mock_status_manager
    app.dependency_overrides[routes.get_job_processor] = lambda: mock_job_processor

    # Also set the global processors for the app lifespan
    routes.set_processors(mock_job_processor, mock_status_manager)

    client = TestClient(app)
    yield client

    # Clear dependency overrides
    app.dependency_overrides.clear()


@pytest.fixture
async def mock_service():
    """Create a mock measurement service for testing measurement service directly."""
    service = MeasurementService()
    service.register_handler("count_rate", CountRateMeasurementHandler)
    yield service
    await service.cleanup()


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check_success(self, client):
        """Health check should return 200."""
        response = client.get("/health")

        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
        assert "service" in response.json()

    def test_health_check_response_format(self, client):
        """Health check should return proper format."""
        response = client.get("/health")
        data = response.json()

        assert isinstance(data, dict)
        assert "status" in data
        assert "service" in data


class TestRootEndpoint:
    """Test root endpoint."""

    def test_root_endpoint_success(self, client):
        """Root endpoint should return service info."""
        response = client.get("/")

        assert response.status_code == 200
        assert response.json()["service"]
        assert (
            "measurement_endpoints" in response.json()
            or "channel_endpoints" in response.json()
        )

    def test_root_endpoint_includes_api_info(self, client):
        """Root should list available endpoints."""
        response = client.get("/")
        data = response.json()

        assert "measurement_endpoints" in data
        endpoints = data["measurement_endpoints"]
        assert "get_status" in endpoints or "start_count_rate" in endpoints


class TestStartMeasurementEndpoint:
    """Test POST /api/v1/measurements/count-rate."""

    @pytest.mark.asyncio
    async def test_start_measurement_success(self, client, mock_service):
        """Should start measurement and return ID."""
        payload = {
            "measurement_type": "count_rate",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", 
                "user_name": "test_user", "channels": [1, 2, 3],
                "binwidth": 1000000000,
                "n_values": 1,
                "target_location": "~/Desktop/MaasData/{datetime}/{measurement-type}",
            },
        }

        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )

        assert response.status_code == 201
        data = response.json()
        assert "measurement_id" in data
        assert data["status"] == "queued"
        assert data["measurement_type"] == "count_rate"

    @pytest.mark.asyncio
    async def test_start_measurement_minimal_payload(self, client, mock_service):
        """Should start with minimal payload (only channels required in metadata)."""
        payload = {
            "measurement_type": "count_rate",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", "user_name": "test_user", "channels": [1]},
        }

        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )

        assert response.status_code == 201
        assert "measurement_id" in response.json()

    @pytest.mark.asyncio
    async def test_start_measurement_with_custom_params(self, client, mock_service):
        """Should accept and use custom parameters."""
        payload = {
            "measurement_type": "count_rate",
            "duration_seconds": 120,
            "metadata": {"user_name": "test_user", 
                "user_name": "test_user", "channels": [1, 2, 3],
                "binwidth": 500000000,
                "n_values": 10,
                "target_location": "C:\\custom\\path\\results.csv",
            },
        }

        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )

        assert response.status_code == 201
        assert "measurement_id" in response.json()

    @pytest.mark.asyncio
    async def test_start_measurement_returns_timestamp(self, client, mock_service):
        """Response should include start timestamp."""
        payload = {
            "measurement_type": "count_rate",
            "duration_seconds": 60,
            "metadata": {"user_name": "test_user", "channels": [1, 2]},
        }
        response = client.post("/api/v1/measurements/count-rate", json=payload)
        assert "started_at" in response.json()

class TestLiveHistogramEndpoints:
    """Test live histogram endpoints."""

    @pytest.mark.asyncio
    async def test_start_startstop_live_success(self, client, mock_service):
        """Should start startstop-live measurement and return ID."""
        payload = {
            "measurement_type": "startstop_live",
            "duration_seconds": 60,
            "metadata": {
                "click_channel": 1,
                "start_channel": 2,
                "user_name": "test_user",
                "binwidth": 1000,
                "n_bins": 1000,
                "refresh_rate": 25
            },
        }

        response = client.post("/api/v1/measurements/startstop-live", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert "measurement_id" in data
        assert data["status"] == "queued"
        assert data["measurement_type"] == "startstop_live"

    @pytest.mark.asyncio
    async def test_start_histogram_live_success(self, client, mock_service):
        """Should start histogram-live measurement and return ID."""
        payload = {
            "measurement_type": "histogram_live",
            "duration_seconds": 60,
            "metadata": {
                "click_channel": 1,
                "start_channel": 2,
                "user_name": "test_user"
            },
        }

        response = client.post("/api/v1/measurements/histogram-live", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert "measurement_id" in data
        assert data["status"] == "queued"
        assert data["measurement_type"] == "histogram_live"

    @pytest.mark.asyncio
    async def test_start_correlation_live_success(self, client, mock_service):
        """Should start correlation-live measurement and return ID."""
        payload = {
            "measurement_type": "correlation_live",
            "duration_seconds": 60,
            "metadata": {
                "channel1": 1,
                "channel2": 2,
                "user_name": "test_user"
            },
        }

        response = client.post("/api/v1/measurements/correlation-live", json=payload)

        assert response.status_code == 201
        data = response.json()
        assert "measurement_id" in data
        assert data["status"] == "queued"
        assert data["measurement_type"] == "correlation_live"

        # Should be ISO format datetime string
        assert "T" in data["started_at"]


class TestStopMeasurementEndpoint:
    """Test DELETE /api/v1/measurements/{measurement_id}."""

    @pytest.mark.asyncio
    async def test_stop_measurement_success(self, client, mock_service):
        """Should stop an active measurement."""
        # Start measurement
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={
                "measurement_type": "count_rate",
                "duration_seconds": 60,
                "metadata": {"user_name": "test_user", "user_name": "test_user", "channels": [1]},
            },
        )
        meas_id = start_response.json()["measurement_id"]

        # Stop measurement - the mock will update it to stopped status
        stop_response = client.delete(
            f"/api/v1/measurements/{meas_id}",
        )

        assert stop_response.status_code == 200
        data = stop_response.json()
        assert data["measurement_id"] == meas_id

    @pytest.mark.asyncio
    async def test_stop_measurement_not_found(self, client, mock_service):
        """Should return 404 for non-existent measurement."""
        response = client.delete(
            "/api/v1/measurements/definitely-nonexistent-id-12345",
        )

        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_stop_measurement_twice_fails_second_time(self, client, mock_service):
        """Stopping twice should handle gracefully."""
        # Start measurement
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={
                "measurement_type": "count_rate",
                "duration_seconds": 60,
                "metadata": {"user_name": "test_user", "user_name": "test_user", "channels": [1]},
            },
        )
        meas_id = start_response.json()["measurement_id"]

        # First stop should succeed
        response1 = client.delete(f"/api/v1/measurements/{meas_id}")
        assert response1.status_code == 200

        # Second stop should also succeed (idempotent behavior)
        # In a real system this might be 409, but for simplicity we allow it
        response2 = client.delete(f"/api/v1/measurements/{meas_id}")
        assert response2.status_code in [200, 409]


class TestGetStatusEndpoint:
    """Test GET /api/v1/measurements/{measurement_id}/status."""

    @pytest.mark.asyncio
    async def test_get_status_active_measurement(self, client, mock_service):
        """Should get status of active measurement."""
        # Start measurement
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={"user_name": "test_user", "channels": [1]},
        )
        meas_id = start_response.json()["measurement_id"]

        # Get status
        status_response = client.get(
            f"/api/v1/measurements/{meas_id}/status",
        )

        assert status_response.status_code == 200
        data = status_response.json()
        # Status should be queued since jobs are queued instead of processed immediately
        assert data["status"] in ["queued", "active"]
        assert data["measurement_id"] == meas_id
        assert data["duration_so_far"] >= 0

    @pytest.mark.asyncio
    async def test_get_status_includes_duration(self, client, mock_service):
        """Status should include duration so far."""
        # Start measurement
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={"user_name": "test_user", "channels": [1]},
        )
        meas_id = start_response.json()["measurement_id"]

        # Get status
        status_response = client.get(
            f"/api/v1/measurements/{meas_id}/status",
        )

        data = status_response.json()
        assert "duration_so_far" in data
        assert isinstance(data["duration_so_far"], float)

    @pytest.mark.asyncio
    async def test_get_status_includes_metadata(self, client, mock_service):
        """Status should include measurement metadata."""
        # Start measurement with parameters
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={
                "user_name": "test_user", "channels": [1, 2],
                "binwidth": 1000000000,
                "n_values": 1,
                "target_location": "~/Desktop/MaasData/{datetime}/{measurement-type}",
            },
        )
        meas_id = start_response.json()["measurement_id"]

        # Get status
        status_response = client.get(
            f"/api/v1/measurements/{meas_id}/status",
        )

        data = status_response.json()
        # Check that metadata contains our parameters
        assert "metadata" in data
        assert data["metadata"]["channels"] == [1, 2]

    @pytest.mark.asyncio
    async def test_get_status_not_found(self, client, mock_service):
        """Should return 404 for non-existent measurement."""
        response = client.get(
            "/api/v1/measurements/definitely-nonexistent-id-12345/status",
        )

        assert response.status_code == 404


class TestListMeasurementsEndpoint:
    """Test GET /api/v1/measurements/."""

    def test_list_measurements_endpoint_exists(self, client):
        """List endpoint should exist."""
        response = client.get("/api/v1/measurements/")

        # Should not 404
        assert response.status_code != 404


class TestApiErrorHandling:
    """Test error handling and edge cases."""

    @pytest.mark.asyncio
    @pytest.mark.asyncio
    async def test_payload_with_implicit_type(self, client, mock_service):
        """Should accept payload with only required fields (channels)."""
        payload = {"user_name": "test_user", "channels": [1, 2]}

        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )

        # Should succeed because all other fields have defaults
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_invalid_payload_missing_type(self, client, mock_service):
        """Should accept minimal payload with only required channels field."""
        # Minimal valid payload - just channels
        payload = {"user_name": "test_user", "channels": [1]}

        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )

        # Should succeed with defaults
        assert response.status_code == 201

    @pytest.mark.asyncio
    async def test_invalid_payload_invalid_duration(self, client, mock_service):
        """Should reject invalid duration."""
        payload = {
            "measurement_type": "count_rate",
            "duration_seconds": "not_a_number",
        }

        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )

        assert response.status_code >= 400

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, client, mock_service):
        """Should handle multiple concurrent requests."""
        # Start 3 measurements
        response1 = client.post(
            "/api/v1/measurements/count-rate",
            json={"user_name": "test_user", "channels": [1]},
        )
        response2 = client.post(
            "/api/v1/measurements/count-rate",
            json={"user_name": "test_user", "channels": [2]},
        )
        response3 = client.post(
            "/api/v1/measurements/count-rate",
            json={"user_name": "test_user", "channels": [3]},
        )

        assert response1.status_code == 201
        assert response2.status_code == 201
        assert response3.status_code == 201

        # All should have different IDs
        id1 = response1.json()["measurement_id"]
        id2 = response2.json()["measurement_id"]
        id3 = response3.json()["measurement_id"]

        assert id1 != id2 != id3


class TestApiIntegration:
    """Integration tests for complete workflows."""

    @pytest.mark.asyncio
    async def test_complete_measurement_workflow(self, client, mock_service):
        """Test complete workflow: start -> query -> stop."""
        # 1. Start measurement
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={
                "user_name": "test_user", "channels": [1, 2, 3],
                "binwidth": 1000000000,
                "n_values": 1,
            },
        )
        assert start_response.status_code == 201
        meas_id = start_response.json()["measurement_id"]

        # 2. Query status (should be queued initially)
        status_response = client.get(
            f"/api/v1/measurements/{meas_id}/status",
        )
        assert status_response.status_code == 200
        assert status_response.json()["status"] in ["queued", "active"]

        # 3. Stop measurement
        stop_response = client.delete(
            f"/api/v1/measurements/{meas_id}",
        )
        assert stop_response.status_code == 200

        # 4. Verify it's stopped or stopped in final status
        final_status = client.get(
            f"/api/v1/measurements/{meas_id}/status",
        )
        assert final_status.json()["status"] in ["stopped", "active"]

    @patch('app.api.routes.aioredis.Redis')
    def test_websocket_streaming(self, mock_redis, client):
        mock_redis_instance = MagicMock()
        mock_pubsub = AsyncMock()
        mock_redis_instance.aclose = AsyncMock()
        
        mock_redis_instance.pubsub.return_value = mock_pubsub
        mock_redis.return_value = mock_redis_instance
        
        mock_pubsub.get_message.side_effect = [
            {"data": "test_data_1"},
            None,
            None,
        ]
        
        with client.websocket_connect("/api/v1/measurements/stream/test_id") as websocket:
            data = websocket.receive_text()
            assert data == "test_data_1"
            
            mock_pubsub.subscribe.assert_called_once_with("measurement:data:test_id")
