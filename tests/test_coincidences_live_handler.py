"""Tests for the Coincidences Live Measurement Handler."""

import pytest
import asyncio
from unittest.mock import MagicMock, AsyncMock, patch
from datetime import datetime
from app.services.coincidences_live import CoincidencesLiveMeasurementHandler
from app.models import CoincidencesMetadata

@pytest.fixture
def mock_redis():
    redis = MagicMock()
    return redis

@pytest.fixture
def mock_tagger():
    tagger = MagicMock()
    return tagger

class TestCoincidencesLiveMeasurementHandler:
    """Test coincidences live measurement handler."""

    def test_handler_initialization(self, mock_tagger):
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        assert handler.tagger == mock_tagger
        assert handler._measurement_task is None
        assert handler._start_time is None

    @pytest.mark.asyncio
    async def test_start_and_stop_live_coincidences(self, mock_tagger, mock_redis):
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        handler.redis_client = mock_redis
        handler.status_id = "test_status_id"
        metadata = CoincidencesMetadata(user_name="test_user", channels=[1, 2], refresh_rate=100) # fast refresh

        # Start measurement in background
        task = asyncio.create_task(handler.start(duration_seconds=0.1, metadata=metadata))
        
        # Give it a moment to run and publish
        await asyncio.sleep(0.05)
        
        # Stop measurement
        result = await handler.stop()
        await task
        
        assert result["status"] == "stopped"
        assert "duration" in result
        
        # Verify redis was called
        assert mock_redis.publish.called
        
        # Verify publish channel
        call_args = mock_redis.publish.call_args[0]
        assert call_args[0] == "measurement:data:test_status_id"

    @pytest.mark.asyncio
    async def test_stop_without_start(self, mock_tagger):
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        result = await handler.stop()
        
        assert result["status"] == "stopped"
        assert result["duration"] == 0

    @pytest.mark.asyncio
    async def test_start_cancellation(self, mock_tagger):
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        metadata = CoincidencesMetadata(user_name="test_user", channels=[1, 2])
        
        task = asyncio.create_task(handler.start(duration_seconds=10, metadata=metadata))
        await asyncio.sleep(0.05)
        
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
            
        assert handler._stopped is True
