"""Tests for count-rate live measurement handler implementation."""

import pytest
import asyncio
import json
from datetime import datetime
from unittest.mock import MagicMock

from app.handlers.count_rate_live import CountRateLiveMeasurementHandler
from app.models import CountRateMetadata


async def safe_await(task):
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.fixture
def mock_redis():
    """Mock Redis client."""
    return MagicMock()


@pytest.fixture
async def handler(mock_redis):
    """Create a handler for testing."""
    mock_tagger = MagicMock()
    mock_tagger.setTestSignal = MagicMock()
    h = CountRateLiveMeasurementHandler(tagger=mock_tagger)
    h.status_id = "test-status-id"
    h.redis_client = mock_redis
    return h


@pytest.fixture
def metadata():
    """Create metadata for testing."""
    return CountRateMetadata(user_name="test_user", 
        channels=[1, 2],
        binwidth=int(1e9),
        n_values=1,
    )


class TestCountRateLiveMeasurementHandler:
    """Test CountRateLiveMeasurementHandler functionality."""

    @pytest.mark.asyncio
    async def test_handler_initialization(self, handler):
        """Handler should initialize correctly."""
        assert handler._measurement_task is None
        assert handler._count == 0
        assert handler._start_time is None

    @pytest.mark.asyncio
    async def test_start_handler_publishes_to_redis(self, handler, metadata, mock_redis):
        """Should start measurement task and publish to redis."""
        task = asyncio.create_task(handler.start(0.2, metadata))
        
        # Wait for at least a few 0.04s loops
        await asyncio.sleep(0.15)

        assert handler._measurement_task is not None
        assert handler._start_time is not None

        # Verify redis publish was called
        assert mock_redis.publish.called
        assert mock_redis.publish.call_count >= 2
        
        # Check payload
        call_args = mock_redis.publish.call_args[0]
        channel = call_args[0]
        payload = json.loads(call_args[1])
        
        assert channel == "measurement:data:test-status-id"
        assert payload["type"] == "count_rate"
        assert payload["status_id"] == "test-status-id"
        assert "data" in payload
        assert "timestamp" in payload

        await handler.stop()
        await safe_await(task)

    @pytest.mark.asyncio
    async def test_stop_handler_returns_results(self, handler, metadata):
        """Should return results when stopped."""
        task = asyncio.create_task(handler.start(0.2, metadata))
        await asyncio.sleep(0.1)

        results = await handler.stop()
        await safe_await(task)

        assert "total_count" in results
        assert "duration_seconds" in results
        assert "count_rate_cps" in results
        assert "stopped_at" in results

        assert results["total_count"] >= 0
        assert results["duration_seconds"] >= 0.1

    @pytest.mark.asyncio
    async def test_measurement_task_cleanup(self, handler, metadata):
        """Measurement task should be cancelled on stop."""
        task = asyncio.create_task(handler.start(0.2, metadata))
        await asyncio.sleep(0.1)

        assert handler._measurement_task is not None
        assert not handler._measurement_task.done()

        await handler.stop()
        await safe_await(task)

        assert handler._measurement_task.done()

    @pytest.mark.asyncio
    async def test_results_have_correct_types(self, handler, metadata):
        """Results should have correct data types."""
        task = asyncio.create_task(handler.start(0.2, metadata))
        await asyncio.sleep(0.1)

        results = await handler.stop()
        await safe_await(task)

        assert isinstance(results["total_count"], int)
        assert isinstance(results["duration_seconds"], float)
        assert isinstance(results["count_rate_cps"], float)
        assert isinstance(results["stopped_at"], str)

    @pytest.mark.asyncio
    async def test_redis_publish_failure_handled_gracefully(self, handler, metadata, mock_redis):
        """Should handle exceptions during redis publish gracefully."""
        # Make redis throw an exception
        mock_redis.publish.side_effect = Exception("Redis connection failed")
        
        task = asyncio.create_task(handler.start(0.2, metadata))
        # Wait a bit to ensure loop runs
        await asyncio.sleep(0.1)
        
        # Should not crash, just logs a warning
        assert not task.done()
        
        results = await handler.stop()
        await safe_await(task)
        assert results["status"] == "stopped"


class TestCountRateLiveMeasurementHandlerEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_very_short_measurement(self):
        """Should handle very short measurements."""
        mock_tagger = MagicMock()
        mock_tagger.setTestSignal = MagicMock()
        handler = CountRateLiveMeasurementHandler(tagger=mock_tagger)
        metadata = CountRateMetadata(user_name="test_user", 
            channels=[1],
            binwidth=int(1e9),
            n_values=1,
        )

        task = asyncio.create_task(handler.start(0.01, metadata))
        
        # Since duration is 0.01, the while loop will exit immediately before waiting
        # Or it might run once if the first time check passes.
        await safe_await(task)

        results = await handler.stop()
        
        assert results["duration_seconds"] > 0
        assert results["total_count"] >= 0

    @pytest.mark.asyncio
    async def test_concurrent_operations_isolated(self):
        """Multiple handlers should be isolated."""
        mock_tagger1 = MagicMock()
        mock_tagger2 = MagicMock()

        handler1 = CountRateLiveMeasurementHandler(tagger=mock_tagger1)
        handler1.status_id = "h1"
        handler1.redis_client = MagicMock()
        
        handler2 = CountRateLiveMeasurementHandler(tagger=mock_tagger2)
        handler2.status_id = "h2"
        handler2.redis_client = MagicMock()
        
        metadata = CountRateMetadata(user_name="test_user", 
            channels=[1],
            binwidth=int(1e9),
            n_values=1,
        )

        task1 = asyncio.create_task(handler1.start(0.2, metadata))
        task2 = asyncio.create_task(handler2.start(0.2, metadata))

        await asyncio.sleep(0.15)

        results1 = await handler1.stop()
        results2 = await handler2.stop()

        await safe_await(task1)
        await safe_await(task2)

        assert results1["duration_seconds"] > 0
        assert results2["duration_seconds"] > 0
        
        assert handler1.redis_client.publish.called
        assert handler2.redis_client.publish.called

        # channel strings
        assert handler1.redis_client.publish.call_args[0][0] == "measurement:data:h1"
        assert handler2.redis_client.publish.call_args[0][0] == "measurement:data:h2"

    @pytest.mark.asyncio
    async def test_count_rate_handles_getData_failure(self):
        """Should handle getData() throwing an exception gracefully."""
        from unittest.mock import patch
        mock_tagger = MagicMock()
        
        # We need to simulate Counter initialization and then getData throwing exception
        mock_counter = MagicMock()
        mock_counter.getData.side_effect = Exception("Hardware timeout")
        
        with patch("app.handlers.count_rate_live.TimeTagger.Counter", return_value=mock_counter):
            handler = CountRateLiveMeasurementHandler(tagger=mock_tagger)
            metadata = CountRateMetadata(user_name="test_user", 
                channels=[1],
                binwidth=int(1e9),
                n_values=1,
            )

            task = asyncio.create_task(handler.start(0.2, metadata))
            await asyncio.sleep(0.1)
            
            # This shouldn't crash
            results = await handler.stop()
            
            # The background task might crash, but stop() should return safely
            try:
                await safe_await(task)
            except Exception:
                pass
                
            assert results["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_zero_division_protection(self):
        """Should not cause division by zero."""
        mock_tagger = MagicMock()
        handler = CountRateLiveMeasurementHandler(tagger=mock_tagger)

        # This shouldn't happen in practice, but let's be defensive
        results = await handler.stop()

        # Should handle gracefully
        assert "error" in results or "count_rate_cps" in results
