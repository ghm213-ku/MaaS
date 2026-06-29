"""Tests for the core measurement service."""
import pytest
import asyncio
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from app.services.measurement import (
    MeasurementService,
    Measurement,
    MeasurementHandler,
)


class MockMeasurementHandler(MeasurementHandler):
    """Mock handler for testing."""
    
    def __init__(self):
        self.started = False
        self.stopped = False
        self.start_calls = 0
        self.stop_calls = 0
    
    async def start(self, duration_seconds, metadata, stop_checker=None):
        self.started = True
        self.start_calls += 1
    
    async def stop(self):
        self.stopped = True
        self.stop_calls += 1
        return {"mock_result": "test_data", "calls": self.stop_calls}


@pytest.fixture
async def measurement_service():
    """Create a measurement service for testing."""
    service = MeasurementService()
    service.register_handler("mock", MockMeasurementHandler)
    yield service
    await service.cleanup()


class TestMeasurementService:
    """Test MeasurementService functionality."""
    
    @pytest.mark.asyncio
    async def test_register_handler(self):
        """Should register measurement handlers."""
        service = MeasurementService()
        service.register_handler("mock", MockMeasurementHandler)
        
        assert "mock" in service._handlers
        assert service._handlers["mock"] == MockMeasurementHandler
    
    @pytest.mark.asyncio
    async def test_start_measurement_creates_unique_id(self, measurement_service):
        """Each measurement should get a unique ID."""
        service = measurement_service
        
        id1 = await service.start_measurement("mock")
        id2 = await service.start_measurement("mock")
        
        assert id1 != id2
        assert id1 in service._measurements
        assert id2 in service._measurements
    
    @pytest.mark.asyncio
    async def test_start_measurement_unknown_type_fails(self, measurement_service):
        """Should raise ValueError for unknown measurement type."""
        service = measurement_service
        
        with pytest.raises(ValueError, match="Unknown measurement type"):
            await service.start_measurement("unknown_type")
    
    @pytest.mark.asyncio
    async def test_start_measurement_with_duration(self, measurement_service):
        """Should handle measurement with duration."""
        service = measurement_service
        
        meas_id = await service.start_measurement("mock", duration_seconds=10)
        measurement = service._measurements[meas_id]
        
        assert measurement.duration_task is not None
        
        await measurement.stop()
    
    @pytest.mark.asyncio
    async def test_start_measurement_with_metadata(self, measurement_service):
        """Should store and pass metadata."""
        service = measurement_service
        metadata = {"detector": "det_001", "location": "lab_B"}
        
        meas_id = await service.start_measurement("mock", metadata=metadata)
        measurement = service._measurements[meas_id]
        
        assert measurement.metadata == metadata
    
    @pytest.mark.asyncio
    async def test_get_measurement_status_active(self, measurement_service):
        """Should get status of active measurement."""
        service = measurement_service
        
        meas_id = await service.start_measurement("mock")
        measurement = service.get_measurement_status(meas_id)
        
        assert measurement.status == "active"
        assert measurement.measurement_id == meas_id
    
    @pytest.mark.asyncio
    async def test_get_measurement_status_not_found(self, measurement_service):
        """Should raise ValueError for non-existent measurement."""
        service = measurement_service
        
        with pytest.raises(ValueError, match="not found"):
            service.get_measurement_status("nonexistent_id")
    
    @pytest.mark.asyncio
    async def test_stop_measurement_active(self, measurement_service):
        """Should stop an active measurement."""
        service = measurement_service
        
        meas_id = await service.start_measurement("mock")
        results = await service.stop_measurement(meas_id)
        
        assert results["mock_result"] == "test_data"
        
        measurement = service._measurements[meas_id]
        assert measurement.status == "stopped"
    
    @pytest.mark.asyncio
    async def test_stop_measurement_not_found(self, measurement_service):
        """Should raise ValueError when stopping non-existent measurement."""
        service = measurement_service
        
        with pytest.raises(ValueError, match="not found"):
            await service.stop_measurement("nonexistent_id")
    
    @pytest.mark.asyncio
    async def test_stop_measurement_not_active(self, measurement_service):
        """Should raise ValueError when stopping inactive measurement."""
        service = measurement_service
        
        meas_id = await service.start_measurement("mock")
        await service.stop_measurement(meas_id)
        
        with pytest.raises(ValueError, match="not active"):
            await service.stop_measurement(meas_id)
    
    @pytest.mark.asyncio
    async def test_get_duration(self, measurement_service):
        """Should calculate duration correctly."""
        service = measurement_service
        
        meas_id = await service.start_measurement("mock")
        measurement = service._measurements[meas_id]
        
        # Wait a bit
        await asyncio.sleep(0.1)
        
        duration = measurement.get_duration()
        assert duration >= 0.1
    
    @pytest.mark.asyncio
    async def test_cleanup_stops_active_measurements(self, measurement_service):
        """Cleanup should stop all active measurements."""
        service = measurement_service
        
        # Start multiple measurements
        id1 = await service.start_measurement("mock")
        id2 = await service.start_measurement("mock")
        
        # Cleanup
        await service.cleanup()
        
        # All should be stopped
        m1 = service._measurements[id1]
        m2 = service._measurements[id2]
        
        assert m1.status == "stopped"
        assert m2.status == "stopped"
    
    @pytest.mark.asyncio
    async def test_multiple_concurrent_measurements(self, measurement_service):
        """Should handle multiple concurrent measurements."""
        service = measurement_service
        
        # Start 5 measurements
        meas_ids = []
        for i in range(5):
            meas_id = await service.start_measurement("mock", metadata={"index": i})
            meas_ids.append(meas_id)
        
        # Verify all are active
        for meas_id in meas_ids:
            measurement = service.get_measurement_status(meas_id)
            assert measurement.status == "active"
        
        # Stop all
        for meas_id in meas_ids:
            await service.stop_measurement(meas_id)
        
        # Verify all are stopped
        for meas_id in meas_ids:
            measurement = service._measurements[meas_id]
            assert measurement.status == "stopped"


class TestMeasurement:
    """Test individual Measurement class."""
    
    @pytest.mark.asyncio
    async def test_measurement_creation(self):
        """Should create measurement with correct properties."""
        handler = MockMeasurementHandler()
        meas = Measurement(
            measurement_id="test_id",
            measurement_type="mock",
            handler=handler,
            duration_seconds=10,
            metadata={"test": "data"},
        )
        
        assert meas.measurement_id == "test_id"
        assert meas.status == "active"
        assert meas.metadata == {"test": "data"}
        assert meas.started_at is not None
        
        await meas.stop()
    
    @pytest.mark.asyncio
    async def test_measurement_start_handler(self):
        """Should start the handler successfully."""
        handler = MockMeasurementHandler()
        meas = Measurement(
            measurement_id="test_id",
            measurement_type="mock",
            handler=handler,
        )
        
        await meas.start_handler()
        
        assert handler.started is True
        assert handler.start_calls == 1
        
        await meas.stop()
    
    @pytest.mark.asyncio
    async def test_measurement_stop_collects_results(self):
        """Should stop handler and collect results."""
        handler = MockMeasurementHandler()
        meas = Measurement(
            measurement_id="test_id",
            measurement_type="mock",
            handler=handler,
        )
        
        await meas.start_handler()
        results = await meas.stop()
        
        assert handler.stopped is True
        assert results["mock_result"] == "test_data"
        assert meas.status == "stopped"
    
    @pytest.mark.asyncio
    async def test_measurement_auto_stop_timer(self):
        """Should auto-stop after specified duration."""
        handler = MockMeasurementHandler()
        meas = Measurement(
            measurement_id="test_id",
            measurement_type="mock",
            handler=handler,
            duration_seconds=1,
        )
        
        await meas.start_handler()
        
        # Wait for auto-stop
        await asyncio.sleep(1.5)
        
        assert meas.status == "stopped"
        assert handler.stopped is True
    
    @pytest.mark.asyncio
    async def test_measurement_cancel_auto_stop(self):
        """Should cancel auto-stop timer when stopping early."""
        handler = MockMeasurementHandler()
        meas = Measurement(
            measurement_id="test_id",
            measurement_type="mock",
            handler=handler,
            duration_seconds=10,  # Long duration
        )
        
        await meas.start_handler()
        
        # Stop immediately
        await meas.stop()
        
        assert meas.status == "stopped"
        assert meas.duration_task.cancelled()
    
    @pytest.mark.asyncio
    async def test_measurement_double_stop_safe(self):
        """Stopping twice should be safe."""
        handler = MockMeasurementHandler()
        meas = Measurement(
            measurement_id="test_id",
            measurement_type="mock",
            handler=handler,
        )
        
        await meas.start_handler()
        
        result1 = await meas.stop()
        result2 = await meas.stop()
        
        # Second stop should return same results
        assert result1 == result2


class TestMeasurementErrorHandling:
    """Test error handling in measurement service."""
    
    class FailingHandler(MeasurementHandler):
        """Handler that fails on start."""
        
        async def start(self, duration_seconds, metadata, stop_checker=None):
            raise RuntimeError("Start failed")
        
        async def stop(self):
            return {}
    
    @pytest.mark.asyncio
    async def test_start_handler_failure_handled(self):
        """Should handle handler start failures gracefully."""
        handler = self.FailingHandler()
        meas = Measurement(
            measurement_id="test_id",
            measurement_type="failing",
            handler=handler,
        )
        
        with pytest.raises(RuntimeError):
            await meas.start_handler()
        
        assert meas.status == "error"
    
    @pytest.mark.asyncio
    async def test_start_measurement_handler_failure_cleanup(self):
        """Should clean up on start failure."""
        service = MeasurementService()
        service.register_handler("failing", self.FailingHandler)
        
        with pytest.raises(RuntimeError):
            await service.start_measurement("failing")
        
        # Measurement should not be in service
        assert len(service._measurements) == 0
