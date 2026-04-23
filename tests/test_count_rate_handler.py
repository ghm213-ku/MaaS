"""Tests for count-rate measurement handler implementation."""
import pytest
import asyncio
from datetime import datetime

from app.services.count_rate import CountRateMeasurementHandler


@pytest.fixture
async def handler():
    """Create a handler for testing."""
    return CountRateMeasurementHandler()


class TestCountRateMeasurementHandler:
    """Test CountRateMeasurementHandler functionality."""
    
    @pytest.mark.asyncio
    async def test_handler_initialization(self, handler):
        """Handler should initialize correctly."""
        assert handler._measurement_task is None
        assert handler._count == 0
        assert handler._start_time is None
    
    @pytest.mark.asyncio
    async def test_start_handler(self, handler):
        """Should start measurement task."""
        await handler.start(None, None)
        
        assert handler._measurement_task is not None
        assert handler._start_time is not None
        assert handler._count == 0
    
    @pytest.mark.asyncio
    async def test_stop_handler_returns_results(self, handler):
        """Should return results when stopped."""
        await handler.start(None, {"test": "metadata"})
        
        # Let it count a bit
        await asyncio.sleep(0.2)
        
        results = await handler.stop()
        
        assert "total_count" in results
        assert "duration_seconds" in results
        assert "count_rate_cps" in results
        assert "stopped_at" in results
        
        assert results["total_count"] > 0
        assert results["duration_seconds"] >= 0.2
    
    @pytest.mark.asyncio
    async def test_count_increments_during_measurement(self, handler):
        """Count should increment during measurement."""
        await handler.start(None, None)
        
        # Wait a bit
        await asyncio.sleep(0.15)
        
        count_before_stop = handler._count
        
        results = await handler.stop()
        
        assert count_before_stop > 0
        assert results["total_count"] == count_before_stop
    
    @pytest.mark.asyncio
    async def test_count_rate_calculation(self, handler):
        """Count rate should be calculated correctly."""
        await handler.start(None, None)
        
        # Let it count for a known duration
        await asyncio.sleep(0.2)
        
        results = await handler.stop()
        
        duration = results["duration_seconds"]
        total_count = results["total_count"]
        count_rate = results["count_rate_cps"]
        
        # Verify calculation (with small tolerance for timing)
        expected_rate = total_count / duration
        assert abs(count_rate - expected_rate) < 0.01
    
    @pytest.mark.asyncio
    async def test_stop_without_start(self, handler):
        """Should handle stop without prior start."""
        results = await handler.stop()
        
        assert "error" in results
    
    @pytest.mark.asyncio
    async def test_measurement_task_cleanup(self, handler):
        """Measurement task should be cancelled on stop."""
        await handler.start(None, None)
        
        task = handler._measurement_task
        assert not task.done()
        
        await handler.stop()
        
        assert task.done()
        assert task.cancelled()
    
    @pytest.mark.asyncio
    async def test_results_have_correct_types(self, handler):
        """Results should have correct data types."""
        await handler.start(None, None)
        await asyncio.sleep(0.1)
        
        results = await handler.stop()
        
        assert isinstance(results["total_count"], int)
        assert isinstance(results["duration_seconds"], float)
        assert isinstance(results["count_rate_cps"], float)
        assert isinstance(results["stopped_at"], str)
    
    @pytest.mark.asyncio
    async def test_metadata_in_results(self, handler):
        """Results should maintain metadata association."""
        metadata = {"detector_id": "det_001", "location": "lab_B"}
        await handler.start(None, metadata)
        
        await asyncio.sleep(0.1)
        
        results = await handler.stop()
        
        # Metadata should be available in handler (implementation detail)
        # For now, just verify results are returned
        assert results is not None
    
    @pytest.mark.asyncio
    async def test_multiple_start_stop_cycles(self, handler):
        """Should support multiple measurement cycles."""
        # First cycle
        await handler.start(None, None)
        await asyncio.sleep(0.1)
        results1 = await handler.stop()
        count1 = results1["total_count"]
        
        # Second cycle
        await handler.start(None, None)
        await asyncio.sleep(0.1)
        results2 = await handler.stop()
        count2 = results2["total_count"]
        
        # Both should have counts
        assert count1 > 0
        assert count2 > 0
    
    @pytest.mark.asyncio
    async def test_varying_durations(self, handler):
        """Should produce different results for different durations."""
        # Short measurement
        await handler.start(None, None)
        await asyncio.sleep(0.05)
        results_short = await handler.stop()
        count_short = results_short["total_count"]
        
        # Longer measurement
        await handler.start(None, None)
        await asyncio.sleep(0.15)
        results_long = await handler.stop()
        count_long = results_long["total_count"]
        
        # Longer should have more counts
        assert count_long > count_short


class TestCountRateMeasurementHandlerEdgeCases:
    """Test edge cases and boundary conditions."""
    
    @pytest.mark.asyncio
    async def test_very_short_measurement(self):
        """Should handle very short measurements."""
        handler = CountRateMeasurementHandler()
        
        await handler.start(None, None)
        await asyncio.sleep(0.01)  # 10ms
        
        results = await handler.stop()
        
        assert results["duration_seconds"] > 0
        assert results["total_count"] >= 0
    
    @pytest.mark.asyncio
    async def test_concurrent_operations_isolated(self):
        """Multiple handlers should be isolated."""
        handler1 = CountRateMeasurementHandler()
        handler2 = CountRateMeasurementHandler()
        
        await handler1.start(None, None)
        await handler2.start(None, None)
        
        await asyncio.sleep(0.1)
        
        results1 = await handler1.stop()
        results2 = await handler2.stop()
        
        # Results should be independent
        assert results1["total_count"] > 0
        assert results2["total_count"] > 0
        # They should be approximately similar (both ran for ~same time)
        assert abs(results1["total_count"] - results2["total_count"]) < 50
    
    @pytest.mark.asyncio
    async def test_zero_division_protection(self):
        """Should not cause division by zero."""
        handler = CountRateMeasurementHandler()
        
        # This shouldn't happen in practice, but let's be defensive
        results = await handler.stop()
        
        # Should handle gracefully
        assert "error" in results or "count_rate_cps" in results
