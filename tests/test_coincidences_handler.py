"""Tests for the Coincidences Measurement Handler."""

import pytest
import asyncio
from unittest.mock import MagicMock
from app.services.coincidences import CoincidencesMeasurementHandler
from app.models import CoincidencesMetadata

@pytest.fixture
def mock_tagger():
    """Create a mock TimeTagger."""
    mock = MagicMock()
    return mock

class TestCoincidencesMeasurementHandler:
    """Test coincidences measurement handler."""

    @pytest.mark.asyncio
    async def test_start_and_stop_coincidences(self, mock_tagger):
        """Should initialize and stop gracefully."""
        handler = CoincidencesMeasurementHandler(tagger=mock_tagger)
        metadata = CoincidencesMetadata(user_name="test_user", 
            coincidenceWindow=1000,
            channels=[1, 2]
        )

        task = asyncio.create_task(handler.start(0.01, metadata))
        await asyncio.sleep(0.05)

        results = await handler.stop()
        
        try:
            await asyncio.wait_for(task, timeout=1.0)
        except asyncio.TimeoutError:
            pass

        assert results["status"] == "stopped"
        assert "duration" in results

    @pytest.mark.asyncio
    async def test_stop_without_start(self, mock_tagger):
        """Should handle stop gracefully even if never started."""
        handler = CoincidencesMeasurementHandler(tagger=mock_tagger)
        results = await handler.stop()
        
        assert results["status"] == "stopped"
        assert results["duration"] == 0

    @pytest.mark.asyncio
    async def test_stop_failure_is_handled(self, mock_tagger):
        """Should handle exception if stop throws an error."""
        handler = CoincidencesMeasurementHandler(tagger=mock_tagger)
        
        mock_counter = MagicMock()
        mock_counter.stop.side_effect = Exception("Hardware timeout")
        handler._counter = mock_counter
        
        results = await handler.stop()
        
        assert results["status"] == "stopped"
