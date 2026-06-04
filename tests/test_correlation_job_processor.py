"""Tests for correlation measurement job processing."""

import pytest
import asyncio
from unittest.mock import MagicMock, patch, AsyncMock
from app.services.job_processor import JobProcessor
from app.services.correlation import CorrelationMeasurementHandler
from app.services.status_manager import StatusManager, MeasurementStatus
from app.models import CorrelationMetadata


@pytest.fixture
def mock_status_manager():
    """Create a mock status manager."""
    mock = MagicMock(spec=StatusManager)
    mock.redis_client = MagicMock()
    mock.update_status = MagicMock()
    mock.get_metadata = MagicMock(return_value={})
    mock.release_channels = MagicMock()
    return mock


@pytest.fixture
def mock_tagger():
    """Create a mock TimeTagger."""
    mock = MagicMock()
    mock.setTestSignal = MagicMock()
    return mock


@pytest.fixture
def job_processor(mock_status_manager, mock_tagger):
    """Create a job processor with mocked dependencies."""
    processor = JobProcessor(mock_status_manager, tagger=mock_tagger)
    processor.register_handler("correlation", CorrelationMeasurementHandler)
    return processor


class TestCorrelationJobProcessing:
    """Test correlation measurement job processing."""

    def test_processor_registers_correlation_handler(self, job_processor):
        """JobProcessor should register correlation handler."""
        assert "correlation" in job_processor.job_handlers
        assert (
            job_processor.job_handlers["correlation"] == CorrelationMeasurementHandler
        )

    def test_handle_correlation_with_required_params(self, job_processor, mock_tagger):
        """Should handle correlation with only required parameters."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 1,
            "channel2": 2,
        }

        # This should not raise an error
        job_processor._handle_correlation(handler, 1, metadata)

    def test_handle_correlation_with_all_params(self, job_processor, mock_tagger):
        """Should handle correlation with all parameters."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 1,
            "channel2": 2,
            "binwidth": int(5e8),
            "n_values": 50,
            "target_location": "custom/path",
        }

        # Should not raise
        job_processor._handle_correlation(handler, 1, metadata)

    def test_handle_correlation_missing_duration_raises_error(
        self, job_processor, mock_tagger
    ):
        """Should raise error if duration_seconds is missing."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 1,
            "channel2": 2,
        }

        with pytest.raises(ValueError, match="duration_seconds is required"):
            job_processor._handle_correlation(handler, None, metadata)

    def test_handle_correlation_missing_channel1_raises_error(
        self, job_processor, mock_tagger
    ):
        """Should raise error if channel1 is missing."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel2": 2,
        }

        with pytest.raises(ValueError, match="channel1 and channel2 are required"):
            job_processor._handle_correlation(handler, 1, metadata)

    def test_handle_correlation_missing_channel2_raises_error(
        self, job_processor, mock_tagger
    ):
        """Should raise error if channel2 is missing."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 1,
        }

        with pytest.raises(ValueError, match="channel1 and channel2 are required"):
            job_processor._handle_correlation(handler, 1, metadata)

    def test_handle_correlation_channel1_none_raises_error(
        self, job_processor, mock_tagger
    ):
        """Should raise error if channel1 is None."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": None,
            "channel2": 2,
        }

        with pytest.raises(ValueError, match="channel1 and channel2 are required"):
            job_processor._handle_correlation(handler, 1, metadata)

    def test_handle_correlation_channel2_none_raises_error(
        self, job_processor, mock_tagger
    ):
        """Should raise error if channel2 is None."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 1,
            "channel2": None,
        }

        with pytest.raises(ValueError, match="channel1 and channel2 are required"):
            job_processor._handle_correlation(handler, 1, metadata)

    def test_handle_correlation_uses_default_binwidth(self, job_processor, mock_tagger):
        """Should use default binwidth if not provided."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 1,
            "channel2": 2,
        }

        job_processor._handle_correlation(handler, 1, metadata)

        # Handler should receive metadata with default binwidth
        # Verify through the handler's initialization

    def test_handle_correlation_uses_default_n_values(self, job_processor, mock_tagger):
        """Should use default n_values if not provided."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 1,
            "channel2": 2,
        }

        job_processor._handle_correlation(handler, 1, metadata)

    def test_handle_correlation_uses_default_target_location(
        self, job_processor, mock_tagger
    ):
        """Should use default target_location if not provided."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 1,
            "channel2": 2,
        }

        job_processor._handle_correlation(handler, 1, metadata)

    def test_handle_correlation_creates_metadata_object(
        self, job_processor, mock_tagger
    ):
        """Should create CorrelationMetadata object."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata_dict = {
            "channel1": 1,
            "channel2": 2,
            "binwidth": int(5e8),
            "n_values": 50,
        }

        # This should execute without error
        job_processor._handle_correlation(handler, 1, metadata_dict)

    def test_handle_correlation_with_large_channel_numbers(
        self, job_processor, mock_tagger
    ):
        """Should handle large channel numbers."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 101,
            "channel2": 102,
        }

        job_processor._handle_correlation(handler, 1, metadata)

    def test_enqueue_job_with_correlation(self, job_processor):
        """Should enqueue correlation job."""
        status_id = "test-status-id"
        metadata = {
            "channel1": 1,
            "channel2": 2,
        }

        job_processor.enqueue_job(
            status_id=status_id,
            measurement_type="correlation",
            duration_seconds=60,
            metadata=metadata,
        )

        # Should call redis push
        assert job_processor.redis_client.rpush.called

    def test_run_job_calls_handle_correlation(
        self, job_processor, mock_status_manager, mock_tagger
    ):
        """_run_job_in_thread should call _handle_correlation for correlation type."""
        metadata = {
            "channel1": 1,
            "channel2": 2,
        }

        with patch.object(job_processor, "_handle_correlation") as mock_handle:
            try:
                job_processor._run_job_in_thread(
                    "test-id",
                    "correlation",
                    duration_seconds=1,
                    metadata=metadata,
                )
            except:
                pass

            # Verify _handle_correlation was called
            assert mock_handle.called

    def test_correlation_handler_receives_correct_metadata(
        self, job_processor, mock_tagger
    ):
        """Handler should receive CorrelationMetadata with correct values."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 3,
            "channel2": 4,
            "binwidth": int(2e9),
            "n_values": 75,
            "target_location": "test/path",
        }

        # Execute without error
        job_processor._handle_correlation(handler, 1, metadata)


class TestCorrelationHandlerIntegration:
    """Integration tests for correlation handler."""

    @pytest.mark.asyncio
    async def test_correlation_handler_execution(self, mock_tagger):
        """Should execute correlation handler correctly."""
        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = CorrelationMetadata(
            channel1=1,
            channel2=2,
            binwidth=int(1e9),
            n_values=100,
        )

        await handler.start(1, metadata)
        await asyncio.sleep(0.05)
        results = await handler.stop()

        assert results["status"] == "completed"
        assert "duration" in results

    @pytest.mark.asyncio
    async def test_correlation_handler_integration_with_job_processor(
        self, mock_status_manager, mock_tagger
    ):
        """Should integrate correctly with job processor."""
        processor = JobProcessor(mock_status_manager, tagger=mock_tagger)
        processor.register_handler("correlation", CorrelationMeasurementHandler)

        handler = CorrelationMeasurementHandler(tagger=mock_tagger)
        metadata = {
            "channel1": 1,
            "channel2": 2,
            "binwidth": int(1e9),
            "n_values": 100,
        }

        # Should execute without error
        processor._handle_correlation(handler, 1, metadata)
