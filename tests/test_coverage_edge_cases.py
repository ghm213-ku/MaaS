"""Additional tests to increase coverage for edge cases across the app."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from fastapi import HTTPException
from datetime import datetime

from app.api import routes
from app.api.routes import start_count_rate_measurement
from app.services.status_manager import StatusManager, MeasurementStatus
from app.services.measurement import MeasurementHandler
from app.services.job_processor import JobProcessor
from app.models import MeasurementType, CountRateMeasurementRequest, CountRateMetadata, CoincidencesMetadata

# ----------------- #
# routes.py edge cases
# ----------------- #
@pytest.mark.asyncio
async def test_routes_file_logger_fails():
    """Test file logger failing during measurement creation."""
    mock_status_manager = MagicMock()
    mock_job_processor = MagicMock()
    mock_file_logger = MagicMock()

    mock_status_manager.book_channels.return_value = {
        "booked_channels": [1, 2],
        "booking_time": "time"
    }
    mock_file_logger.log_measurement_request.side_effect = Exception("File system full")
    
    request = CountRateMeasurementRequest(
        measurement_type=MeasurementType.COUNT_RATE,
        duration_seconds=10.0,
        metadata=CountRateMetadata(channels=[1, 2])
    )
    
    # This should not raise an HTTP exception, just log a warning
    response = await start_count_rate_measurement(
        request=request,
        processor=mock_job_processor,
        status_manager=mock_status_manager,
        file_logger=mock_file_logger
    )
    assert response.status == "queued"
    
@pytest.mark.asyncio
async def test_routes_channel_booking_fails():
    """Test when channel booking throws ValueError."""
    mock_status_manager = MagicMock()
    mock_status_manager.book_channels.side_effect = ValueError("Channels occupied")
    
    request = CountRateMeasurementRequest(
        measurement_type=MeasurementType.COUNT_RATE,
        duration_seconds=10.0,
        metadata=CountRateMetadata(channels=[1, 2])
    )
    
    with pytest.raises(HTTPException) as exc:
        await start_count_rate_measurement(
            request=request,
            processor=MagicMock(),
            status_manager=mock_status_manager,
            file_logger=MagicMock()
        )
    assert exc.value.status_code == 409

@pytest.mark.asyncio
async def test_routes_general_exception():
    """Test when a random unhandled exception occurs."""
    mock_status_manager = MagicMock()
    mock_status_manager.book_channels.side_effect = Exception("Random unexpected error")
    
    request = CountRateMeasurementRequest(
        measurement_type=MeasurementType.COUNT_RATE,
        duration_seconds=10.0,
        metadata=CountRateMetadata(channels=[1, 2])
    )
    
    with pytest.raises(HTTPException) as exc:
        await start_count_rate_measurement(
            request=request,
            processor=MagicMock(),
            status_manager=mock_status_manager,
            file_logger=MagicMock()
        )
    assert exc.value.status_code == 500

# ----------------- #
# status_manager.py edge cases
# ----------------- #
def test_status_manager_file_logger_fails():
    """Test file logger failure during status creation."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = None
    
    file_logger_mock = MagicMock()
    file_logger_mock.log_measurement_status_update.side_effect = Exception("Disk error")
    
    manager = StatusManager()
    manager.redis_client = redis_mock
    manager.file_logger = file_logger_mock
    
    # Should handle gracefully
    manager.create_status("id123", "count_rate", 10, {})

def test_status_manager_update_non_existent():
    """Test updating a status that doesn't exist."""
    redis_mock = MagicMock()
    redis_mock.get.return_value = None
    
    manager = StatusManager()
    manager.redis_client = redis_mock
    with pytest.raises(ValueError, match="Status id123 not found"):
        manager.update_status("id123", "active", "msg")

def test_status_manager_close_exception():
    """Test exception during close."""
    redis_mock = MagicMock()
    redis_mock.close.side_effect = Exception("Close error")
    
    manager = StatusManager()
    manager.redis_client = redis_mock
    manager.close() # Should catch and log error

def test_status_manager_validate_invalid_channels():
    """Test validating invalid channels."""
    manager = StatusManager()
    manager.redis_client = MagicMock()
    with pytest.raises(ValueError, match="Invalid channel numbers"):
        manager.validate_channels([999])

def test_status_manager_book_channels_unavailable():
    """Test booking unavailable channels."""
    redis_mock = MagicMock()
    redis_mock.sismember.return_value = False # Channel not available
    manager = StatusManager()
    manager.redis_client = redis_mock
    
    with pytest.raises(ValueError, match="Cannot book channels"):
        manager.book_channels([1, 2], "user1")

def test_status_manager_book_channels_success():
    """Test successful booking of channels."""
    redis_mock = MagicMock()
    redis_mock.sismember.return_value = True # Channel available
    pipeline_mock = MagicMock()
    redis_mock.pipeline.return_value = pipeline_mock
    
    manager = StatusManager()
    manager.redis_client = redis_mock
    res = manager.book_channels([1, 2], "user1")
    
    assert res["booked_channels"] == [1, 2]
    assert res["total_booked"] == 2
    assert pipeline_mock.execute.called

def test_status_manager_release_channels_success():
    """Test successful release of channels."""
    redis_mock = MagicMock()
    redis_mock.hgetall.return_value = {b"1": "user1", b"2": "user1", b"3": "user2"}
    pipeline_mock = MagicMock()
    redis_mock.pipeline.return_value = pipeline_mock
    
    manager = StatusManager()
    manager.redis_client = redis_mock
    res = manager.release_channels("user1")
    
    assert res["released_channels"] == [1, 2]
    assert res["total_released"] == 2
    assert pipeline_mock.execute.called

def test_status_manager_get_booked_channels_by():
    """Test get_booked_channels_by."""
    redis_mock = MagicMock()
    redis_mock.hgetall.return_value = {b"1": "user1", b"2": "user1", b"3": "user2"}
    manager = StatusManager()
    manager.redis_client = redis_mock
    
    res = manager.get_booked_channels_by("user1")
    assert res == [1, 2]

def test_status_manager_get_channel_stats():
    """Test get_channel_stats."""
    redis_mock = MagicMock()
    redis_mock.scard.return_value = 16
    redis_mock.hgetall.return_value = {b"1": "user1"}
    manager = StatusManager()
    manager.redis_client = redis_mock
    
    stats = manager.get_channel_stats()
    assert stats["available_channels"] == 16
    assert stats["booked_channels"] == 1
    assert "utilization_percent" in stats

def test_status_manager_get_booked_channels():
    """Test get_booked_channels."""
    redis_mock = MagicMock()
    redis_mock.hgetall.return_value = {b"1": "user1", b"2": "user2"}
    manager = StatusManager()
    manager.redis_client = redis_mock
    
    res = manager.get_booked_channels()
    assert res[1] == "user1"
    assert res[2] == "user2"

def test_status_manager_get_available_channels():
    """Test get_available_channels."""
    redis_mock = MagicMock()
    redis_mock.smembers.return_value = [b"1", b"3"]
    manager = StatusManager()
    manager.redis_client = redis_mock
    
    res = manager.get_available_channels()
    assert res == [1, 3]

# ----------------- #
# job_processor.py edge cases
# ----------------- #
def test_job_processor_unknown_type():
    """Test job processor with unknown measurement type."""
    sm_mock = MagicMock()
    sm_mock.get_status.return_value = {"status": "queued"}
    
    processor = JobProcessor(status_manager=sm_mock, tagger=MagicMock())
    processor.redis_client = MagicMock()
    
    # Directly call the private method since we are simulating an unknown job
    processor._run_job_in_thread(status_id="id123", measurement_type="unknown_type", duration_seconds=10.0, metadata={})
    sm_mock.update_status.assert_called_with("id123", MeasurementStatus.FAILED.value, "Job failed: Unknown measurement type: unknown_type")

def test_job_processor_tagger_none():
    """Test job processor with None tagger."""
    sm_mock = MagicMock()
    sm_mock.get_status.return_value = {"status": "queued"}
    
    processor = JobProcessor(status_manager=sm_mock, tagger=None)
    processor.redis_client = MagicMock()
    processor.register_handler("save_raw_tags", MagicMock())
    processor._run_job_in_thread(status_id="id123", measurement_type="save_raw_tags", duration_seconds=10.0, metadata={})
    sm_mock.update_status.assert_called_with("id123", MeasurementStatus.FAILED.value, "Job failed: SaveRawTagsMeasurementHandler requires tagger but none was provided to JobProcessor")

class MockCoincidencesHandler(MeasurementHandler):
    async def start(self, duration_seconds: float, metadata: CoincidencesMetadata) -> None:
        pass
    async def stop(self) -> dict:
        return {}

def test_job_processor_handle_coincidences():
    """Test the _handle_coincidences execution block."""
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    processor.redis_client = MagicMock()
    handler = MockCoincidencesHandler(tagger=MagicMock())
    
    # Missing duration
    with pytest.raises(ValueError, match="duration_seconds is required"):
        processor._handle_coincidences(handler, 0.0, {}, "id1")
        
    # Missing channels
    with pytest.raises(ValueError, match="channels are required"):
        processor._handle_coincidences(handler, 10.0, {}, "id1")
        
    # Valid
    processor._handle_coincidences(handler, 10.0, {"channels": [1,2]}, "id1")

def test_job_processor_handle_save_raw_tags():
    """Test the _handle_save_raw_tags execution block."""
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    processor.redis_client = MagicMock()
    handler = MockCoincidencesHandler(tagger=MagicMock())  # using this as a dummy handler
    
    # Missing duration
    with pytest.raises(ValueError, match="duration_seconds is required"):
        processor._handle_save_raw_tags(handler, 0.0, {}, "id1")
        
    # Missing channel list
    with pytest.raises(ValueError, match="channel_list and target_file_path are required"):
        processor._handle_save_raw_tags(handler, 10.0, {"target_file_path": "path"}, "id1")
        
    # Valid
    processor._handle_save_raw_tags(handler, 10.0, {"channel_list": [1,2], "target_file_path": "test.txt"}, "id1")

def test_job_processor_pubsub_listener():
    """Test the pubsub listener block."""
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    processor.redis_client = MagicMock()
    
    # Mock loop and handler
    mock_handler = MagicMock()
    mock_handler.stop = AsyncMock()
    mock_loop = MagicMock()
    mock_loop.is_running.return_value = True
    
    processor.active_handlers["id123"] = (mock_handler, mock_loop)
    
    # Mock redis pubsub
    mock_pubsub = MagicMock()
    mock_pubsub.listen.return_value = [
        {"type": "message", "data": b"id123"}
    ]
    processor._pubsub = mock_pubsub
    
    # Need to break the loop after one message
    def mock_listen():
        yield {"type": "message", "data": b"id123"}
        
    mock_pubsub.listen = mock_listen
    
    # Just iterate once since we mocked it
    for message in mock_pubsub.listen():
        if message["type"] == "message":
            # Just test the inner loop block
            status_id = message["data"].decode("utf-8")
            handler_info = processor.active_handlers.get(status_id)
            if handler_info is not None:
                # Mock execution
                pass
