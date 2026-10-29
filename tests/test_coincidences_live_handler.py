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
        metadata = CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2]], refresh_rate=100) # fast refresh

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
        metadata = CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2]])
        
        task = asyncio.create_task(handler.start(duration_seconds=10, metadata=metadata))
        await asyncio.sleep(0.05)
        
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
            
        assert handler._stopped is True

    @pytest.mark.asyncio
    async def test_multiple_coincidences_live_with_virtual_tagger(self, mock_redis):
        """Should run multiple coincidences live measurement with Virtual TimeTagger."""
        from Swabian import TimeTagger
        tagger = TimeTagger.createTimeTaggerVirtual()
        try:
            handler = CoincidencesLiveMeasurementHandler(tagger=tagger)
            handler.redis_client = mock_redis
            handler.status_id = "test_multiple_live_id"
            metadata = CoincidencesMetadata(
                user_name="test_user",
                coincidences=[[1, 2], [2, 3, 5]],
                refresh_rate=100,
            )
            task = asyncio.create_task(handler.start(duration_seconds=0.1, metadata=metadata))
            await asyncio.sleep(0.05)
            result = await handler.stop()
            await task
            assert result["status"] == "stopped"
            assert mock_redis.publish.called

            import json
            # Verify the main channel payload format
            main_calls = [c for c in mock_redis.publish.call_args_list if c[0][0] == "measurement:data:test_multiple_live_id"]
            assert len(main_calls) > 0
            payload = json.loads(main_calls[-1][0][1])
            assert payload["type"] == "coincidences_live"
            assert payload["status_id"] == "test_multiple_live_id"
            assert payload["coincidences"] == [[1, 2], [2, 3, 5]]
            assert len(payload["virtual_channels"]) == 2
            assert len(payload["streams"]) == 2
            assert payload["streams"][0]["coincidence"] == [1, 2]
            assert payload["streams"][0]["virtual_channel"] == payload["virtual_channels"][0]
            assert payload["streams"][1]["coincidence"] == [2, 3, 5]
            assert payload["streams"][1]["virtual_channel"] == payload["virtual_channels"][1]
            assert "data" in payload
            assert "timestamp" in payload

            # Verify individual stream sub-channel publishing
            stream_0_calls = [c for c in mock_redis.publish.call_args_list if c[0][0] == "measurement:data:test_multiple_live_id:stream_0"]
            assert len(stream_0_calls) > 0
            s0 = json.loads(stream_0_calls[-1][0][1])
            assert s0["type"] == "coincidences_live_stream"
            assert s0["coincidence"] == [1, 2]
            assert s0["virtual_channel"] == payload["virtual_channels"][0]
        finally:
            TimeTagger.freeTimeTagger(tagger)
