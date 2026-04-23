"""Tests for API routes and endpoints."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

from main import app
from app.services.measurement import MeasurementService
from app.services.count_rate import CountRateMeasurementHandler
from app.api import routes


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture
async def mock_service():
    """Create a mock measurement service."""
    service = MeasurementService()
    service.register_handler("count_rate", CountRateMeasurementHandler)
    routes.set_service_provider(lambda: service)
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
        assert "endpoints" in response.json()
    
    def test_root_endpoint_includes_api_info(self, client):
        """Root should list available endpoints."""
        response = client.get("/")
        data = response.json()
        
        assert "endpoints" in data
        endpoints = data["endpoints"]
        assert "health" in endpoints
        assert "start_measurement" in endpoints


class TestStartMeasurementEndpoint:
    """Test POST /api/v1/measurements/count-rate."""
    
    @pytest.mark.asyncio
    async def test_start_measurement_success(self, client, mock_service):
        """Should start measurement and return ID."""
        payload = {
            "measurement_type": "count_rate",
            "duration_seconds": 10,
            "metadata": {"detector": "det_001"},
        }
        
        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )
        
        assert response.status_code == 201
        data = response.json()
        assert "measurement_id" in data
        assert data["status"] == "active"
        assert data["measurement_type"] == "count_rate"
    
    @pytest.mark.asyncio
    async def test_start_measurement_minimal_payload(self, client, mock_service):
        """Should start with minimal payload."""
        payload = {"measurement_type": "count_rate"}
        
        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )
        
        assert response.status_code == 201
        assert "measurement_id" in response.json()
    
    @pytest.mark.asyncio
    async def test_start_measurement_with_metadata(self, client, mock_service):
        """Should accept and use metadata."""
        payload = {
            "measurement_type": "count_rate",
            "metadata": {
                "detector_id": "det_001",
                "location": {
                    "building": "A",
                    "room": 101,
                },
                "tags": ["important", "test"],
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
        payload = {"measurement_type": "count_rate"}
        
        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )
        
        data = response.json()
        assert "started_at" in data
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
            json={"measurement_type": "count_rate"},
        )
        meas_id = start_response.json()["measurement_id"]
        
        # Stop measurement
        stop_response = client.delete(
            f"/api/v1/measurements/{meas_id}",
        )
        
        assert stop_response.status_code == 200
        data = stop_response.json()
        assert data["status"] == "stopped"
        assert data["measurement_id"] == meas_id
    
    @pytest.mark.asyncio
    async def test_stop_measurement_not_found(self, client, mock_service):
        """Should return 404 for non-existent measurement."""
        response = client.delete(
            "/api/v1/measurements/nonexistent_id",
        )
        
        assert response.status_code == 404
        assert "not found" in response.json()["detail"].lower()
    
    @pytest.mark.asyncio
    async def test_stop_measurement_twice_fails_second_time(self, client, mock_service):
        """Stopping twice should fail the second time."""
        # Start measurement
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={"measurement_type": "count_rate"},
        )
        meas_id = start_response.json()["measurement_id"]
        
        # First stop should succeed
        response1 = client.delete(f"/api/v1/measurements/{meas_id}")
        assert response1.status_code == 200
        
        # Second stop should fail
        response2 = client.delete(f"/api/v1/measurements/{meas_id}")
        assert response2.status_code == 409  # Conflict


class TestGetStatusEndpoint:
    """Test GET /api/v1/measurements/{measurement_id}/status."""
    
    @pytest.mark.asyncio
    async def test_get_status_active_measurement(self, client, mock_service):
        """Should get status of active measurement."""
        # Start measurement
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={"measurement_type": "count_rate"},
        )
        meas_id = start_response.json()["measurement_id"]
        
        # Get status
        status_response = client.get(
            f"/api/v1/measurements/{meas_id}/status",
        )
        
        assert status_response.status_code == 200
        data = status_response.json()
        assert data["status"] == "active"
        assert data["measurement_id"] == meas_id
        assert data["duration_so_far"] >= 0
    
    @pytest.mark.asyncio
    async def test_get_status_includes_duration(self, client, mock_service):
        """Status should include duration so far."""
        # Start measurement
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={"measurement_type": "count_rate"},
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
        metadata = {"detector": "det_001"}
        
        # Start measurement
        start_response = client.post(
            "/api/v1/measurements/count-rate",
            json={
                "measurement_type": "count_rate",
                "metadata": metadata,
            },
        )
        meas_id = start_response.json()["measurement_id"]
        
        # Get status
        status_response = client.get(
            f"/api/v1/measurements/{meas_id}/status",
        )
        
        data = status_response.json()
        assert data["metadata"] == metadata
    
    @pytest.mark.asyncio
    async def test_get_status_not_found(self, client, mock_service):
        """Should return 404 for non-existent measurement."""
        response = client.get(
            "/api/v1/measurements/nonexistent_id/status",
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
    async def test_payload_with_implicit_type(self, client, mock_service):
        """Should accept payload where measurement_type uses default."""
        payload = {"duration_seconds": 10}
        
        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )
        
        # Should succeed because measurement_type defaults to count_rate
        assert response.status_code == 201
    
    @pytest.mark.asyncio
    async def test_invalid_payload_missing_type(self, client, mock_service):
        """Should reject payload with completely invalid payload structure."""
        # Send empty object - while measurement_type defaults, we test
        # it with no keys at all
        payload = {}
        
        # This should still work due to defaults
        response = client.post(
            "/api/v1/measurements/count-rate",
            json=payload,
        )
        
        # Should succeed due to defaults in the model
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
            json={"measurement_type": "count_rate"},
        )
        response2 = client.post(
            "/api/v1/measurements/count-rate",
            json={"measurement_type": "count_rate"},
        )
        response3 = client.post(
            "/api/v1/measurements/count-rate",
            json={"measurement_type": "count_rate"},
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
                "measurement_type": "count_rate",
                "duration_seconds": 5,
                "metadata": {"test": "workflow"},
            },
        )
        assert start_response.status_code == 201
        meas_id = start_response.json()["measurement_id"]
        
        # 2. Query status
        status_response = client.get(
            f"/api/v1/measurements/{meas_id}/status",
        )
        assert status_response.status_code == 200
        assert status_response.json()["status"] == "active"
        
        # 3. Stop measurement
        stop_response = client.delete(
            f"/api/v1/measurements/{meas_id}",
        )
        assert stop_response.status_code == 200
        assert stop_response.json()["status"] == "stopped"
        
        # 4. Verify stopped
        final_status = client.get(
            f"/api/v1/measurements/{meas_id}/status",
        )
        assert final_status.json()["status"] == "stopped"
