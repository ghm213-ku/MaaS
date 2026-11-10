"""Tests for the shared request-model behaviour and the measurement-type registry."""

import pytest
from pydantic import ValidationError

from app.models import (
    REQUEST_MODELS,
    CountRateLiveMeasurementRequest,
    CountRateMeasurementRequest,
    CountRateMetadata,
    HistogramLiveMeasurementRequest,
    MeasurementType,
    SetParametersRequest,
    StartStopLiveMeasurementRequest,
    get_metadata_model,
)


class TestRegistry:
    def test_every_measurement_type_has_a_request_model(self):
        assert set(REQUEST_MODELS) == {t.value for t in MeasurementType}

    def test_get_metadata_model(self):
        assert get_metadata_model("count_rate") is CountRateMetadata

    def test_get_metadata_model_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown measurement type"):
            get_metadata_model("unknown_type")


class TestFlatPayload:
    """Metadata fields given at the top level are wrapped into "metadata"."""

    def test_flat_payload_is_wrapped(self):
        request = CountRateMeasurementRequest(
            user_name="test_user", channels=[1, 2], binwidth=500000000, n_values=10, duration_seconds=5
        )
        assert request.metadata.channels == [1, 2]
        assert request.metadata.binwidth == 500000000
        assert request.duration_seconds == 5
        assert request.measurement_type == MeasurementType.COUNT_RATE

    def test_flat_payload_defaults(self):
        request = CountRateMeasurementRequest(user_name="test_user", channels=[1])
        assert request.duration_seconds == 60
        assert request.metadata.binwidth == int(1e9)
        assert request.metadata.n_values == 1

    def test_flat_live_payload_has_no_duration_by_default(self):
        request = CountRateLiveMeasurementRequest(user_name="test_user", channels=[1])
        assert request.duration_seconds is None

    def test_flat_set_parameters_defaults_to_zero_duration(self):
        request = SetParametersRequest(user_name="test_user", channels=[1], input_delay=5)
        assert request.duration_seconds == 0

    def test_flat_payload_drops_duration_for_types_without_one(self):
        request = StartStopLiveMeasurementRequest(
            user_name="u", click_channel=1, start_channel=2, duration_seconds=10
        )
        assert "duration_seconds" not in request.model_dump()

    def test_flat_payload_does_not_modify_the_callers_dict(self):
        payload = {"user_name": "u", "channels": [1], "duration_seconds": 3}
        CountRateMeasurementRequest(**payload)
        CountRateMeasurementRequest.model_validate(payload)
        assert payload == {"user_name": "u", "channels": [1], "duration_seconds": 3}

    def test_invalid_metadata_raises(self):
        with pytest.raises(ValidationError):
            CountRateMeasurementRequest(channels="not_a_list")


class TestMetadataAttributes:
    """request.<field> reads request.metadata.<field>."""

    def test_reads_metadata_fields(self):
        request = CountRateMeasurementRequest(
            duration_seconds=1,
            metadata={"user_name": "u", "channels": [3], "target_location": "C:\\custom\\{datetime}.csv"},
        )
        assert request.user_name == "u"
        assert request.channels == [3]
        assert request.target_location == "C:\\custom\\{datetime}.csv"

    def test_unknown_attribute_raises(self):
        request = CountRateMeasurementRequest(duration_seconds=1, metadata={"user_name": "u", "channels": [3]})
        with pytest.raises(AttributeError):
            request.not_a_field

    def test_time_histogram_requests_use_both_channels(self):
        request = HistogramLiveMeasurementRequest(user_name="u", click_channel=4, start_channel=7)
        assert request.channels == [4, 7]
