"""Tests for the Coincidences Live Measurement Handler."""

import json
import pytest
import asyncio
from unittest.mock import MagicMock, patch
from app.handlers.coincidences_live import CoincidencesLiveMeasurementHandler
from app.models import CoincidencesMetadata


@pytest.fixture
def mock_redis():
    return MagicMock()


@pytest.fixture
def mock_tagger():
    return MagicMock()


@pytest.fixture
def mock_tt():
    """Patch the TimeTagger module shared by both coincidences handlers."""
    tt = MagicMock()
    tt.Coincidences.return_value.getChannels.return_value = [20, 21]
    tt.Counter.return_value.getData.return_value = [[1, 2, 3], [4, 5, 6]]
    with patch("app.handlers.coincidences.TimeTagger", tt):
        yield tt


def _published(mock_redis, channel):
    return [json.loads(c[0][1]) for c in mock_redis.publish.call_args_list if c[0][0] == channel]


class TestCoincidencesLiveMeasurementHandler:
    """Test coincidences live measurement handler."""

    def test_handler_initialization(self, mock_tagger):
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        assert handler.tagger == mock_tagger
        assert handler._measurement_task is None
        assert handler._start_time is None

    @pytest.mark.asyncio
    async def test_start_and_stop_live_coincidences(self, mock_tagger, mock_redis, mock_tt):
        mock_tt.Coincidences.return_value.getChannels.return_value = [20]
        mock_tt.Counter.return_value.getData.return_value = [[7]]
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        handler.redis_client = mock_redis
        handler.status_id = "test_status_id"
        metadata = CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2]], refresh_rate=100)

        task = asyncio.create_task(handler.start(duration_seconds=10, metadata=metadata))
        await asyncio.sleep(0.05)

        result = await handler.stop()
        await task

        assert result["status"] == "stopped"
        assert "duration" in result
        assert _published(mock_redis, "measurement:data:test_status_id")
        mock_tt.Counter.return_value.stop.assert_called()

    @pytest.mark.asyncio
    async def test_uses_same_api_and_parameters_as_non_live(self, mock_tagger, mock_redis, mock_tt):
        """Live must use Coincidences + Counter with binwidth/n_values, like the one-shot handler."""
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        handler.redis_client = mock_redis
        handler.status_id = "sid"
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2], [2, 3, 5]],
            coincidence_window=2500,
            timestamp="Average",
            binwidth=int(1e9),
            n_values=3,
            refresh_rate=100,
        )

        await handler.start(duration_seconds=0.05, metadata=metadata)

        mock_tt.Coincidences.assert_called_once_with(
            mock_tagger, [[1, 2], [2, 3, 5]], 2500, mock_tt.CoincidenceTimestamp.Average
        )
        mock_tt.Counter.assert_called_once_with(
            tagger=mock_tagger, channels=[20, 21], binwidth=int(1e9), n_values=3
        )
        assert not mock_tt.Countrate.called
        mock_tt.Counter.return_value.startFor.assert_called_once_with(int(0.05 * 1e12))

    @pytest.mark.asyncio
    async def test_payload_format_for_multiple_coincidences(self, mock_tagger, mock_redis, mock_tt):
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        handler.redis_client = mock_redis
        handler.status_id = "sid"
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2], [2, 3, 5]],
            binwidth=int(5e11),  # 0.5 s bins
            n_values=3,
            refresh_rate=100,
        )

        await handler.start(duration_seconds=0.05, metadata=metadata)

        payloads = _published(mock_redis, "measurement:data:sid")
        assert payloads
        payload = payloads[-1]
        assert payload["type"] == "coincidences_live"
        assert payload["status_id"] == "sid"
        assert payload["coincidences"] == [[1, 2], [2, 3, 5]]
        assert payload["virtual_channels"] == [20, 21]
        assert payload["data"] == [[1, 2, 3], [4, 5, 6]]
        assert "timestamp" in payload
        s0, s1 = payload["streams"]
        assert s0["coincidence"] == [1, 2]
        assert s0["virtual_channel"] == 20
        assert s0["data"] == [1, 2, 3]
        assert s0["rate"] == pytest.approx(6.0)  # 3 counts in the latest 0.5 s bin
        assert s1["coincidence"] == [2, 3, 5]
        assert s1["virtual_channel"] == 21
        assert s1["rate"] == pytest.approx(12.0)

        sub = _published(mock_redis, "measurement:data:sid:stream_1")
        assert sub
        assert sub[-1]["type"] == "coincidences_live_stream"
        assert sub[-1]["coincidence"] == [2, 3, 5]
        assert sub[-1]["virtual_channel"] == 21
        assert sub[-1]["data"] == [4, 5, 6]

    @pytest.mark.asyncio
    async def test_hardware_setup_error_propagates(self, mock_tagger, mock_redis, mock_tt):
        """A failed hardware setup must fail the job instead of streaming zeros."""
        mock_tt.Coincidences.side_effect = RuntimeError("channel not available")
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        handler.redis_client = mock_redis
        handler.status_id = "sid"
        metadata = CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2]])

        with pytest.raises(RuntimeError, match="channel not available"):
            await handler.start(duration_seconds=0.05, metadata=metadata)
        assert not mock_redis.publish.called

    @pytest.mark.asyncio
    async def test_stop_does_not_delete_files(self, mock_tagger):
        """Live measurements never write target_location, so stop must not delete it."""
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        with patch.object(handler, "_delete_output_file") as mock_delete:
            await handler.stop()
        mock_delete.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_without_start(self, mock_tagger):
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        result = await handler.stop()

        assert result["status"] == "stopped"
        assert result["duration"] == 0

    @pytest.mark.asyncio
    async def test_start_cancellation(self, mock_tagger, mock_tt):
        handler = CoincidencesLiveMeasurementHandler(tagger=mock_tagger)
        metadata = CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2]])

        task = asyncio.create_task(handler.start(duration_seconds=10, metadata=metadata))
        await asyncio.sleep(0.05)

        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

        assert handler._stopped is True
        mock_tt.Counter.return_value.stop.assert_called()
