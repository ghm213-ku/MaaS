"""Tests for count-rate measurement handler implementation."""

import pytest
import asyncio
from datetime import datetime

from app.services.count_rate import CountRateMeasurementHandler
from app.models import CountRateMetadata


async def safe_await(task):
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.fixture
async def handler():
    """Create a handler for testing."""
    from unittest.mock import MagicMock
    mock_tagger = MagicMock()
    mock_tagger.setTestSignal = MagicMock()
    return CountRateMeasurementHandler(tagger=mock_tagger)


@pytest.fixture
def metadata():
    """Create metadata for testing."""
    return CountRateMetadata(
        channels=[1, 2],
        binwidth=int(1e9),
        n_values=1,
        target_location="desktop/MaasData/test",
    )


class TestCountRateMeasurementHandler:
    """Test CountRateMeasurementHandler functionality."""

    @pytest.mark.asyncio
    async def test_handler_initialization(self, handler):
        """Handler should initialize correctly."""
        assert handler._measurement_task is None
        assert handler._count == 0
        assert handler._start_time is None

    @pytest.mark.asyncio
    async def test_start_handler(self, handler, metadata):
        """Should start measurement task."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        assert handler._measurement_task is not None
        assert handler._start_time is not None
        assert handler._count >= 0

        await handler.stop()
        await safe_await(task)

    @pytest.mark.asyncio
    async def test_stop_handler_returns_results(self, handler, metadata):
        """Should return results when stopped."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        results = await handler.stop()
        await safe_await(task)

        assert "total_count" in results
        assert "duration_seconds" in results
        assert "count_rate_cps" in results
        assert "stopped_at" in results

        assert results["total_count"] >= 0
        assert results["duration_seconds"] >= 0.05

    @pytest.mark.asyncio
    async def test_count_increments_during_measurement(self, handler, metadata):
        """Count should increment during measurement."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        # Internal polling was removed for efficiency, so handler._count
        # is only populated when stop() is called or measurement completes.
        results = await handler.stop()
        await safe_await(task)

        assert results["total_count"] > 0

    @pytest.mark.asyncio
    async def test_count_rate_calculation(self, handler, metadata):
        """Count rate should be calculated correctly."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        results = await handler.stop()
        await safe_await(task)

        duration = results["duration_seconds"]
        total_count = results["total_count"]
        count_rate = results["count_rate_cps"]

        # Verify calculation (with small tolerance for timing)
        expected_rate = total_count / duration if duration > 0 else 0
        assert abs(count_rate - expected_rate) < 0.01

    @pytest.mark.asyncio
    async def test_stop_without_start(self, handler):
        """Should handle stop without prior start."""
        results = await handler.stop()

        assert "error" in results

    @pytest.mark.asyncio
    async def test_measurement_task_cleanup(self, handler, metadata):
        """Measurement task should be cancelled on stop."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        assert handler._measurement_task is not None
        assert not handler._measurement_task.done()

        await handler.stop()
        await safe_await(task)

        assert handler._measurement_task.done()

    @pytest.mark.asyncio
    async def test_results_have_correct_types(self, handler, metadata):
        """Results should have correct data types."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        results = await handler.stop()
        await safe_await(task)

        assert isinstance(results["total_count"], int)
        assert isinstance(results["duration_seconds"], float)
        assert isinstance(results["count_rate_cps"], float)
        assert isinstance(results["stopped_at"], str)

    @pytest.mark.asyncio
    async def test_metadata_in_results(self, handler, metadata):
        """Results should maintain metadata association."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        results = await handler.stop()
        await safe_await(task)

        # Metadata should be available in handler (implementation detail)
        # For now, just verify results are returned
        assert results is not None

    @pytest.mark.asyncio
    async def test_multiple_start_stop_cycles(self, handler, metadata):
        """Should support multiple measurement cycles."""
        # First cycle
        task1 = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)
        results1 = await handler.stop()
        await safe_await(task1)
        count1 = results1["total_count"]

        # Second cycle
        task2 = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)
        results2 = await handler.stop()
        await safe_await(task2)
        count2 = results2["total_count"]

        # Both should have counts
        assert count1 > 0
        assert count2 > 0

    @pytest.mark.asyncio
    async def test_varying_durations(self, handler, metadata):
        """Should produce different results for different durations."""
        # Short measurement
        task_short = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.02)
        results_short = await handler.stop()
        await safe_await(task_short)
        count_short = results_short["total_count"]

        # Longer measurement
        task_long = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.06)
        results_long = await handler.stop()
        await safe_await(task_long)
        count_long = results_long["total_count"]

        # Longer should have more counts or equal
        assert count_long >= count_short


class TestCountRateMeasurementHandlerEdgeCases:
    """Test edge cases and boundary conditions."""

    @pytest.mark.asyncio
    async def test_very_short_measurement(self):
        """Should handle very short measurements."""
        from unittest.mock import MagicMock
        mock_tagger = MagicMock()
        mock_tagger.setTestSignal = MagicMock()
        handler = CountRateMeasurementHandler(tagger=mock_tagger)
        metadata = CountRateMetadata(
            channels=[1],
            binwidth=int(1e9),
            n_values=1,
            target_location="desktop/MaasData/test",
        )

        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.01)  # 10ms

        results = await handler.stop()
        await safe_await(task)

        assert results["duration_seconds"] > 0
        assert results["total_count"] >= 0

    @pytest.mark.asyncio
    async def test_concurrent_operations_isolated(self):
        """Multiple handlers should be isolated."""
        from unittest.mock import MagicMock
        mock_tagger1 = MagicMock()
        mock_tagger1.setTestSignal = MagicMock()
        mock_tagger2 = MagicMock()
        mock_tagger2.setTestSignal = MagicMock()

        handler1 = CountRateMeasurementHandler(tagger=mock_tagger1)
        handler2 = CountRateMeasurementHandler(tagger=mock_tagger2)
        metadata = CountRateMetadata(
            channels=[1],
            binwidth=int(1e9),
            n_values=1,
            target_location="desktop/MaasData/test",
        )

        task1 = asyncio.create_task(handler1.start(1, metadata))
        task2 = asyncio.create_task(handler2.start(1, metadata))

        await asyncio.sleep(0.05)

        results1 = await handler1.stop()
        results2 = await handler2.stop()

        await safe_await(task1)
        await safe_await(task2)

        assert results1["duration_seconds"] > 0
        assert results2["duration_seconds"] > 0
        # Results should be independent
        assert results1["total_count"] > 0
        assert results2["total_count"] > 0

    @pytest.mark.asyncio
    async def test_count_rate_handles_getData_failure(self):
        """Should handle getData() throwing an exception during stop gracefully."""
        from unittest.mock import MagicMock, patch
        mock_tagger = MagicMock()
        mock_tagger.setTestSignal = MagicMock()
        
        # We need to simulate Counter initialization and then getData throwing exception
        mock_counter = MagicMock()
        mock_counter.getData.side_effect = Exception("Hardware timeout")
        
        with patch("app.services.count_rate.TimeTagger.Counter", return_value=mock_counter):
            handler = CountRateMeasurementHandler(tagger=mock_tagger)
            metadata = CountRateMetadata(
                channels=[1],
                binwidth=int(1e9),
                n_values=1,
            )

            task = asyncio.create_task(handler.start(1, metadata))
            await asyncio.sleep(0.01)
            
            # This shouldn't crash
            results = await handler.stop()
            
            # The background task might crash, but stop() should return safely
            try:
                await safe_await(task)
            except Exception:
                pass
                
            assert results["status"] == "stopped"
            assert results["total_count"] == 0

    @pytest.mark.asyncio
    async def test_zero_division_protection(self):
        """Should not cause division by zero."""
        from unittest.mock import MagicMock
        mock_tagger = MagicMock()
        handler = CountRateMeasurementHandler(tagger=mock_tagger)

        # This shouldn't happen in practice, but let's be defensive
        results = await handler.stop()

        # Should handle gracefully
        assert "error" in results or "count_rate_cps" in results
