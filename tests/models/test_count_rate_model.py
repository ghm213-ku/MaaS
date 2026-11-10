"""Tests for CountRateMeasurementRequest model and payloads."""

import pytest
from pydantic import ValidationError

from app.models import (
    CountRateMeasurementRequest,
    CountRateMetadata,
    MeasurementType,
)


class TestCountRateMeasurementRequestModel:
    """Test CountRateMeasurementRequest model validation."""

    def test_model_creation_with_valid_metadata(self):
        """Should create valid CountRateMeasurementRequest."""
        metadata = CountRateMetadata(
            user_name="test_user",
            channels=[1, 2],
            binwidth=1000000000,
            n_values=10,
            target_location="desktop/MaasData/test",
        )
        request = CountRateMeasurementRequest(
            measurement_type=MeasurementType.COUNT_RATE,
            duration_seconds=60,
            metadata=metadata,
        )

        assert request.measurement_type == MeasurementType.COUNT_RATE
        assert request.duration_seconds == 60
        assert request.channels == [1, 2]
        assert request.user_name == "test_user"
        assert request.binwidth == 1000000000
        assert request.n_values == 10
        assert request.target_location == "desktop/MaasData/test"

    def test_model_default_measurement_type(self):
        """Should default to COUNT_RATE measurement type."""
        metadata = CountRateMetadata(user_name="test_user", channels=[1, 2])
        request = CountRateMeasurementRequest(duration_seconds=60, metadata=metadata)

        assert request.measurement_type == MeasurementType.COUNT_RATE

    def test_model_requires_duration_seconds(self):
        """Should require duration_seconds field."""
        metadata = CountRateMetadata(user_name="test_user", channels=[1, 2])
        
        with pytest.raises(ValidationError):
            CountRateMeasurementRequest(metadata=metadata)

    def test_model_requires_metadata(self):
        """Should require metadata field."""
        with pytest.raises(ValidationError):
            CountRateMeasurementRequest(duration_seconds=60)

    def test_wrap_flat_payload(self):
        """Should wrap flat dictionary payload into correct structure."""
        flat_payload = {
            "duration_seconds": 60,
            "measurement_type": MeasurementType.COUNT_RATE,
            "user_name": "test_user",
            "channels": [1, 2],
            "binwidth": 1000000000,
            "n_values": 10,
            "target_location": "desktop/MaasData/test",
        }
        
        request = CountRateMeasurementRequest.model_validate(flat_payload)
        
        assert request.measurement_type == MeasurementType.COUNT_RATE
        assert request.duration_seconds == 60
        assert request.user_name == "test_user"
        assert request.channels == [1, 2]
        assert request.binwidth == 1000000000
        assert request.n_values == 10
        assert request.target_location == "desktop/MaasData/test"

class TestCountRateMetadata:
    """Test CountRateMetadata validation."""

    def test_valid_metadata(self):
        """Should allow valid metadata creation."""
        metadata = CountRateMetadata(
            user_name="test_user",
            channels=[1, 2],
            binwidth=1000000000,
            n_values=10,
            target_location="desktop/MaasData/test",
            refresh_rate=50,
        )
        assert metadata.channels == [1, 2]
        assert metadata.binwidth == 1000000000
        assert metadata.n_values == 10
        assert metadata.target_location == "desktop/MaasData/test"
        assert metadata.refresh_rate == 50

    def test_missing_required_fields(self):
        """Should raise ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            CountRateMetadata(channels=[1, 2])

        with pytest.raises(ValidationError):
            CountRateMetadata(user_name="test_user")

    def test_default_fields(self):
        """Should set default fields correctly."""
        metadata = CountRateMetadata(
            user_name="test_user",
            channels=[1, 2],
        )
        assert metadata.binwidth == int(1e9)
        assert metadata.n_values == 1
        assert metadata.target_location == "~/Desktop/MaasData/{datetime}/{measurement-type}"
        assert metadata.refresh_rate == 25

    def test_invalid_types(self):
        """Should raise ValidationError for invalid field types."""
        with pytest.raises(ValidationError):
            CountRateMetadata(
                user_name="test_user",
                channels="not_a_list",
            )
        
        with pytest.raises(ValidationError):
            CountRateMetadata(
                user_name="test_user",
                channels=[1, 2],
                binwidth="invalid",
            )
