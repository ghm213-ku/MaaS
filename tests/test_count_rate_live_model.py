"""Tests for CountRateLiveMeasurementRequest model and payloads."""

import pytest
from pydantic import ValidationError

from app.models import (
    CountRateLiveMeasurementRequest,
    CountRateMetadata,
    MeasurementType,
)


class TestCountRateLiveMeasurementRequestModel:
    """Test CountRateLiveMeasurementRequest model validation."""

    def test_model_creation_with_valid_metadata(self):
        """Should create valid CountRateLiveMeasurementRequest."""
        metadata = CountRateMetadata(
            user_name="test_user",
            channels=[1, 2],
            binwidth=1000000000,
            n_values=10,
            refresh_rate=50,
        )
        request = CountRateLiveMeasurementRequest(
            measurement_type=MeasurementType.COUNT_RATE_LIVE,
            duration_seconds=60,
            metadata=metadata,
        )

        assert request.measurement_type == MeasurementType.COUNT_RATE_LIVE
        assert request.duration_seconds == 60
        assert request.channels == [1, 2]
        assert request.user_name == "test_user"
        assert request.binwidth == 1000000000
        assert request.n_values == 10
        assert request.metadata.refresh_rate == 50

    def test_model_default_measurement_type(self):
        """Should default to COUNT_RATE_LIVE measurement type."""
        metadata = CountRateMetadata(user_name="test_user", channels=[1, 2])
        request = CountRateLiveMeasurementRequest(duration_seconds=60, metadata=metadata)

        assert request.measurement_type == MeasurementType.COUNT_RATE_LIVE

    def test_model_requires_duration_seconds(self):
        """Should require duration_seconds field."""
        metadata = CountRateMetadata(user_name="test_user", channels=[1, 2])
        
        with pytest.raises(ValidationError):
            CountRateLiveMeasurementRequest(metadata=metadata)

    def test_model_requires_metadata(self):
        """Should require metadata field."""
        with pytest.raises(ValidationError):
            CountRateLiveMeasurementRequest(duration_seconds=60)

    def test_wrap_flat_payload(self):
        """Should wrap flat dictionary payload into correct structure."""
        flat_payload = {
            "duration_seconds": 60,
            "measurement_type": MeasurementType.COUNT_RATE_LIVE,
            "user_name": "test_user",
            "channels": [1, 2],
            "binwidth": 1000000000,
            "n_values": 10,
            "refresh_rate": 50,
        }
        
        request = CountRateLiveMeasurementRequest.model_validate(flat_payload)
        
        assert request.measurement_type == MeasurementType.COUNT_RATE_LIVE
        assert request.duration_seconds == 60
        assert request.user_name == "test_user"
        assert request.channels == [1, 2]
        assert request.binwidth == 1000000000
        assert request.n_values == 10
        assert request.metadata.refresh_rate == 50
