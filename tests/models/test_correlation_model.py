"""Tests for CorrelationMeasurementRequest model and payloads."""

import pytest
from pydantic import ValidationError

from app.models import (
    CorrelationMeasurementRequest,
    CorrelationMetadata,
    MeasurementType,
    REQUEST_MODELS,
)


class TestCorrelationMeasurementRequestModel:
    """Test CorrelationMeasurementRequest model validation."""

    def test_model_creation_with_valid_metadata(self):
        """Should create valid CorrelationMeasurementRequest."""
        metadata = CorrelationMetadata(user_name="test_user", 
            channel1=1,
            channel2=2,
            binwidth=int(1e9),
            n_values=100,
            target_location="desktop/MaasData/test",
        )
        request = CorrelationMeasurementRequest(
            measurement_type=MeasurementType.CORRELATION,
            duration_seconds=60,
            metadata=metadata,
        )

        assert request.measurement_type == MeasurementType.CORRELATION
        assert request.duration_seconds == 60
        assert request.metadata.channel1 == 1
        assert request.metadata.channel2 == 2

    def test_model_default_measurement_type(self):
        """Should default to CORRELATION measurement type."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)
        request = CorrelationMeasurementRequest(duration_seconds=60, metadata=metadata)

        assert request.measurement_type == MeasurementType.CORRELATION

    def test_model_requires_duration_seconds(self):
        """Should require duration_seconds field."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)

        with pytest.raises(ValidationError) as exc_info:
            CorrelationMeasurementRequest(metadata=metadata)

        assert "duration_seconds" in str(exc_info.value)

    def test_model_requires_metadata(self):
        """Should require metadata field."""
        with pytest.raises(ValidationError) as exc_info:
            CorrelationMeasurementRequest(duration_seconds=60)

        assert "metadata" in str(exc_info.value)

    def test_model_dict_serialization(self):
        """Should serialize to dictionary correctly."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)
        request = CorrelationMeasurementRequest(duration_seconds=60, metadata=metadata)

        request_dict = request.dict()
        assert request_dict["measurement_type"] == "correlation"
        assert request_dict["duration_seconds"] == 60
        assert request_dict["metadata"]["channel1"] == 1
        assert request_dict["metadata"]["channel2"] == 2

    def test_model_json_schema(self):
        """Should have valid JSON schema."""
        schema = CorrelationMeasurementRequest.model_json_schema()

        assert "properties" in schema
        assert "duration_seconds" in schema["properties"]
        assert "metadata" in schema["properties"]

    def test_model_with_custom_parameters(self):
        """Should accept custom binwidth and n_values."""
        metadata = CorrelationMetadata(user_name="test_user", 
            channel1=3,
            channel2=4,
            binwidth=int(5e8),
            n_values=50,
            target_location="custom/path",
        )
        request = CorrelationMeasurementRequest(duration_seconds=120, metadata=metadata)

        assert request.metadata.channel1 == 3
        assert request.metadata.channel2 == 4
        assert request.metadata.binwidth == int(5e8)
        assert request.metadata.n_values == 50

    def test_model_duration_seconds_must_be_int(self):
        """duration_seconds should be integer."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)

        with pytest.raises(ValidationError):
            CorrelationMeasurementRequest(duration_seconds="not_int", metadata=metadata)

    def test_model_with_minimal_metadata(self):
        """Should work with minimal metadata (only required fields)."""
        metadata = CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)
        request = CorrelationMeasurementRequest(duration_seconds=30, metadata=metadata)

        assert request.duration_seconds == 30
        assert request.metadata.channel1 == 1
        assert request.metadata.channel2 == 2
        assert request.metadata.binwidth == int(1e3)  # default (1000 ps)
        assert request.metadata.n_values == 1000  # default (1000 bins)


class TestCorrelationFlatPayload:
    """Correlation requests given as a flat payload."""

    def test_mapper_get_model_for_correlation(self):
        """Should return CorrelationMeasurementRequest for 'correlation' type."""
        model_class = REQUEST_MODELS["correlation"]

        assert model_class == CorrelationMeasurementRequest

    def test_mapper_validate_and_parse_correlation_valid(self):
        """Should parse valid correlation payload."""
        payload = {
            "user_name": "test_user", "channel1": 1,
            "channel2": 2,
            "binwidth": 1000000000,
            "n_values": 100,
            "target_location": "desktop/MaasData/test",
        }
        result = CorrelationMeasurementRequest(**payload)

        assert isinstance(result, CorrelationMeasurementRequest)
        assert result.channel1 == 1
        assert result.channel2 == 2

    def test_mapper_validate_and_parse_correlation_minimal(self):
        """Should parse minimal correlation payload (only channels required)."""
        payload = {"user_name": "test_user", "channel1": 1, "channel2": 2}
        result = CorrelationMeasurementRequest(**payload)

        assert isinstance(result, CorrelationMeasurementRequest)
        assert result.channel1 == 1
        assert result.channel2 == 2
        assert result.binwidth == int(1e3)  # default
        assert result.n_values == 1000  # default

    def test_mapper_validate_and_parse_correlation_missing_channel1(self):
        """Should raise ValidationError if channel1 is missing."""
        payload = {"channel2": 2}

        with pytest.raises(ValidationError):
            CorrelationMeasurementRequest(**payload)

    def test_mapper_validate_and_parse_correlation_missing_channel2(self):
        """Should raise ValidationError if channel2 is missing."""
        payload = {"user_name": "test_user", "channel1": 1}

        with pytest.raises(ValidationError):
            CorrelationMeasurementRequest(**payload)

    def test_mapper_validate_and_parse_correlation_invalid_channel1_type(self):
        """Should raise ValidationError if channel1 is not an integer."""
        payload = {"channel1": "not_int", "channel2": 2}

        with pytest.raises(ValidationError):
            CorrelationMeasurementRequest(**payload)

    def test_mapper_validate_and_parse_correlation_invalid_channel2_type(self):
        """Should raise ValidationError if channel2 is not an integer."""
        payload = {"user_name": "test_user", "channel1": 1, "channel2": "not_int"}

        with pytest.raises(ValidationError):
            CorrelationMeasurementRequest(**payload)

class TestCorrelationMeasurementTypeEnum:
    """Test MeasurementType enum includes correlation."""

    def test_measurement_type_has_correlation(self):
        """MeasurementType should have CORRELATION value."""
        assert hasattr(MeasurementType, "CORRELATION")
        assert MeasurementType.CORRELATION.value == "correlation"

    def test_measurement_type_correlation_is_string_enum(self):
        """CORRELATION should be a string enum."""
        assert isinstance(MeasurementType.CORRELATION, str)
        assert MeasurementType.CORRELATION == "correlation"
