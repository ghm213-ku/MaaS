"""End-to-End API Integration Tests.

These tests run the full FastAPI web layer along with a real JobProcessor (using mocked hardware) 
and real Redis to verify the end-to-end flow of all major APIs.
"""

import asyncio
import json
import time
import pytest
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

import redis

from main import app
from app.services.status_manager import StatusManager, MeasurementStatus
from app.services.job_processor import JobProcessor
from app.api.routes import set_processors

# Import all handlers
from app.services.count_rate import CountRateMeasurementHandler
from app.services.count_rate_live import CountRateLiveMeasurementHandler
from app.services.save_raw_tags import SaveRawTagsMeasurementHandler
from app.services.coincidences import CoincidencesMeasurementHandler
from app.services.correlation import CorrelationMeasurementHandler
from app.services.set_parameters import SetParametersHandler
from app.services.time_histograms_live import (
    StartStopLiveMeasurementHandler,
    HistogramLiveMeasurementHandler,
    CorrelationLiveMeasurementHandler,
)


@pytest.fixture
def redis_client():
    """Get Redis client for testing."""
    try:
        client = redis.Redis(host="127.0.0.1", port=6379, db=15, decode_responses=True)
        client.ping()
        yield client
    except redis.ConnectionError:
        pytest.skip("Redis server not available on 127.0.0.1:6379")
    finally:
        try:
            client.flushdb()
        except:
            pass


@pytest.fixture
def e2e_setup(redis_client):
    """Sets up StatusManager, JobProcessor, and TestClient for E2E testing."""
    # 1. Real Status Manager
    status_manager = StatusManager(redis_host="127.0.0.1", redis_port=6379, redis_db=15)

    # 2. Real Job Processor with mock hardware
    mock_tagger = MagicMock()
    job_processor = JobProcessor(status_manager, tagger=mock_tagger)
    
    # Register all handlers
    job_processor.register_handler("count_rate", CountRateMeasurementHandler)
    job_processor.register_handler("count_rate_live", CountRateLiveMeasurementHandler)
    job_processor.register_handler("save_raw_tags", SaveRawTagsMeasurementHandler)
    job_processor.register_handler("coincidences", CoincidencesMeasurementHandler)
    job_processor.register_handler("correlation", CorrelationMeasurementHandler)
    job_processor.register_handler("set_parameters", SetParametersHandler)
    job_processor.register_handler("startstop_live", StartStopLiveMeasurementHandler)
    job_processor.register_handler("histogram_live", HistogramLiveMeasurementHandler)
    job_processor.register_handler("correlation_live", CorrelationLiveMeasurementHandler)

    # We need to start the background worker loop manually for the test
    # Normally worker.py calls poll_jobs() in a loop. For E2E we'll use a background thread or asyncio task.
    import threading
    stop_polling = threading.Event()

    def poll_worker():
        while not stop_polling.is_set():
            job = job_processor.get_next_job()
            if job:
                job_processor.process_job(
                    status_id=job.get("status_id"),
                    measurement_type=job.get("measurement_type"),
                    duration_seconds=job.get("duration_seconds"),
                    metadata=job.get("metadata"),
                )
            time.sleep(0.1)

    worker_thread = threading.Thread(target=poll_worker, daemon=True)
    worker_thread.start()

    # 3. FastAPI Client setup
    set_processors(job_processor, status_manager)
    client = TestClient(app)

    yield client, status_manager, redis_client

    # Cleanup
    stop_polling.set()
    worker_thread.join(timeout=2.0)


class TestE2EMeasurementWorkflows:
    """E2E tests for measurement APIs."""

    def test_count_rate_e2e(self, e2e_setup):
        """Test complete count-rate measurement flow."""
        client, status_manager, r = e2e_setup

        client.post("/api/v1/channels/book", json={"user_name": "e2e_test", "channel_numbers": [1, 2]})

        payload = {
            "measurement_type": "count_rate",
            "duration_seconds": 1,
            "metadata": {
                "user_name": "e2e_test",
                "channels": [1, 2],
                "binwidth": 1000,
                "n_values": 1
            }
        }
        
        # Start
        resp = client.post("/api/v1/measurements/count-rate", json=payload)
        assert resp.status_code == 201
        meas_id = resp.json()["measurement_id"]

        # Wait for completion (duration is 1s, plus some overhead)
        # Use polling to prevent flakiness
        completed = False
        for _ in range(50):
            status_resp = client.get(f"/api/v1/measurements/{meas_id}/status")
            assert status_resp.status_code == 200
            data = status_resp.json()
            if data["status"] == "completed":
                completed = True
                break
            time.sleep(0.1)
            
        assert completed, f"Measurement did not complete in time, last status: {data['status']}"
        assert "results" in data
        assert data["results"] is not None

    def test_live_histogram_e2e(self, e2e_setup):
        """Test a live streaming endpoint (histogram-live) end-to-end."""
        client, status_manager, r = e2e_setup

        client.post("/api/v1/channels/book", json={"user_name": "e2e_test", "channel_numbers": [1, 2]})

        payload = {
            "measurement_type": "histogram_live",
            "metadata": {
                "click_channel": 1,
                "start_channel": 2,
                "user_name": "e2e_test",
                "refresh_rate": 10  # 10Hz
            }
        }

        # Subscribe to redis channel
        pubsub = r.pubsub()
        # We don't know the meas_id yet, so we subscribe to pattern
        pubsub.psubscribe("measurement:data:*")
        
        # Start
        resp = client.post("/api/v1/measurements/histogram-live", json=payload)
        assert resp.status_code == 201
        meas_id = resp.json()["measurement_id"]

        # Wait for completion
        messages = []
        for _ in range(50):
            msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=0.1)
            if msg:
                messages.append(msg)
                break
            time.sleep(0.1)

        assert len(messages) > 0, "No live data streamed to Redis"
        
        first_data = json.loads(messages[0]["data"])
        assert first_data["type"] == "histogram_live"
        assert first_data["status_id"] == meas_id
        assert "data" in first_data
        assert "index" in first_data
        
        # Stop measurement
        client.delete(f"/api/v1/measurements/{meas_id}")

    def test_correlation_e2e(self, e2e_setup):
        """Test complete correlation measurement flow."""
        client, status_manager, r = e2e_setup

        client.post("/api/v1/channels/book", json={"user_name": "e2e_test", "channel_numbers": [1, 2]})

        payload = {
            "measurement_type": "correlation",
            "duration_seconds": 1,
            "metadata": {
                "channel1": 1,
                "channel2": 2,
                "user_name": "e2e_test",
                "target_location": "desktop/test_corr_{datetime}.csv"
            }
        }
        
        # Start
        resp = client.post("/api/v1/measurements/correlation", json=payload)
        assert resp.status_code == 201
        meas_id = resp.json()["measurement_id"]

        # Wait for completion
        completed = False
        for _ in range(50):
            status_resp = client.get(f"/api/v1/measurements/{meas_id}/status")
            assert status_resp.status_code == 200
            if status_resp.json()["status"] == "completed":
                completed = True
                break
            time.sleep(0.1)
            
        assert completed, "Correlation measurement did not complete in time"

    def test_set_parameters_e2e(self, e2e_setup):
        """Test set-parameters flow."""
        client, status_manager, r = e2e_setup

        client.post("/api/v1/channels/book", json={"user_name": "e2e_test", "channel_numbers": [1, 2]})

        payload = {
            "measurement_type": "set_parameters",
            "duration_seconds": 0,
            "metadata": {
                "channels": [1, 2],
                "user_name": "e2e_test",
                "input_delay": 500,
                "trigger_voltage": 0.5
            }
        }
        
        # Start
        resp = client.post("/api/v1/set-parameters/", json=payload)
        assert resp.status_code == 201
        meas_id = resp.json()["measurement_id"]

        # Wait for completion (instant)
        time.sleep(0.5)

        # Check status
        status_resp = client.get(f"/api/v1/measurements/{meas_id}/status")
        assert status_resp.status_code == 200
        assert status_resp.json()["status"] == "completed"
