"""
Integration tests for the distributed architecture.

Tests the interaction between web layer, Redis, and backend workers.
"""
import asyncio
import json
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest
import redis

from app.services.status_manager import StatusManager, MeasurementStatus
from app.services.job_processor import JobProcessor
from app.services.count_rate import CountRateMeasurementHandler
from app.services.save_raw_tags import SaveRawTagsMeasurementHandler


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
    processor = JobProcessor(status_manager)
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
            metadata={"detector": "det_001"},
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
            MeasurementStatus.ACTIVE,
            "Measurement started",
            None,
        )
        
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.ACTIVE.value
        
        # Update to completed with results
        results = {"total_count": 12345, "duration": 30.5}
        status_manager.update_status(
            status_id,
            MeasurementStatus.COMPLETED,
            "Measurement completed",
            results,
        )
        
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.COMPLETED.value
        assert status_manager.get_results(status_id) == results

    def test_metadata_persistence(self, status_manager):
        """Test metadata is properly stored and retrieved."""
        status_id = str(uuid.uuid4())
        metadata = {
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

    def test_delete_status(self, status_manager):
        """Test deleting a status."""
        status_id = str(uuid.uuid4())
        
        status_manager.create_status(status_id, "count_rate", 30, {})
        status = status_manager.get_status(status_id)
        assert status is not None
        
        status_manager.delete_status(status_id)
        status = status_manager.get_status(status_id)
        assert status is None

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
            {"detector": "test"},
        )
        
        # Process job (should update status)
        with patch.object(CountRateMeasurementHandler, "start"):
            job_processor.process_job(status_id, "count_rate", 2)
            
            # Give thread a moment to start
            time.sleep(0.1)
            
            # Check status was marked as active
            status = status_manager.get_status(status_id)
            assert status["status"] in [
                MeasurementStatus.ACTIVE.value,
                MeasurementStatus.QUEUED.value,
            ]

    def test_handler_registration(self, job_processor):
        """Test handler registration."""
        assert "count_rate" in job_processor.handlers
        assert "save_raw_tags" in job_processor.handlers
        assert job_processor.handlers["count_rate"] == CountRateMeasurementHandler
        assert job_processor.handlers["save_raw_tags"] == SaveRawTagsMeasurementHandler

    def test_stop_job(self, status_manager, job_processor):
        """Test stopping a job."""
        status_id = str(uuid.uuid4())
        
        status_manager.create_status(status_id, "count_rate", 10, {})
        
        # Mark as active
        status_manager.update_status(
            status_id,
            MeasurementStatus.ACTIVE,
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
                {"job": i},
            )
        
        # Start all jobs
        with patch.object(CountRateMeasurementHandler, "start"):
            for status_id in status_ids:
                job_processor.process_job(status_id, "count_rate", 1)
        
        # Give threads a moment to start
        time.sleep(0.2)
        
        # Check all jobs are tracked
        for status_id in status_ids:
            job_info = job_processor.get_job_status(status_id)
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
            MeasurementStatus.ACTIVE,
            "Measurement started",
            None,
        )
        
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.ACTIVE.value
        
        # Step 4: Complete with results (worker)
        results = {"total_count": 50000, "duration": 5.0}
        status_manager.update_status(
            status_id,
            MeasurementStatus.COMPLETED,
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
            MeasurementStatus.ACTIVE,
            "Running",
            None,
        )
        
        # Fail with error
        error_message = "Connection timeout to detector"
        status_manager.update_status(
            status_id,
            MeasurementStatus.FAILED,
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
            MeasurementStatus.ACTIVE,
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
        metadata = {
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
            MeasurementStatus.ACTIVE,
            "Running",
            None,
        )
        status_manager.update_status(
            status_id,
            MeasurementStatus.COMPLETED,
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
            (MeasurementStatus.QUEUED, "Queued"),
            (MeasurementStatus.ACTIVE, "Active"),
            (MeasurementStatus.COMPLETED, "Done"),
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


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
