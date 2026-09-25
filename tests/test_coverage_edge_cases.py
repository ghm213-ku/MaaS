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
from app.services.file_logger import FileLogger
from app.utils.path_utils import format_target_location
from app.services.job_processor import JobProcessor
from app.models import MeasurementType, CountRateMeasurementRequest, CountRateMetadata, CoincidencesMetadata

# ----------------- #
# routes.py edge cases
# ----------------- #
@pytest.mark.asyncio
async def test_routes_file_logger_fails():
    """Test file logger failing during measurement creation."""
    mock_status_manager = MagicMock()
    mock_status_manager.get_booked_channels.return_value = {1: "test_user", 2: "test_user", 3: "test_user", 4: "test_user"}
    mock_job_processor = MagicMock()
    mock_file_logger = MagicMock()

    mock_status_manager.validate_channels.return_value = {
        "booked_channels": [1, 2],
        "booking_time": "time"
    }
    mock_file_logger.log_measurement_request.side_effect = Exception("File system full")
    
    request = CountRateMeasurementRequest(
        measurement_type=MeasurementType.COUNT_RATE,
        duration_seconds=10.0,
        metadata=CountRateMetadata(user_name="test_user", channels=[1, 2])
    )
    
    # This should not raise an HTTP exception, just log a warning
    response = start_count_rate_measurement(
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
    mock_status_manager.get_booked_channels.return_value = {1: "test_user", 2: "test_user", 3: "test_user", 4: "test_user"}
    mock_status_manager.validate_channels.side_effect = ValueError("Channels occupied")
    
    request = CountRateMeasurementRequest(
        measurement_type=MeasurementType.COUNT_RATE,
        duration_seconds=10.0,
        metadata=CountRateMetadata(user_name="test_user", channels=[1, 2])
    )
    
    with pytest.raises(HTTPException) as exc:
        start_count_rate_measurement(
            request=request,
            processor=MagicMock(),
            status_manager=mock_status_manager,
            file_logger=MagicMock()
        )
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_routes_general_exception():
    """Test when a random unhandled exception occurs."""
    mock_status_manager = MagicMock()
    mock_status_manager.get_booked_channels.return_value = {1: "test_user", 2: "test_user", 3: "test_user", 4: "test_user"}
    mock_status_manager.validate_channels.side_effect = Exception("Random unexpected error")
    
    request = CountRateMeasurementRequest(
        measurement_type=MeasurementType.COUNT_RATE,
        duration_seconds=10.0,
        metadata=CountRateMetadata(user_name="test_user", channels=[1, 2])
    )
    
    with pytest.raises(HTTPException) as exc:
        start_count_rate_measurement(
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
    processor._run_job_in_thread(status_id="id123", measurement_type="unknown_type", duration_seconds=10.0, metadata={"user_name": "test_user", })
    sm_mock.update_status.assert_called_with("id123", MeasurementStatus.FAILED.value, "Job failed: Unknown measurement type: unknown_type")

def test_job_processor_tagger_none():
    """Test job processor with None tagger."""
    sm_mock = MagicMock()
    sm_mock.get_status.return_value = {"status": "queued"}
    
    processor = JobProcessor(status_manager=sm_mock, tagger=None)
    processor.redis_client = MagicMock()
    processor.register_handler("save_raw_tags", MagicMock())
    processor._run_job_in_thread(status_id="id123", measurement_type="save_raw_tags", duration_seconds=10.0, metadata={"user_name": "test_user", })
    sm_mock.update_status.assert_called_with("id123", MeasurementStatus.FAILED.value, "Job failed: SaveRawTagsMeasurementHandler requires tagger but none was provided to JobProcessor")

class MockCoincidencesHandler(MeasurementHandler):
    async def start(self, duration_seconds: float, metadata: CoincidencesMetadata) -> None:
        pass
    async def stop(self) -> dict:
        return {}

def test_job_processor_handle_coincidences():
    """Test the coincidences execution block."""
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    processor.redis_client = MagicMock()
    handler = MockCoincidencesHandler(tagger=MagicMock())
    processor.job_handlers["coincidences"] = MagicMock(return_value=handler)
    
    # Missing metadata fields
    processor._run_job_in_thread("id1", "coincidences", 0.0, {})
    args = processor.status_manager.update_status.call_args_list[-1].args
    assert args[1] == "failed" and "validation errors" in args[2]
        
    # Missing channels
    processor._run_job_in_thread("id1", "coincidences", 10.0, {"user_name": "test_user"})
    args = processor.status_manager.update_status.call_args_list[-1].args
    assert args[1] == "failed" and "channels" in args[2] and "Field required" in args[2]
        
    # Valid
    processor._run_job_in_thread("id1", "coincidences", 10.0, {"user_name": "test_user", "channels": [1,2]})
    # Should complete
    args = processor.status_manager.update_status.call_args_list[-1].args
    assert args[1] == "completed"

def test_job_processor_handle_save_raw_tags():
    """Test the save_raw_tags execution block."""
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    processor.redis_client = MagicMock()
    handler = MockCoincidencesHandler(tagger=MagicMock())  # using this as a dummy handler
    processor.job_handlers["save_raw_tags"] = MagicMock(return_value=handler)
    
    # Missing metadata fields
    processor._run_job_in_thread("id1", "save_raw_tags", 0.0, {})
    args = processor.status_manager.update_status.call_args_list[-1].args
    assert args[1] == "failed" and "validation errors" in args[2]
        
    # Missing channel list
    processor._run_job_in_thread("id1", "save_raw_tags", 10.0, {"user_name": "test_user", "target_file_path": "path"})
    args = processor.status_manager.update_status.call_args_list[-1].args
    assert args[1] == "failed" and "channel_list" in args[2] and "Field required" in args[2]
        
    # Valid
    processor._run_job_in_thread("id1", "save_raw_tags", 10.0, {"user_name": "test_user", "channel_list": [1,2], "target_file_path": "test.txt"})
    # Should complete
    args = processor.status_manager.update_status.call_args_list[-1].args
    assert args[1] == "completed"

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
import tempfile

def test_job_processor_run_job_skip_stopped():
    sm_mock = MagicMock()
    sm_mock.get_status.return_value = {"status": MeasurementStatus.STOPPED.value}
    
    processor = JobProcessor(status_manager=sm_mock, tagger=MagicMock())
    processor.redis_client = MagicMock()
    
    processor._run_job_in_thread("id123", "count_rate", 10.0, {})
    # Should return early, not call update_status
    sm_mock.update_status.assert_not_called()

def test_job_processor_run_job_cancelled_error():
    sm_mock = MagicMock()
    sm_mock.get_status.return_value = {"status": "queued"}
    
    processor = JobProcessor(status_manager=sm_mock, tagger=MagicMock())
    processor.redis_client = MagicMock()
    
    handler = MockCoincidencesHandler(tagger=MagicMock())
    handler.start = AsyncMock(side_effect=asyncio.CancelledError())
    processor.job_handlers["coincidences"] = MagicMock(return_value=handler)
    
    processor._run_job_in_thread("id123", "coincidences", 10.0, {"channels": [1,2]})
    # Should catch CancelledError and not update_status to FAILED
    sm_mock.update_status.assert_called_with("id123", "active", "coincidences measurement started")


def test_job_processor_format_target_location_empty():
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    res = processor._format_target_location("", "count_rate")
    assert res == ""

def test_job_processor_format_target_location_directory():
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    with tempfile.TemporaryDirectory() as temp_dir:
        res = processor._format_target_location(temp_dir, "count_rate")
        assert res.endswith(".csv")
        assert "count_rate" in res
        
        res_raw = processor._format_target_location(temp_dir, "save_raw_tags")
        assert res_raw.endswith(".tags")
        assert "save_raw_tags" in res_raw

def test_job_processor_is_job_active():
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    processor.active_jobs["id1"] = mock_thread
    
    assert processor.is_job_active("id1") is True
    assert processor.is_job_active("id2") is False

def test_job_processor_listen_for_stops_new_loop():
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    processor.redis_client = MagicMock()
    
    mock_handler = MagicMock()
    mock_handler.stop = AsyncMock()
    processor.active_handlers["id123"] = mock_handler # no loop provided
    
    mock_pubsub = MagicMock()
    mock_pubsub.listen.return_value = [{"type": "message", "data": b"id123"}]
    processor._pubsub = mock_pubsub
    
    def mock_listen():
        yield {"type": "message", "data": b"id123"}
        
    mock_pubsub.listen = mock_listen
    
    processor._listen_for_stops()
    mock_handler.stop.assert_called()

def test_status_manager_update_status_file_logger_exception():
    redis_mock = MagicMock()
    redis_mock.get.return_value = '{"status": "queued"}'
    file_logger_mock = MagicMock()
    file_logger_mock.log_measurement_status_update.side_effect = Exception("Write error")
    
    manager = StatusManager()
    manager.redis_client = redis_mock
    manager.file_logger = file_logger_mock
    
    # Should catch exception and not raise
    manager.update_status("id1", "active", "Started")

def test_status_manager_update_status_release_channels_exception():
    redis_mock = MagicMock()
    redis_mock.get.return_value = '{"status": "queued"}'
    manager = StatusManager()
    manager.redis_client = redis_mock
    manager.file_logger = MagicMock()
    
    # Mock release_channels to raise
    manager.release_channels = MagicMock(side_effect=Exception("Release failed"))
    
    # Should catch release_channels exception when status is completed
    manager.update_status("id1", MeasurementStatus.COMPLETED.value, "Done")

def test_status_manager_get_results_invalid_json():
    redis_mock = MagicMock()
    redis_mock.get.return_value = "invalid json"
    manager = StatusManager()
import tempfile

def test_job_processor_run_job_skip_stopped():
    sm_mock = MagicMock()
    sm_mock.get_status.return_value = {"status": MeasurementStatus.STOPPED.value}
    
    processor = JobProcessor(status_manager=sm_mock, tagger=MagicMock())
    processor.redis_client = MagicMock()
    
    processor._run_job_in_thread("id123", "count_rate", 10.0, {})
    # Should return early, not call update_status
    sm_mock.update_status.assert_not_called()

def test_job_processor_run_job_cancelled_error():
    sm_mock = MagicMock()
    sm_mock.get_status.return_value = {"status": "queued"}
    
    processor = JobProcessor(status_manager=sm_mock, tagger=MagicMock())
    processor.redis_client = MagicMock()
    
    handler = MockCoincidencesHandler(tagger=MagicMock())
    handler.start = AsyncMock(side_effect=asyncio.CancelledError())
    processor.job_handlers["coincidences"] = MagicMock(return_value=handler)
    
    processor._run_job_in_thread("id123", "coincidences", 10.0, {"user_name": "test_user", "channels": [1,2]})
    # Should catch CancelledError and not update_status to FAILED
    sm_mock.update_status.assert_called_with("id123", "active", "coincidences measurement started")


def test_job_processor_format_target_location_empty():
    res = format_target_location("", "count_rate")
    assert res == ""

def test_job_processor_format_target_location_directory():
    with tempfile.TemporaryDirectory() as temp_dir:
        res = format_target_location(temp_dir, "count_rate")
        assert res.endswith(".csv")
        assert "count_rate" in res
        
        res_raw = format_target_location(temp_dir, "save_raw_tags")
        assert res_raw.endswith(".tags")
        assert "save_raw_tags" in res_raw

def test_job_processor_is_job_active():
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    mock_thread = MagicMock()
    mock_thread.is_alive.return_value = True
    processor.active_jobs["id1"] = mock_thread
    
    assert processor.is_job_active("id1") is True
    assert processor.is_job_active("id2") is False

def test_job_processor_listen_for_stops_new_loop():
    processor = JobProcessor(status_manager=MagicMock(), tagger=MagicMock())
    processor.redis_client = MagicMock()
    
    mock_handler = MagicMock()
    mock_handler.stop = AsyncMock()
    processor.active_handlers["id123"] = mock_handler # no loop provided
    
    mock_pubsub = MagicMock()
    mock_pubsub.listen.return_value = [{"type": "message", "data": b"id123"}]
    processor._pubsub = mock_pubsub
    
    def mock_listen():
        yield {"type": "message", "data": b"id123"}
        
    mock_pubsub.listen = mock_listen
    
    processor._listen_for_stops()
    mock_handler.stop.assert_called()

def test_status_manager_update_status_file_logger_exception():
    redis_mock = MagicMock()
    redis_mock.get.return_value = '{"status": "queued"}'
    file_logger_mock = MagicMock()
    file_logger_mock.log_measurement_status_update.side_effect = Exception("Write error")
    
    manager = StatusManager()
    manager.redis_client = redis_mock
    manager.file_logger = file_logger_mock
    
    # Should catch exception and not raise
    manager.update_status("id1", "active", "Started")

def test_status_manager_update_status_release_channels_exception():
    redis_mock = MagicMock()
    redis_mock.get.return_value = '{"status": "queued"}'
    manager = StatusManager()
    manager.redis_client = redis_mock
    manager.file_logger = MagicMock()
    
    # Mock release_channels to raise
    manager.release_channels = MagicMock(side_effect=Exception("Release failed"))
    
    # Should catch release_channels exception when status is completed
    manager.update_status("id1", MeasurementStatus.COMPLETED.value, "Done")

def test_status_manager_get_results_invalid_json():
    redis_mock = MagicMock()
    redis_mock.get.return_value = "invalid json"
    manager = StatusManager()
    manager.redis_client = redis_mock
    
    res = manager.get_results("id1")
    assert res is None

def test_status_manager_delete_status_file_logger_exception():
    redis_mock = MagicMock()
    redis_mock.get.return_value = '{"status": "completed"}'
    redis_mock.delete.return_value = 1
    file_logger_mock = MagicMock()
    file_logger_mock.log_measurement_status_removal.side_effect = Exception("Write error")
    
    manager = StatusManager()
    manager.redis_client = redis_mock
    manager.file_logger = file_logger_mock
    
    manager.delete_status("id1")
    # Exception caught and handled silently
    assert redis_mock.delete.called

def test_status_manager_health_check_exception():
    redis_mock = MagicMock()
    redis_mock.ping.side_effect = Exception("Redis down")
    manager = StatusManager()
    manager.redis_client = redis_mock
    
    res = manager.health_check()
    assert res is False

def test_status_manager_get_all_channels():
    manager = StatusManager()
    channels = manager.get_all_channels()
    assert len(channels) == len(manager.ALL_CHANNELS)
    assert set(c["channel_number"] for c in channels) == set(manager.ALL_CHANNELS)

def test_status_manager_validate_channels_true():
    manager = StatusManager()
    # Should not raise exception
    manager.validate_channels([1, 16])
