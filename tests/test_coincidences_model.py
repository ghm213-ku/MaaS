"""Tests for CoincidencesMeasurementRequest model and payloads."""

import pytest
from pydantic import ValidationError

from app.models import (
    CoincidencesMeasurementRequest,
    CoincidencesMetadata,
    MeasurementType,
)


class TestCoincidencesMeasurementRequestModel:
    """Test CoincidencesMeasurementRequest model validation."""

    def test_model_creation_with_valid_metadata(self):
        """Should create valid CoincidencesMeasurementRequest."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            channels=[1, 2, 3],
            binwidth=1000000000,
            n_values=10,
            target_location="desktop/MaasData/test",
        )
        request = CoincidencesMeasurementRequest(
            measurement_type=MeasurementType.COINCIDENCES,
            duration_seconds=60,
            metadata=metadata,
        )

        assert request.measurement_type == MeasurementType.COINCIDENCES
        assert request.duration_seconds == 60
        assert request.channels == [1, 2, 3]
        assert request.user_name == "test_user"
        assert request.binwidth == 1000000000
        assert request.n_values == 10
        assert request.target_location == "desktop/MaasData/test"

    def test_model_default_measurement_type(self):
        """Should default to COINCIDENCES measurement type."""
        metadata = CoincidencesMetadata(user_name="test_user", channels=[1, 2, 3])
        request = CoincidencesMeasurementRequest(duration_seconds=60, metadata=metadata)

        assert request.measurement_type == MeasurementType.COINCIDENCES

    def test_model_requires_duration_seconds(self):
        """Should require duration_seconds field."""
        metadata = CoincidencesMetadata(user_name="test_user", channels=[1, 2, 3])
        
        with pytest.raises(ValidationError):
            CoincidencesMeasurementRequest(metadata=metadata)

    def test_model_requires_metadata(self):
        """Should require metadata field."""
        with pytest.raises(ValidationError):
            CoincidencesMeasurementRequest(duration_seconds=60)

    def test_wrap_flat_payload(self):
        """Should wrap flat dictionary payload into correct structure."""
        flat_payload = {
            "duration_seconds": 60,
            "measurement_type": MeasurementType.COINCIDENCES,
            "user_name": "test_user",
            "channels": [1, 2, 3],
            "binwidth": 1000000000,
            "n_values": 10,
            "target_location": "desktop/MaasData/test",
        }
        
        request = CoincidencesMeasurementRequest.model_validate(flat_payload)
        
        assert request.measurement_type == MeasurementType.COINCIDENCES
        assert request.duration_seconds == 60
        assert request.user_name == "test_user"
        assert request.channels == [1, 2, 3]
        assert request.binwidth == 1000000000
        assert request.n_values == 10
        assert request.target_location == "desktop/MaasData/test"

class TestCoincidencesMetadata:
    """Test CoincidencesMetadata validation."""

    def test_valid_metadata(self):
        """Should allow valid metadata creation."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            channels=[1, 2, 3],
            binwidth=1000000000,
            n_values=10,
            target_location="desktop/MaasData/test",
        )
        assert metadata.channels == [1, 2, 3]
        assert metadata.binwidth == 1000000000
        assert metadata.n_values == 10
        assert metadata.target_location == "desktop/MaasData/test"

    def test_missing_required_fields(self):
        """Should raise ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            CoincidencesMetadata(channels=[1, 2, 3])

        with pytest.raises(ValidationError):
            CoincidencesMetadata(user_name="test_user")

    def test_default_fields(self):
        """Should set default fields correctly."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            channels=[1, 2, 3],
        )
        assert metadata.binwidth == int(1e9)
        assert metadata.n_values == 1
        assert metadata.target_location == "desktop/MaasData/{datetime}/{measurement-type}"

    def test_invalid_types(self):
        """Should raise ValidationError for invalid field types."""
        with pytest.raises(ValidationError):
            CoincidencesMetadata(
                user_name="test_user",
                channels="not_a_list",
            )
        
        with pytest.raises(ValidationError):
            CoincidencesMetadata(
                user_name="test_user",
                channels=[1, 2, 3],
                binwidth="invalid",
            )
