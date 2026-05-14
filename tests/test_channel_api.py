"""Comprehensive tests for Channel Management API endpoints.

This test module tests the channel management endpoints at /api/v1/channels/
including:
- List all channels (GET /api/v1/channels/)
- List available channels (GET /api/v1/channels/available)
- Book channels (POST /api/v1/channels/book)
- Release channels (POST /api/v1/channels/release/{booked_by})

Tests verify proper channel state management, validation, and error handling.
"""

import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from datetime import datetime

from main import app
from app.services.status_manager import StatusManager
from app.services.job_processor import JobProcessor
from app.api import routes


@pytest.fixture
def client():
    """Create a test client with mocked channel management."""
    # Channel state tracking
    booked_channels = {}  # {channel: booked_by}
    available_channels = list(range(1, 17)) + list(range(101, 117)) + list(range(201, 217))
    
    def create_mock_status_manager():
        """Create a mock status manager with full channel functionality."""
        mock_status_manager = MagicMock(spec=StatusManager)
        
        # Channel validation
        def validate_channels_side_effect(channels):
            """Validate channels exist and are valid."""
            valid_channels = list(range(1, 17)) + list(range(101, 117)) + list(range(201, 217))
            for ch in channels:
                if ch not in valid_channels:
                    raise ValueError(f"Invalid channel number: {ch}")
        
        # Get all channels with status
        def get_all_channels_side_effect():
            """Return all channels with their status."""
            all_channels = list(range(1, 17)) + list(range(101, 117)) + list(range(201, 217))
            result = []
            for ch in all_channels:
                status = "booked" if ch in booked_channels else "available"
                booked_by = booked_channels.get(ch)
                result.append({
                    "channel": ch,
                    "status": status,
                    "booked_by": booked_by,
                })
            return result
        
        # Get available channels
        def get_available_channels_side_effect():
            """Return list of available channels."""
            all_channels = list(range(1, 17)) + list(range(101, 117)) + list(range(201, 217))
            return [ch for ch in all_channels if ch not in booked_channels]
        
        # Get booked channels
        def get_booked_channels_side_effect():
            """Return mapping of booked channels to booked_by identifiers."""
            return dict(booked_channels)
        
        # Get booked channels by identifier
        def get_booked_channels_by_side_effect(booked_by):
            """Return channels booked by a specific identifier."""
            return [ch for ch, by in booked_channels.items() if by == booked_by]
        
        # Get channel stats
        def get_channel_stats_side_effect():
            """Return channel statistics."""
            all_channels = list(range(1, 17)) + list(range(101, 117)) + list(range(201, 217))
            available = len(get_available_channels_side_effect())
            booked = len(booked_channels)
            total = len(all_channels)
            utilization = (booked / total * 100) if total > 0 else 0
            
            return {
                "total_channels": total,
                "available_channels": available,
                "booked_channels": booked,
                "utilization_percent": utilization,
            }
        
        # Book channels
        def book_channels_side_effect(channels, booked_by):
            """Book channels for a measurement or user."""
            # Validate first
            validate_channels_side_effect(channels)
            
            # Check if any are already booked
            already_booked = [ch for ch in channels if ch in booked_channels]
            if already_booked:
                raise ValueError(f"Channels already booked: {already_booked}")
            
            # Book the channels
            for ch in channels:
                booked_channels[ch] = booked_by
            
            return {
                "booked_by": booked_by,
                "booked_channels": channels,
                "booking_time": datetime.utcnow().isoformat(),
                "total_booked": len(channels),
            }
        
        # Release channels
        def release_channels_side_effect(booked_by):
            """Release all channels booked by an identifier."""
            released = []
            for ch, by in list(booked_channels.items()):
                if by == booked_by:
                    del booked_channels[ch]
                    released.append(ch)
            
            return {
                "booked_by": booked_by,
                "released_channels": released,
                "total_released": len(released),
            }
        
        # Health check
        mock_status_manager.health_check.return_value = True
        
        # Channel methods
        mock_status_manager.validate_channels.side_effect = validate_channels_side_effect
        mock_status_manager.get_all_channels.side_effect = get_all_channels_side_effect
        mock_status_manager.get_available_channels.side_effect = get_available_channels_side_effect
        mock_status_manager.get_booked_channels.side_effect = get_booked_channels_side_effect
        mock_status_manager.get_booked_channels_by.side_effect = get_booked_channels_by_side_effect
        mock_status_manager.get_channel_stats.side_effect = get_channel_stats_side_effect
        mock_status_manager.book_channels.side_effect = book_channels_side_effect
        mock_status_manager.release_channels.side_effect = release_channels_side_effect
        
        return mock_status_manager
    
    # Create mocks
    mock_status_manager = create_mock_status_manager()
    mock_job_processor = MagicMock(spec=JobProcessor)
    
    # Set up dependency overrides
    app.dependency_overrides[routes.get_status_manager] = lambda: mock_status_manager
    app.dependency_overrides[routes.get_job_processor] = lambda: mock_job_processor
    
    # Set global processors
    routes.set_processors(mock_job_processor, mock_status_manager)
    
    client = TestClient(app)
    yield client
    
    # Clear overrides
    app.dependency_overrides.clear()


class TestListAllChannels:
    """Test GET /api/v1/channels/ - List all channels."""
    
    def test_list_channels_success(self, client):
        """Should return all channels with status."""
        response = client.get("/api/v1/channels/")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check structure
        assert "channels" in data
        assert "total_channels" in data
        assert "available_channels" in data
        assert "booked_channels" in data
        
        # All channels should be available initially
        assert data["total_channels"] == 48  # 16+16+16
        assert data["available_channels"] == 48
        assert data["booked_channels"] == 0
        
        # Check channels structure
        channels = data["channels"]
        assert len(channels) == 48
        assert all("channel" in ch and "status" in ch for ch in channels)
    
    def test_list_channels_shows_booked_status(self, client):
        """Should show booked status for reserved channels."""
        # Book some channels first
        book_response = client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-001", "channel_numbers": [1, 2, 3]}
        )
        assert book_response.status_code == 201
        
        # List channels
        response = client.get("/api/v1/channels/")
        assert response.status_code == 200
        
        data = response.json()
        assert data["available_channels"] == 45  # 48 - 3
        assert data["booked_channels"] == 3
        
        # Check booked channels in list
        channels = data["channels"]
        booked_ch = [ch for ch in channels if ch["channel"] in [1, 2, 3]]
        assert all(ch["status"] == "booked" for ch in booked_ch)
        assert all(ch["booked_by"] == "measurement-001" for ch in booked_ch)
    
    def test_list_channels_response_format(self, client):
        """Should return properly formatted response."""
        response = client.get("/api/v1/channels/")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify structure
        assert isinstance(data["channels"], list)
        assert isinstance(data["total_channels"], int)
        assert isinstance(data["available_channels"], int)
        assert isinstance(data["booked_channels"], int)


class TestListAvailableChannels:
    """Test GET /api/v1/channels/available - List available channels."""
    
    def test_list_available_success(self, client):
        """Should return available channels and stats."""
        response = client.get("/api/v1/channels/available")
        
        assert response.status_code == 200
        data = response.json()
        
        # Check structure
        assert "available_channel_numbers" in data
        assert "total_channels" in data
        assert "available_channels" in data
        assert "booked_channels" in data
        assert "utilization_percent" in data
        assert "booked_by_identifier" in data
        
        # Initially all should be available
        assert data["available_channels"] == 48
        assert data["booked_channels"] == 0
        assert data["utilization_percent"] == 0
        assert len(data["available_channel_numbers"]) == 48
    
    def test_list_available_after_booking(self, client):
        """Should show correct availability after booking."""
        # Book channels
        book_response = client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-002", "channel_numbers": [1, 5, 10]}
        )
        assert book_response.status_code == 201
        
        # List available
        response = client.get("/api/v1/channels/available")
        assert response.status_code == 200
        
        data = response.json()
        assert data["available_channels"] == 45
        assert data["booked_channels"] == 3
        assert 1 not in data["available_channel_numbers"]
        assert 5 not in data["available_channel_numbers"]
        assert 10 not in data["available_channel_numbers"]
        
        # Check booked_by_identifier mapping
        assert "measurement-002" in data["booked_by_identifier"]
        assert set(data["booked_by_identifier"]["measurement-002"]) == {1, 5, 10}
    
    def test_list_available_utilization_percent(self, client):
        """Should calculate utilization percentage correctly."""
        # Book 8 out of 48 channels (16.67%)
        client.post(
            "/api/v1/channels/book",
            json={"booked_by": "test-001", "channel_numbers": [1, 2, 3, 4, 5, 6, 7, 8]}
        )
        
        response = client.get("/api/v1/channels/available")
        data = response.json()
        
        expected_utilization = (8 / 48) * 100
        assert abs(data["utilization_percent"] - expected_utilization) < 0.1


class TestBookChannels:
    """Test POST /api/v1/channels/book - Book channels."""
    
    def test_book_channels_success(self, client):
        """Should successfully book available channels."""
        response = client.post(
            "/api/v1/channels/book",
            json={
                "booked_by": "measurement-003",
                "channel_numbers": [1, 2, 3]
            }
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verify response
        assert data["booked_by"] == "measurement-003"
        assert set(data["booked_channels"]) == {1, 2, 3}
        assert data["total_booked"] == 3
        assert "booking_time" in data
    
    def test_book_channels_invalid_channel(self, client):
        """Should reject invalid channel numbers."""
        response = client.post(
            "/api/v1/channels/book",
            json={
                "booked_by": "measurement-004",
                "channel_numbers": [1, 999]
            }
        )
        
        assert response.status_code == 400
        assert "Invalid channel" in response.json()["detail"]
    
    def test_book_channels_already_booked(self, client):
        """Should reject booking already-booked channels."""
        # Book channels first
        client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-005", "channel_numbers": [1, 2]}
        )
        
        # Try to book same channels
        response = client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-006", "channel_numbers": [1, 3]}
        )
        
        assert response.status_code == 409
        assert "already booked" in response.json()["detail"].lower()
    
    def test_book_channels_multiple_calls(self, client):
        """Should allow multiple independent bookings."""
        # Book for measurement 1
        response1 = client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-007", "channel_numbers": [1, 2, 3]}
        )
        assert response1.status_code == 201
        
        # Book for measurement 2
        response2 = client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-008", "channel_numbers": [5, 6, 7]}
        )
        assert response2.status_code == 201
        
        # Verify both bookings exist
        list_response = client.get("/api/v1/channels/available")
        data = list_response.json()
        
        assert "measurement-007" in data["booked_by_identifier"]
        assert "measurement-008" in data["booked_by_identifier"]
    
    def test_book_channels_empty_list(self, client):
        """Should handle empty channel list."""
        response = client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-009", "channel_numbers": []}
        )
        
        # Should succeed but book nothing
        assert response.status_code == 201
        data = response.json()
        assert data["total_booked"] == 0


class TestReleaseChannels:
    """Test POST /api/v1/channels/release/{booked_by} - Release channels."""
    
    def test_release_channels_success(self, client):
        """Should successfully release booked channels."""
        # Book channels first
        client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-010", "channel_numbers": [1, 2, 3]}
        )
        
        # Release channels
        response = client.post("/api/v1/channels/release/measurement-010")
        
        assert response.status_code == 200
        data = response.json()
        
        # Verify response
        assert data["booked_by"] == "measurement-010"
        assert set(data["released_channels"]) == {1, 2, 3}
        assert data["total_released"] == 3
    
    def test_release_channels_not_booked(self, client):
        """Should handle release of non-booked identifier gracefully."""
        response = client.post("/api/v1/channels/release/measurement-nonexistent")
        
        assert response.status_code == 200
        data = response.json()
        
        # Should return empty release
        assert data["booked_by"] == "measurement-nonexistent"
        assert data["released_channels"] == []
        assert data["total_released"] == 0
    
    def test_release_channels_clears_availability(self, client):
        """Should restore channels to available after release."""
        measurement_id = "measurement-011"
        
        # Book channels
        client.post(
            "/api/v1/channels/book",
            json={"booked_by": measurement_id, "channel_numbers": [10, 11, 12]}
        )
        
        # Verify booked
        list1 = client.get("/api/v1/channels/available").json()
        assert list1["available_channels"] == 45
        
        # Release
        client.post(f"/api/v1/channels/release/{measurement_id}")
        
        # Verify available again
        list2 = client.get("/api/v1/channels/available").json()
        assert list2["available_channels"] == 48
        assert 10 in list2["available_channel_numbers"]
        assert 11 in list2["available_channel_numbers"]
        assert 12 in list2["available_channel_numbers"]
    
    def test_release_specific_identifier_only(self, client):
        """Should only release channels for the specified identifier."""
        # Book for measurement 1
        client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-012", "channel_numbers": [1, 2]}
        )
        
        # Book for measurement 2
        client.post(
            "/api/v1/channels/book",
            json={"booked_by": "measurement-013", "channel_numbers": [5, 6]}
        )
        
        # Release measurement 1
        client.post("/api/v1/channels/release/measurement-012")
        
        # Verify only measurement 1 channels are released
        list_response = client.get("/api/v1/channels/available").json()
        
        assert 1 in list_response["available_channel_numbers"]
        assert 2 in list_response["available_channel_numbers"]
        assert 5 not in list_response["available_channel_numbers"]
        assert 6 not in list_response["available_channel_numbers"]


class TestChannelIntegration:
    """Integration tests for channel management workflows."""
    
    def test_complete_booking_workflow(self, client):
        """Test complete flow: list -> book -> verify -> release -> verify."""
        measurement_id = "measurement-014"
        
        # 1. List initial state
        response1 = client.get("/api/v1/channels/")
        assert response1.json()["available_channels"] == 48
        
        # 2. Book channels
        response2 = client.post(
            "/api/v1/channels/book",
            json={"booked_by": measurement_id, "channel_numbers": [5, 10, 15]}
        )
        assert response2.status_code == 201
        assert response2.json()["total_booked"] == 3
        
        # 3. Verify booked
        response3 = client.get("/api/v1/channels/available")
        assert response3.json()["available_channels"] == 45
        assert response3.json()["booked_channels"] == 3
        
        # 4. Release channels
        response4 = client.post(f"/api/v1/channels/release/{measurement_id}")
        assert response4.json()["total_released"] == 3
        
        # 5. Verify released
        response5 = client.get("/api/v1/channels/")
        assert response5.json()["available_channels"] == 48
    
    def test_multiple_measurements_concurrent_booking(self, client):
        """Test multiple measurements booking different channels."""
        measurements = [
            ("meas-a", [1, 2, 3]),
            ("meas-b", [10, 11, 12]),
            ("meas-c", [101, 102, 103]),
        ]
        
        # Book all
        for meas_id, channels in measurements:
            response = client.post(
                "/api/v1/channels/book",
                json={"booked_by": meas_id, "channel_numbers": channels}
            )
            assert response.status_code == 201
        
        # Verify total booked
        stats = client.get("/api/v1/channels/available").json()
        assert stats["booked_channels"] == 9
        assert stats["available_channels"] == 39
        
        # Release one
        client.post("/api/v1/channels/release/meas-a")
        
        # Verify partial release
        stats2 = client.get("/api/v1/channels/available").json()
        assert stats2["booked_channels"] == 6
        assert stats2["available_channels"] == 42
    
    def test_channel_stats_accuracy(self, client):
        """Verify channel statistics are accurate."""
        # Book different amounts
        client.post(
            "/api/v1/channels/book",
            json={"booked_by": "m1", "channel_numbers": [1]}
        )
        client.post(
            "/api/v1/channels/book",
            json={"booked_by": "m2", "channel_numbers": [2, 3, 4]}
        )
        
        # Get stats
        response = client.get("/api/v1/channels/available")
        data = response.json()
        
        assert data["total_channels"] == 48
        assert data["booked_channels"] == 4
        assert data["available_channels"] == 44
        assert data["utilization_percent"] == pytest.approx((4/48)*100, rel=0.1)
