"""Tests for the Coincidences Measurement Handler."""

import pytest
import asyncio
import numpy as np
from unittest.mock import MagicMock, patch
from app.services.coincidences import CoincidencesMeasurementHandler
from app.models import CoincidencesMetadata


@pytest.fixture
def mock_tagger():
    """Create a mock TimeTagger."""
    return MagicMock()


@pytest.fixture
def mock_tt():
    """Patch the TimeTagger module used by the coincidences handlers.

    Coincidences creates one virtual channel per group (20, 21, ...) and the
    Counter returns one row of n_values bins per virtual channel.
    """
    tt = MagicMock()
    tt.Coincidences.return_value.getChannels.return_value = [20, 21]
    tt.Counter.return_value.getData.return_value = [[1, 2, 3], [4, 5, 6]]
    # Totals over the whole measurement differ from the sum of the buffered bins
    tt.Counter.return_value.getDataTotalCounts.return_value = [60, 150]
    tt.Counter.return_value.getCaptureDuration.return_value = 15000
    with patch("app.services.coincidences.TimeTagger", tt):
        yield tt


class TestCoincidencesMeasurementHandler:
    """Test coincidences measurement handler."""

    @pytest.mark.asyncio
    async def test_start_and_stop_coincidences(self, mock_tagger, mock_tt):
        """Should initialize and stop gracefully."""
        handler = CoincidencesMeasurementHandler(tagger=mock_tagger)
        metadata = CoincidencesMetadata(user_name="test_user",
            coincidenceWindow=1000,
            coincidences=[[1, 2]]
        )

        task = asyncio.create_task(handler.start(10, metadata))
        await asyncio.sleep(0.05)

        results = await handler.stop()
        await asyncio.wait_for(task, timeout=1.0)

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

    @pytest.mark.asyncio
    async def test_passes_all_parameters_to_timetagger(self, mock_tagger, mock_tt, tmp_path):
        """coincidences, window, timestamp, binwidth and n_values all reach the hardware."""
        handler = CoincidencesMeasurementHandler(tagger=mock_tagger)
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2], [2, 3, 5]],
            coincidence_window=2500,
            timestamp="First",
            binwidth=5000,
            n_values=3,
            target_location=str(tmp_path / "out.csv"),
        )

        result = await handler.start(0.01, metadata)

        mock_tt.Coincidences.assert_called_once_with(
            mock_tagger, [[1, 2], [2, 3, 5]], 2500, mock_tt.CoincidenceTimestamp.First
        )
        mock_tt.Counter.assert_called_once_with(
            tagger=mock_tagger, channels=[20, 21], binwidth=5000, n_values=3
        )
        mock_tt.Counter.return_value.startFor.assert_called_once_with(int(0.01 * 1e12))
        assert result["status"] == "completed"
        # count comes from getDataTotalCounts, not from summing getData's bins
        assert result["count"] == 210
        assert result["counts_per_group"] == [60, 150]
        # 15000 ps captured / 5000 ps bins = 3 completed bins = 15 ns
        assert result["integration_time_seconds"] == pytest.approx(15000e-12)
        assert result["count_rate_cps_per_group"] == pytest.approx([60 / 15e-9, 150 / 15e-9])
        np.testing.assert_array_equal(
            np.loadtxt(tmp_path / "out.csv", delimiter=","), [[1, 2, 3], [4, 5, 6]]
        )

    @pytest.mark.asyncio
    async def test_hardware_setup_error_propagates(self, mock_tagger, mock_tt, tmp_path):
        """A failed Coincidences/Counter setup must fail the job, not report completed."""
        mock_tt.Coincidences.side_effect = RuntimeError("channel not available")
        handler = CoincidencesMeasurementHandler(tagger=mock_tagger)
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2]],
            target_location=str(tmp_path / "out.csv"),
        )

        with pytest.raises(RuntimeError, match="channel not available"):
            await handler.start(0.01, metadata)
        assert not (tmp_path / "out.csv").exists()
