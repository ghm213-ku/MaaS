"""
Integration tests for the count-rate-live API with Redis Pub/Sub.

Tests the interaction between the live streaming handler and Redis.
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
from app.services.count_rate_live import CountRateLiveMeasurementHandler


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
    # Mock counter data
    mock_counter = Mock()
    mock_counter.getData.return_value = [10, 20, 30]
    
    with patch("app.services.count_rate_live.TimeTagger.Counter", return_value=mock_counter):
        processor = JobProcessor(status_manager, tagger=mock_tagger)
        processor.register_handler("count_rate_live", CountRateLiveMeasurementHandler)
        yield processor


class TestCountRateLiveIntegration:
    """End-to-end integration tests for live count rate."""

    def test_live_data_streaming_via_pubsub(self, status_manager, job_processor, redis_client):
        """Test that the API actually streams data to Redis via Pub/Sub."""
        status_id = str(uuid.uuid4())
        
        # We need a dedicated redis client for subscribing, since pubsub blocks the connection
        pubsub_client = redis.Redis(host="localhost", port=6379, db=15, decode_responses=True)
        pubsub = pubsub_client.pubsub()
        
        channel_name = f"measurement:data:{status_id}"
        pubsub.subscribe(channel_name)
        
        # Step 1: Create status (web layer)
        metadata = {"detector": "det_001", "channels": [1, 2, 3], "user_name": "test_user"}
        status_manager.create_status(
            status_id,
            "count_rate_live",
            None,
            metadata,
        )

        # Step 2: Enqueue job (API)
        job_processor.enqueue_job(
            status_id=status_id,
            measurement_type="count_rate_live",
            duration_seconds=None,
            metadata=metadata,
        )
        
        # Step 3: Retrieve and process job (Worker)
        job = job_processor.get_next_job()
        assert job is not None
        
        job_processor.process_job(
            status_id=job["status_id"],
            measurement_type=job["measurement_type"],
            duration_seconds=job["duration_seconds"],
            metadata=job["metadata"],
        )
        
        # Step 4: Verify live streaming works by receiving messages from pub/sub
        messages = []
        timeout = time.time() + 2.0  # Wait up to 2 seconds
        
        # Let the thread run and publish
        while time.time() < timeout:
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if msg:
                messages.append(msg)
            
            # Since the API publishes at 25Hz, we should quickly get a few messages
            if len(messages) >= 3:
                break
                
        # We should have received at least a few messages
        assert len(messages) >= 3, f"Expected at least 3 messages, got {len(messages)}"
        
        for msg in messages:
            data = json.loads(msg["data"])
            assert data["type"] == "count_rate"
            assert data["status_id"] == status_id
            assert "data" in data
            assert isinstance(data["data"], list)
            assert "timestamp" in data
            
        # Manually stop since duration_seconds is None
        job_processor.stop_job(status_id)
        time.sleep(0.5)

        pubsub.unsubscribe()
        pubsub.close()
        pubsub_client.close()

    def test_live_streaming_stops_when_job_stopped(self, status_manager, job_processor, redis_client):
        """Test that streaming stops when the job is halted."""
        status_id = str(uuid.uuid4())
        
        pubsub_client = redis.Redis(host="localhost", port=6379, db=15, decode_responses=True)
        pubsub = pubsub_client.pubsub()
        channel_name = f"measurement:data:{status_id}"
        pubsub.subscribe(channel_name)
        
        metadata = {"channels": [1, 2], "user_name": "test_user"}
        status_manager.create_status(
            status_id,
            "count_rate_live",
            None,
            metadata,
        )

        job_processor.enqueue_job(
            status_id=status_id,
            measurement_type="count_rate_live",
            duration_seconds=None,
            metadata=metadata,
        )
        
        job = job_processor.get_next_job()
        
        job_processor.process_job(
            status_id=job["status_id"],
            measurement_type=job["measurement_type"],
            duration_seconds=job["duration_seconds"],
            metadata=job["metadata"],
        )
        
        # Verify it started streaming
        msg = None
        for _ in range(20):  # Wait up to 2 seconds
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if msg:
                break
            time.sleep(0.1)
            
        assert msg is not None, "Did not receive initial message"
        
        # Stop the job
        job_processor.stop_job(status_id)
        
        # Flush pending messages
        while pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1):
            pass
            
        # Give it a moment to stop
        time.sleep(1.0)
        
        # Verify no more messages arrive
        msg_after_stop = pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
        assert msg_after_stop is None, "Received message after job was stopped"
        
        status = status_manager.get_status(status_id)
        assert status["status"] == MeasurementStatus.STOPPED.value
        
        pubsub.unsubscribe()
        pubsub.close()
        pubsub_client.close()
