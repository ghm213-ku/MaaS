"""Tests for SetParametersRequest model and payloads."""

import pytest
from pydantic import ValidationError

from app.models import (
    SetParametersRequest,
    SetParametersMetadata,
    MeasurementType,
)


class TestSetParametersRequestModel:
    """Test SetParametersRequest model validation."""

    def test_model_creation_with_valid_metadata(self):
        """Should create valid SetParametersRequest."""
        metadata = SetParametersMetadata(
            user_name="test_user",
            channels=[1, 2],
            input_delay=1000,
            trigger_voltage=0.5,
        )
        request = SetParametersRequest(
            measurement_type=MeasurementType.SET_PARAMETERS,
            duration_seconds=0,
            metadata=metadata,
        )

        assert request.measurement_type == MeasurementType.SET_PARAMETERS
        assert request.duration_seconds == 0
        assert request.metadata.channels == [1, 2]
        assert request.metadata.input_delay == 1000
        assert request.metadata.trigger_voltage == 0.5

    def test_model_default_measurement_type(self):
        """Should default to SET_PARAMETERS measurement type."""
        metadata = SetParametersMetadata(user_name="test_user", channels=[1, 2])
        request = SetParametersRequest(duration_seconds=0, metadata=metadata)

        assert request.measurement_type == MeasurementType.SET_PARAMETERS

    def test_model_default_duration_seconds(self):
        """Should default to 0 duration_seconds."""
        metadata = SetParametersMetadata(user_name="test_user", channels=[1, 2])
        request = SetParametersRequest(metadata=metadata)
        
        assert request.duration_seconds == 0

    def test_model_requires_metadata(self):
        """Should require metadata field."""
        with pytest.raises(ValidationError):
            SetParametersRequest(duration_seconds=0)

    def test_wrap_flat_payload(self):
        """Should wrap flat dictionary payload into correct structure."""
        flat_payload = {
            "duration_seconds": 0,
            "measurement_type": MeasurementType.SET_PARAMETERS,
            "user_name": "test_user",
            "channels": [1, 2],
            "input_delay": 1000,
            "trigger_voltage": 0.5,
        }
        
        request = SetParametersRequest.model_validate(flat_payload)
        
        assert request.measurement_type == MeasurementType.SET_PARAMETERS
        assert request.duration_seconds == 0
        assert request.metadata.user_name == "test_user"
        assert request.metadata.channels == [1, 2]
        assert request.metadata.input_delay == 1000
        assert request.metadata.trigger_voltage == 0.5

class TestSetParametersMetadata:
    """Test SetParametersMetadata validation."""

    def test_valid_metadata(self):
        """Should allow valid metadata creation."""
        metadata = SetParametersMetadata(
            user_name="test_user",
            channels=[1, 2],
            input_delay=1000,
            trigger_voltage=0.5,
        )
        assert metadata.channels == [1, 2]
        assert metadata.input_delay == 1000
        assert metadata.trigger_voltage == 0.5

    def test_missing_required_fields(self):
        """Should raise ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            SetParametersMetadata(channels=[1, 2])

        with pytest.raises(ValidationError):
            SetParametersMetadata(user_name="test_user")

    def test_optional_fields(self):
        """Should allow optional fields to be omitted."""
        metadata = SetParametersMetadata(
            user_name="test_user",
            channels=[1, 2],
        )
        assert metadata.input_delay is None
        assert metadata.trigger_voltage is None

    def test_invalid_types(self):
        """Should raise ValidationError for invalid field types."""
        with pytest.raises(ValidationError):
            SetParametersMetadata(
                user_name="test_user",
                channels="not_a_list",
            )
        
        with pytest.raises(ValidationError):
            SetParametersMetadata(
                user_name="test_user",
                channels=[1, 2],
                input_delay="invalid",
            )
