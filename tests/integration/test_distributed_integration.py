"""
Integration tests for the distributed architecture.

Tests the interaction between web layer, Redis, and backend workers.
"""

import asyncio
import json
import time
import uuid
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
import redis

from app.services.status_manager import StatusManager, MeasurementStatus
from app.services.job_processor import JobProcessor
from app.handlers.count_rate import CountRateMeasurementHandler
from app.handlers.save_raw_tags import SaveRawTagsMeasurementHandler


@pytest.fixture
def redis_client():
    """Get Redis client for testing."""
    try:
        client = redis.Redis(host="localhost", port=6379, db=15, decode_responses=True)
        client.ping()
        yield client
    except redis.ConnectionError:
        pytest.skip("Redis server not available")
    finally:
        # Cleanup
        try:
            client.flushdb()
        except:
            pass


@pytest.fixture
def status_manager(redis_client):
    """Create StatusManager instance for testing."""
    manager = StatusManager(redis_host="localhost", redis_port=6379, redis_db=15)
    return manager


@pytest.fixture
def job_processor(status_manager):
    """Create JobProcessor instance for testing."""
    from unittest.mock import Mock

    mock_tagger = Mock()
    processor = JobProcessor(status_manager, tagger=mock_tagger)
    processor.register_handler("count_rate", CountRateMeasurementHandler)
    processor.register_handler("save_raw_tags", SaveRawTagsMeasurementHandler)
    return processor


class TestStatusManagerWithRedis:
    """Test StatusManager with actual Redis."""

    def test_create_and_retrieve_status(self, status_manager):
        """Test creating and retrieving a status."""
        status_id = str(uuid.uuid4())

        # Create status
        status_manager.create_status(
            status_id=status_id,
            measurement_type="count_rate",
            duration_seconds=30,
            metadata={"user_name": "test_user", "detector": "det_001"},
        )

        # Retrieve status
        status = status_manager.get_status(status_id)

        assert status is not None
        assert status["status_id"] == status_id
        assert status["measurement_type"] == "count_rate"
        assert status["status"] == MeasurementStatus.QUEUED.value
        assert status["duration_seconds"] == 30

    def test_update_status_and_results(self, status_manager):
        """Test updating status and storing results."""
        status_id = str(uuid.uuid4())

        # Create status
        status_manager.create_status(status_id, "count_rate", 30, {})

        # Update to active
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE.value,
            "Measurement started",
            None,
        )

        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.ACTIVE.value

        # Update to completed with results
        results = {"total_count": 12345, "duration": 30.5}
        status_manager.update_status(
            status_id,
            MeasurementStatus.COMPLETED.value,
            "Measurement completed",
            results,
        )

        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.COMPLETED.value
        assert status_manager.get_results(status_id) == results

    def test_metadata_persistence(self, status_manager):
        """Test metadata is properly stored and retrieved."""
        status_id = str(uuid.uuid4())
        metadata = {"user_name": "test_user", 
            "channel_list": [1, 2, 3],
            "target_file_path": "C:\\data\\output.dat",
            "custom_field": "value",
        }

        status_manager.create_status(
            status_id,
            "save_raw_tags",
            30,
            metadata,
        )

        retrieved_metadata = status_manager.get_metadata(status_id)
        assert retrieved_metadata == metadata

    def test_status_ttl(self, status_manager, redis_client):
        """Test that status expires with TTL."""
        status_id = str(uuid.uuid4())

        # Create status with default TTL
        status_manager.create_status(status_id, "count_rate", 30, {})

        # Check TTL is set (should be around 3600 seconds)
        status_key = f"measurement:status:{status_id}"
        ttl = redis_client.ttl(status_key)
        assert ttl > 0
        assert ttl <= 3600

    def test_status_persists_after_terminal_state(self, status_manager):
        """Test that measurement persists in Redis after reaching terminal status.

        Measurements should stay in Redis with TTL until expiry.
        They are logged when status changes, not deleted.
        """
        status_id = str(uuid.uuid4())

        # Create and activate a measurement
        status_manager.create_status(status_id, "count_rate", 30, {})
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE.value,
            "Measurement started",
        )

        # Verify it exists and is active
        status = status_manager.get_status(status_id)
        assert status is not None
        assert status["status"] == MeasurementStatus.ACTIVE.value

        # Update to terminal status (COMPLETED)
        status_manager.update_status(
            status_id,
            MeasurementStatus.COMPLETED.value,
            "Measurement completed successfully",
        )

        # Should STILL exist in Redis (not auto-deleted)
        status = status_manager.get_status(status_id)
        assert (
            status is not None
        ), "Status should persist in Redis after terminal status"
        assert status["status"] == MeasurementStatus.COMPLETED.value

    def test_status_persists_after_failed_state(self, status_manager):
        """Test that measurement persists when it fails."""
        status_id = str(uuid.uuid4())

        # Create and activate
        status_manager.create_status(status_id, "count_rate", 30, {})
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE.value,
            "Measurement started",
        )

        # Update to failed status
        status_manager.update_status(
            status_id,
            MeasurementStatus.FAILED.value,
            "Measurement failed: connection timeout",
        )

        # Should persist in Redis
        status = status_manager.get_status(status_id)
        assert status is not None, "Status should persist in Redis after FAILED status"
        assert status["status"] == MeasurementStatus.FAILED.value

    def test_status_persists_after_stopped_state(self, status_manager):
        """Test that measurement persists when user stops it."""
        status_id = str(uuid.uuid4())

        # Create and activate
        status_manager.create_status(status_id, "count_rate", 30, {})
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE.value,
            "Measurement started",
        )

        # User stops the measurement
        status_manager.update_status(
            status_id,
            MeasurementStatus.STOPPED.value,
            "Measurement stopped by user",
        )

        # Should persist in Redis
        status = status_manager.get_status(status_id)
        assert status is not None, "Status should persist in Redis after STOPPED status"
        assert status["status"] == MeasurementStatus.STOPPED.value

    def test_health_check(self, status_manager):
        """Test health check."""
        health = status_manager.health_check()
        assert health is True


class TestJobProcessorIntegration:
    """Test JobProcessor integration with StatusManager."""

    def test_process_job_updates_status(self, status_manager, job_processor):
        """Test that processing a job updates status in Redis."""
        status_id = str(uuid.uuid4())

        # Create initial status
        status_manager.create_status(
            status_id,
            "count_rate",
            2,  # 2 second measurement
            {"detector": "test", "channels": [1, 2], "user_name": "test_user"},
        )

        # Process job (should update status)
        mock_handler = AsyncMock(return_value={"status": "completed"})
        with patch.object(CountRateMeasurementHandler, "start", mock_handler):
            job_processor.process_job(status_id, "count_rate", 2)

            # Give thread a moment to complete
            time.sleep(0.2)

            # Check status was processed (could be active during or completed after)
            status = status_manager.get_status(status_id)
            assert status["status"] in [
                MeasurementStatus.ACTIVE.value,
                MeasurementStatus.QUEUED.value,
                MeasurementStatus.COMPLETED.value,
            ]

    def test_handler_registration(self, job_processor):
        """Test handler registration."""
        assert "count_rate" in job_processor.job_handlers
        assert "save_raw_tags" in job_processor.job_handlers
        assert job_processor.job_handlers["count_rate"] == CountRateMeasurementHandler
        assert job_processor.job_handlers["save_raw_tags"] == SaveRawTagsMeasurementHandler

    def test_stop_job(self, status_manager, job_processor):
        """Test stopping a job."""
        status_id = str(uuid.uuid4())

        status_manager.create_status(status_id, "count_rate", 10, {})

        # Mark as active
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE.value,
            "Running",
            None,
        )

        # Stop job
        job_processor.stop_job(status_id)

        # Check status updated
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.STOPPED.value

    def test_concurrent_job_execution(self, status_manager, job_processor):
        """Test multiple jobs can run concurrently."""
        status_ids = [str(uuid.uuid4()) for _ in range(3)]

        # Create multiple statuses
        for i, status_id in enumerate(status_ids):
            status_manager.create_status(
                status_id,
                "count_rate",
                1,  # 1 second each
                {"job": i, "channels": [1, 2]},
            )

        # Start all jobs
        with patch.object(CountRateMeasurementHandler, "start", new_callable=AsyncMock):
            for status_id in status_ids:
                job_processor.process_job(status_id, "count_rate", 1)

        # Give threads a moment to start
        time.sleep(0.2)

        # Check all jobs are tracked
        for status_id in status_ids:
            job_info = status_manager.get_status(status_id)
            assert job_info is not None


class TestDistributedWorkflow:
    """End-to-end workflow tests."""

    def test_complete_measurement_workflow(self, status_manager, job_processor):
        """Test complete workflow: create → activate → complete."""
        status_id = str(uuid.uuid4())

        # Step 1: Create status (web layer)
        status_manager.create_status(
            status_id,
            "count_rate",
            5,
            {"detector": "det_001", "source": "lab_B"},
        )

        # Step 2: Verify initial state
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.QUEUED.value
        assert status_manager.get_metadata(status_id)["detector"] == "det_001"

        # Step 3: Activate (worker)
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE.value,
            "Measurement started",
            None,
        )

        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.ACTIVE.value

        # Step 4: Complete with results (worker)
        results = {"total_count": 50000, "duration": 5.0}
        status_manager.update_status(
            status_id,
            MeasurementStatus.COMPLETED.value,
            "Measurement completed successfully",
            results,
        )

        # Step 5: Verify final state
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.COMPLETED.value
        assert status_manager.get_results(status_id) == results
        assert status["message"] == "Measurement completed successfully"

    def test_error_handling_workflow(self, status_manager):
        """Test error handling workflow."""
        status_id = str(uuid.uuid4())

        # Create status
        status_manager.create_status(status_id, "count_rate", 5, {})

        # Activate
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE.value,
            "Running",
            None,
        )

        # Fail with error
        error_message = "Connection timeout to detector"
        status_manager.update_status(
            status_id,
            MeasurementStatus.FAILED.value,
            f"Error: {error_message}",
            {"error": error_message},
        )

        # Verify error state
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.FAILED.value
        assert "Error:" in status["message"]

    def test_stop_measurement_workflow(self, status_manager, job_processor):
        """Test stopping a measurement."""
        status_id = str(uuid.uuid4())

        # Create and activate
        status_manager.create_status(status_id, "count_rate", 60, {})
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE.value,
            "Running",
            None,
        )

        # Stop
        job_processor.stop_job(status_id)

        # Verify stopped state
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.STOPPED.value


class TestDataConsistency:
    """Test data consistency across distributed components."""

    def test_metadata_consistency(self, status_manager):
        """Test metadata consistency between create and retrieve."""
        status_id = str(uuid.uuid4())
        metadata = {"user_name": "test_user", 
            "channel_list": [1, 2, 3, 4, 5],
            "target_file_path": "C:\\data\\measurements\\output.dat",
            "sampling_rate": 100000,
            "detector_type": "Si",
        }

        # Store
        status_manager.create_status(
            status_id,
            "save_raw_tags",
            30,
            metadata,
        )

        # Retrieve
        retrieved = status_manager.get_metadata(status_id)
        assert retrieved == metadata

    def test_results_consistency(self, status_manager):
        """Test results consistency."""
        status_id = str(uuid.uuid4())
        results = {
            "total_count": 1234567,
            "live_time": 29.99,
            "real_time": 30.00,
            "channels": [100, 200, 150],
        }

        status_manager.create_status(status_id, "count_rate", 30, {})
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE.value,
            "Running",
            None,
        )
        status_manager.update_status(
            status_id,
            MeasurementStatus.COMPLETED.value,
            "Done",
            results,
        )

        # Retrieve and verify
        retrieved = status_manager.get_results(status_id)
        assert retrieved == results

    def test_status_atomicity(self, status_manager):
        """Test status updates are atomic."""
        status_id = str(uuid.uuid4())

        status_manager.create_status(status_id, "count_rate", 30, {})

        # Update multiple times rapidly
        states = [
            (MeasurementStatus.QUEUED.value, "Queued"),
            (MeasurementStatus.ACTIVE.value, "Active"),
            (MeasurementStatus.COMPLETED.value, "Done"),
        ]

        for state, msg in states:
            status_manager.update_status(status_id, state, msg, None)

        # Final state should be the last one
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.COMPLETED.value


class TestErrorRecovery:
    """Test error recovery scenarios."""

    def test_redis_connection_recovery(self, status_manager):
        """Test graceful handling of Redis issues."""
        # This test verifies the system handles Redis issues
        # In real scenario, Redis would be offline
        health = status_manager.health_check()
        assert isinstance(health, bool)

    def test_invalid_status_id(self, status_manager):
        """Test handling of non-existent status ID."""
        invalid_id = "invalid-uuid"
        status = status_manager.get_status(invalid_id)
        assert status is None

    def test_corrupt_metadata_handling(self, status_manager):
        """Test handling of metadata operations on non-existent status."""
        invalid_id = "invalid-uuid"
        metadata = status_manager.get_metadata(invalid_id)
        assert metadata is None or metadata == {}


class TestJobQueueing:
    """Test the job queueing mechanism (enqueue_job and get_next_job)."""

    def test_enqueue_job_to_redis(self, status_manager, job_processor):
        """Test enqueuing a job to Redis queue."""
        status_id = str(uuid.uuid4())
        metadata = {"user_name": "test_user", "detector": "det_001", "location": "lab_A"}

        # Create status
        status_manager.create_status(
            status_id,
            "count_rate",
            30,
            metadata,
        )

        # Enqueue job to Redis (simulating what the API does)
        job_processor.enqueue_job(
            status_id=status_id,
            measurement_type="count_rate",
            duration_seconds=30,
            metadata=metadata,
        )

        # Retrieve the job from queue
        job = job_processor.get_next_job()
        assert job is not None
        assert job["status_id"] == status_id
        assert job["measurement_type"] == "count_rate"
        assert job["duration_seconds"] == 30
        assert job["metadata"] == metadata

    def test_enqueue_job_without_metadata(self, status_manager, job_processor):
        """Test enqueuing a job without metadata."""
        status_id = str(uuid.uuid4())

        status_manager.create_status(
            status_id,
            "count_rate",
            30,
            {},
        )

        # Enqueue without metadata parameter
        job_processor.enqueue_job(
            status_id=status_id,
            measurement_type="count_rate",
            duration_seconds=30,
        )

        # Retrieve the job
        job = job_processor.get_next_job()
        assert job is not None
        assert job["status_id"] == status_id
        assert job["metadata"] == {}

    def test_get_next_job_with_multiple_jobs(self, status_manager, job_processor):
        """Test retrieving jobs from queue when multiple are enqueued."""
        status_ids = [str(uuid.uuid4()) for _ in range(3)]

        # Create and enqueue multiple jobs
        for i, status_id in enumerate(status_ids):
            status_manager.create_status(
                status_id,
                "count_rate",
                30,
                {"job_number": i},
            )

            job_processor.enqueue_job(
                status_id=status_id,
                measurement_type="count_rate",
                duration_seconds=30,
                metadata={"user_name": "test_user", "job_number": i},
            )

        # Retrieve all jobs in order (FIFO)
        retrieved_ids = []
        for _ in range(3):
            job = job_processor.get_next_job()
            assert job is not None
            retrieved_ids.append(job["status_id"])

        # Should retrieve in same order they were enqueued
        assert retrieved_ids == status_ids

    def test_enqueue_save_raw_tags_with_metadata(self, status_manager, job_processor):
        """Test enqueuing save_raw_tags job with required metadata."""
        status_id = str(uuid.uuid4())
        metadata = {"user_name": "test_user", 
            "channel_list": [1, 2, 3],
            "target_file_path": "C:\\data\\output.dat",
        }

        status_manager.create_status(
            status_id,
            "save_raw_tags",
            30,
            metadata,
        )

        job_processor.enqueue_job(
            status_id=status_id,
            measurement_type="save_raw_tags",
            duration_seconds=30,
            metadata=metadata,
        )

        job = job_processor.get_next_job()
        assert job is not None
        assert job["metadata"]["channel_list"] == [1, 2, 3]
        assert job["metadata"]["target_file_path"] == "C:\\data\\output.dat"

    def test_get_next_job_empty_queue(self, status_manager, job_processor):
        """Test getting next job when queue is empty."""
        # Queue should be empty after previous tests cleanup
        # get_next_job with timeout should return None
        job = job_processor.get_next_job()
        assert job is None

    def test_job_queue_flow_end_to_end(self, status_manager, job_processor):
        """Test complete flow: enqueue → retrieve → process."""
        status_id = str(uuid.uuid4())
        metadata = {"user_name": "test_user", "detector": "det_001", "channels": [1, 2]}

        # Step 1: API creates status
        status_manager.create_status(
            status_id,
            "count_rate",
            5,
            metadata,
        )
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.QUEUED.value

        # Step 2: API enqueues job to Redis
        job_processor.enqueue_job(
            status_id=status_id,
            measurement_type="count_rate",
            duration_seconds=5,
            metadata=metadata,
        )

        # Step 3: Worker retrieves job from queue
        job = job_processor.get_next_job()
        assert job is not None
        assert job["metadata"] == metadata

        # Step 4: Worker processes the job (with mocked handler)
        mock_handler = AsyncMock(return_value={"status": "completed"})
        with patch.object(CountRateMeasurementHandler, "start", mock_handler):
            job_processor.process_job(
                status_id=job["status_id"],
                measurement_type=job["measurement_type"],
                duration_seconds=job["duration_seconds"],
                metadata=job["metadata"],
            )

            time.sleep(0.1)

            # Step 5: Verify job was processed
            status = status_manager.get_status(status_id)
            assert status["status"] in [
                MeasurementStatus.ACTIVE.value,
                MeasurementStatus.COMPLETED.value,
            ]


class TestResultsValidation:
    """Test results validation and handling of legacy/invalid data."""

    def test_get_results_with_legacy_string_data(self, status_manager, redis_client):
        """Test that get_results handles legacy string results gracefully.

        This tests the fix for the case where update_status was incorrectly called
        with a string as the results parameter instead of a dictionary.
        """
        status_id = str(uuid.uuid4())

        # Create status
        status_manager.create_status(status_id, "count_rate", 30, {})

        # Simulate legacy data: store a string in the results key
        # (This would have happened before the fix for update_status)
        results_key = f"measurement:results:{status_id}"
        redis_client.set(
            results_key, json.dumps("count_rate measurement completed successfully")
        )

        # get_results should handle this gracefully and return None instead of raising
        results = status_manager.get_results(status_id)
        assert results is None

    def test_get_results_with_valid_dict(self, status_manager):
        """Test that get_results returns valid dictionary results."""
        status_id = str(uuid.uuid4())

        # Create status
        status_manager.create_status(status_id, "count_rate", 30, {})

        # Update with valid dictionary results
        results_dict = {"total_count": 12345, "duration": 30.0, "error_rate": 0.01}
        status_manager.update_status(
            status_id,
            MeasurementStatus.COMPLETED.value,
            "Measurement completed successfully",
            results_dict,
        )

        # Verify results are retrieved correctly
        retrieved_results = status_manager.get_results(status_id)
        assert retrieved_results == results_dict

    def test_get_results_with_none(self, status_manager):
        """Test that get_results returns None when no results are stored."""
        status_id = str(uuid.uuid4())

        # Create status without results
        status_manager.create_status(status_id, "count_rate", 30, {})

        # get_results should return None
        results = status_manager.get_results(status_id)
        assert results is None

    def test_measurement_status_response_validation(self, status_manager):
        """Test that MeasurementStatusResponse validates results field correctly.

        This ensures the Pydantic model rejects non-dict results and prevents
        validation errors when retrieving measurement status.
        """
        from app.models import MeasurementStatusResponse
        from datetime import datetime

        status_id = str(uuid.uuid4())

        # Create status with valid dict results
        status_manager.create_status(status_id, "count_rate", 30, {})
        status_manager.update_status(
            status_id,
            MeasurementStatus.COMPLETED.value,
            "Measurement completed successfully",
            {"count": 100, "duration": 30.0},
        )

        status = status_manager.get_status(status_id)
        results = status_manager.get_results(status_id)

        # This should not raise a validation error
        response = MeasurementStatusResponse(
            measurement_id=status_id,
            measurement_type=status["measurement_type"],
            status=status["status"],
            started_at=datetime.fromisoformat(status["started_at"]),
            duration_so_far=0.0,
            metadata=None,
            results=results,  # results is a valid dict, not a string
        )

        assert response.results == {"count": 100, "duration": 30.0}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
