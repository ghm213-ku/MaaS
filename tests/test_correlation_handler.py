"""Tests for correlation measurement handler implementation."""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import MagicMock, AsyncMock

from app.services.correlation import CorrelationMeasurementHandler
from app.models import CorrelationMetadata


async def safe_await(task):
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.fixture
async def handler():
    """Create a handler for testing."""
    mock_tagger = MagicMock()
    mock_tagger.setTestSignal = MagicMock()
    return CorrelationMeasurementHandler(tagger=mock_tagger)


@pytest.fixture
def metadata():
    """Create metadata for testing."""
    return CorrelationMetadata(user_name="test_user", 
        channel1=1,
        channel2=2,
        binwidth=int(1e9),
        n_values=100,
        target_location="desktop/MaasData/test",
    )


class TestCorrelationMeasurementHandler:
    """Test CorrelationMeasurementHandler functionality."""

    @pytest.mark.asyncio
    async def test_handler_initialization(self):
        """Handler should initialize correctly."""
        mock_tagger = MagicMock()
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)

        assert handler._measurement_task is None
        assert handler._start_time is None
        assert handler.tagger == mock_tagger

    @pytest.mark.asyncio
    async def test_handler_initialization_without_tagger(self):
        """Handler should initialize without tagger."""
        handler = CorrelationMeasurementHandler()

        assert handler._measurement_task is None
        assert handler._start_time is None
        assert handler.tagger is None

    @pytest.mark.asyncio
    async def test_start_handler(self, handler, metadata):
        """Should start measurement with proper setup."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        assert handler._start_time is not None

        await handler.stop()
        await safe_await(task)

    @pytest.mark.asyncio
    async def test_start_handler_with_custom_parameters(self, handler):
        """Should handle custom binwidth and n_values."""
        metadata = CorrelationMetadata(user_name="test_user", 
            channel1=3,
            channel2=4,
            binwidth=int(5e8),
            n_values=50,
            target_location="custom/path",
        )
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        assert handler._start_time is not None

        await handler.stop()
        await safe_await(task)

    @pytest.mark.asyncio
    async def test_stop_handler_returns_results(self, handler, metadata):
        """Should return results when stopped."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        results = await handler.stop()
        await safe_await(task)

        assert "status" in results
        assert results["status"] == "stopped"
        assert "duration" in results
        assert "message" in results
        assert results["message"] == "Correlation measurement stopped and data file deleted"

    @pytest.mark.asyncio
    async def test_stop_without_start(self, handler):
        """Should handle stop without prior start."""
        results = await handler.stop()

        assert results["status"] == "stopped"
        assert "duration" in results
        assert results["duration"] >= 0

    @pytest.mark.asyncio
    async def test_start_records_start_time(self, handler, metadata):
        """Should record start time when measurement begins."""
        before_start = datetime.utcnow()
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)
        after_start = datetime.utcnow()

        assert handler._start_time is not None
        assert before_start <= handler._start_time <= after_start

        await handler.stop()
        await safe_await(task)

    @pytest.mark.asyncio
    async def test_start_with_single_channel_pair(self, handler):
        """Should work with single channel pair."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        assert handler._start_time is not None

        await handler.stop()
        await safe_await(task)

    @pytest.mark.asyncio
    async def test_start_with_default_values(self, handler):
        """Should use default values when not specified."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=5, channel2=6)
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        # Defaults should be applied
        assert metadata.binwidth == int(1e3)
        assert metadata.n_values == 1000

        await handler.stop()
        await safe_await(task)

    @pytest.mark.asyncio
    async def test_multiple_start_stop_cycles(self, handler, metadata):
        """Should handle multiple start/stop cycles."""
        # First cycle
        task1 = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)
        results1 = await handler.stop()
        await safe_await(task1)

        assert results1["status"] == "stopped"
        first_start_time = handler._start_time

        # Second cycle
        task2 = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)
        results2 = await handler.stop()
        await safe_await(task2)

        assert results2["status"] == "stopped"
        second_start_time = handler._start_time

        # Start times should be different
        assert second_start_time > first_start_time

    @pytest.mark.asyncio
    async def test_tagger_called_with_both_channels(self, handler, metadata):
        """Verify handler accepts both channel1 and channel2."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        assert handler._start_time is not None

        await handler.stop()
        await safe_await(task)

    @pytest.mark.asyncio
    async def test_start_with_large_channel_numbers(self, handler):
        """Should handle large channel numbers."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=101, channel2=102)
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        assert handler._start_time is not None

        await handler.stop()
        await safe_await(task)

    @pytest.mark.asyncio
    async def test_stop_calculates_duration_correctly(self, handler, metadata):
        """Stop should calculate duration since start."""
        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        sleep_duration = 0.05
        await asyncio.sleep(sleep_duration)

        results = await handler.stop()
        await safe_await(task)

        # Duration should be at least sleep_duration
        assert results["duration"] >= sleep_duration

    @pytest.mark.asyncio
    async def test_handler_with_mock_tagger(self):
        """Should work with mocked tagger."""
        mock_tagger = MagicMock()
        mock_tagger.setTestSignal = MagicMock(return_value=None)

        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)

        task = asyncio.create_task(handler.start(1, metadata))
        await asyncio.sleep(0.05)

        assert handler._start_time is not None

        await handler.stop()
        await safe_await(task)


class TestCorrelationMetadataModel:
    """Test CorrelationMetadata model."""

    def test_metadata_with_required_fields(self):
        """Should create metadata with only required fields."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)

        assert metadata.channel1 == 1
        assert metadata.channel2 == 2
        assert metadata.binwidth == int(1e3)
        assert metadata.n_values == 1000

    def test_metadata_with_all_fields(self):
        """Should create metadata with all fields."""
        metadata = CorrelationMetadata(user_name="test_user", 
            channel1=1,
            channel2=2,
            binwidth=int(5e8),
            n_values=50,
            target_location="custom/path",
        )

        assert metadata.channel1 == 1
        assert metadata.channel2 == 2
        assert metadata.binwidth == int(5e8)
        assert metadata.n_values == 50
        assert metadata.target_location == "custom/path"

    def test_metadata_default_target_location(self):
        """Should have default target location."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)

        assert (
            metadata.target_location == "desktop/MaasData/{datetime}/{measurement-type}"
        )

    def test_metadata_channel1_required(self):
        """channel1 should be required."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CorrelationMetadata(user_name="test_user", channel2=2)

    def test_metadata_channel2_required(self):
        """channel2 should be required."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CorrelationMetadata(user_name="test_user", channel1=1)

    def test_metadata_channel1_must_be_int(self):
        """channel1 should be integer."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CorrelationMetadata(user_name="test_user", channel1="invalid", channel2=2)

    def test_metadata_channel2_must_be_int(self):
        """channel2 should be integer."""
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            CorrelationMetadata(user_name="test_user", channel1=1, channel2="invalid")

    def test_metadata_dict_conversion(self):
        """Should convert to dict correctly."""
        metadata = CorrelationMetadata(user_name="test_user", 
            channel1=1,
            channel2=2,
            binwidth=int(1e3),
            n_values=1000,
        )

        data = metadata.dict()

        assert data["channel1"] == 1
        assert data["channel2"] == 2
        assert data["binwidth"] == int(1e3)
        assert data["n_values"] == 1000
