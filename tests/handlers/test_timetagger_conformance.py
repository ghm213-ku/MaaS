"""Check MaaS against the real Swabian TimeTagger library, using a virtual tagger.

The rest of the suite replaces TimeTagger with mocks, which can't tell whether
MaaS calls the library the way the library actually behaves. These tests load
the real library (skipped when it isn't installed) and create a virtual Time
Tagger, so no hardware is needed.
"""

import asyncio
import importlib
import os
import sys
import time
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from pydantic import ValidationError

from app.models import (
    COINCIDENCE_TIMESTAMPS,
    CoincidencesMetadata,
    CorrelationMetadata,
    HistogramLiveMetadata,
    StartStopLiveMetadata,
)

_SWABIAN_MODULES = ("Swabian", "Swabian.TimeTagger", "TimeTagger")


@pytest.fixture
def real_tt():
    """Import the real TimeTagger module in place of the suite's global mocks."""
    saved = {name: sys.modules.pop(name) for name in _SWABIAN_MODULES if name in sys.modules}
    try:
        try:
            tt = importlib.import_module("Swabian.TimeTagger")
        except ImportError:
            pytest.skip("Swabian TimeTagger library is not installed")
        yield tt
    finally:
        for name in _SWABIAN_MODULES:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


@pytest.fixture
def tagger(real_tt, monkeypatch):
    # The virtual tagger's license lives in the real user profile, which the
    # suite's sandbox hides by pointing HOME/USERPROFILE at a scratch dir.
    appdata = os.environ.get("APPDATA")
    if appdata:
        profile = str(Path(appdata).parents[1])
        with monkeypatch.context() as m:
            m.setenv("USERPROFILE", profile)
            m.setenv("HOME", profile)
            tagger = _create_virtual(real_tt)
    else:
        tagger = _create_virtual(real_tt)
    yield tagger
    real_tt.freeTimeTagger(tagger)


def _create_virtual(real_tt):
    try:
        return real_tt.createTimeTaggerVirtual()
    except RuntimeError as e:
        pytest.skip(f"Virtual Time Tagger unavailable: {e}")


class TestCounterTotals:
    def test_summary_uses_total_counts_with_real_counter(self, real_tt, tagger):
        from app.handlers.counter_utils import counter_summary

        # A virtual tagger with no replay never advances time, so this checks
        # the shapes and types the real Counter returns, not real counts.
        counter = real_tt.Counter(tagger, [1, 2], binwidth=int(1e9), n_values=3)
        counter.startFor(int(1e9))

        summary = counter_summary(counter, int(1e9))
        counter.stop()

        # One count total per channel, as getDataTotalCounts returns them
        assert summary["counts_per_channel"] == [0, 0]
        assert summary["count"] == 0
        assert summary["integration_time_seconds"] >= 0
        assert np.asarray(counter.getData()).shape == (2, 3)


class TestSaveRawTags:
    @pytest.mark.parametrize("name", ["rawtest", "rawtest.ttbin", "rawtest.tags"])
    def test_stop_deletes_every_file_filewriter_wrote(self, real_tt, tagger, tmp_path, name):
        from app.handlers.save_raw_tags import SaveRawTagsMeasurementHandler, ttbin_files

        target = str(tmp_path / name)
        writer = real_tt.FileWriter(tagger, target, [1, 2])
        writer.startFor(int(1e10))
        time.sleep(0.2)
        writer.stop()

        written = ttbin_files(target)
        # FileWriter never writes the bare name; it writes <base>.ttbin and parts
        assert written, f"FileWriter wrote nothing for {name}"
        assert all(f.endswith(".ttbin") for f in written)
        # A file for a different measurement with a similar name is not touched
        other = tmp_path / "rawtest2.ttbin"
        other.write_bytes(b"x")

        handler = SaveRawTagsMeasurementHandler(tagger=tagger)
        handler._target_file_path = target
        asyncio.run(handler.stop())
        del writer

        assert ttbin_files(target) == []
        assert other.exists()


class TestCorrelation:
    def test_csv_has_time_axis_centred_on_zero(self, real_tt, tagger, tmp_path):
        from app.handlers.correlation import CorrelationMeasurementHandler

        out = tmp_path / "corr.csv"
        metadata = CorrelationMetadata(
            channel1=1, channel2=2, user_name="u", binwidth=10, n_bins=4,
            target_location=str(out),
        )
        assert metadata.n_values == 4

        handler = CorrelationMeasurementHandler(tagger=tagger)
        with patch("app.handlers.correlation.TimeTagger", real_tt):
            result = asyncio.run(handler.start(0.01, metadata))

        data = np.loadtxt(out, delimiter=",")
        np.testing.assert_array_equal(data[:, 0], [-20, -10, 0, 10])
        np.testing.assert_array_equal(data[:, 1], [0, 0, 0, 0])
        assert result["n_bins"] == 4
        assert result["total_counts"] == 0


class TestCoincidenceTimestamp:
    def test_every_accepted_name_exists_in_timetagger(self, real_tt):
        from app.handlers.coincidences import _resolve_timestamp

        with patch("app.handlers.coincidences.TimeTagger", real_tt):
            for name in COINCIDENCE_TIMESTAMPS:
                assert _resolve_timestamp(name) == getattr(real_tt.CoincidenceTimestamp, name)

    def test_unknown_timestamp_rejected_like_timetagger(self, real_tt, tagger):
        with pytest.raises(Exception):
            real_tt.Coincidences(tagger, [[1, 2]], 1000, 7)
        with pytest.raises(ValidationError):
            CoincidencesMetadata(user_name="u", coincidences=[[1, 2]], timestamp="Middle")

    def test_timestamp_is_case_insensitive(self):
        metadata = CoincidencesMetadata(user_name="u", coincidences=[[1, 2]], timestamp="listedfirst")
        assert metadata.timestamp == "ListedFirst"


class TestTimeHistogramParameters:
    def test_startstop_has_no_bin_count(self, real_tt):
        doc = real_tt.StartStop.__init__.__doc__ or ""
        assert "n_bins" not in doc
        assert "n_bins" not in StartStopLiveMetadata.model_fields

    def test_histogram_keeps_bin_count(self, real_tt):
        assert "n_bins" in (real_tt.Histogram.__init__.__doc__ or "")
        assert "n_bins" in HistogramLiveMetadata.model_fields
