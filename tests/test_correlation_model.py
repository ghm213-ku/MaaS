"""Tests for CorrelationMeasurementRequest model and payloads."""

import pytest
from pydantic import ValidationError

from app.models import (
    CorrelationMeasurementRequest,
    CorrelationMetadata,
    MeasurementType,
)
from app.payloads import (
    MeasurementPayloadMapper,
    MeasurementPayloadSchemas,
)


class TestCorrelationMeasurementRequestModel:
    """Test CorrelationMeasurementRequest model validation."""

    def test_model_creation_with_valid_metadata(self):
        """Should create valid CorrelationMeasurementRequest."""
        metadata = CorrelationMetadata(
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
        metadata = CorrelationMetadata(channel1=1, channel2=2)
        request = CorrelationMeasurementRequest(duration_seconds=60, metadata=metadata)

        assert request.measurement_type == MeasurementType.CORRELATION

    def test_model_requires_duration_seconds(self):
        """Should require duration_seconds field."""
        metadata = CorrelationMetadata(channel1=1, channel2=2)

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
        metadata = CorrelationMetadata(channel1=1, channel2=2)
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
        metadata = CorrelationMetadata(
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
        metadata = CorrelationMetadata(channel1=1, channel2=2)

        with pytest.raises(ValidationError):
            CorrelationMeasurementRequest(duration_seconds="not_int", metadata=metadata)

    def test_model_with_minimal_metadata(self):
        """Should work with minimal metadata (only required fields)."""
        metadata = CorrelationMetadata(channel1=1, channel2=2)
        request = CorrelationMeasurementRequest(duration_seconds=30, metadata=metadata)

        assert request.duration_seconds == 30
        assert request.metadata.channel1 == 1
        assert request.metadata.channel2 == 2
        assert request.metadata.binwidth == int(1e9)  # default
        assert request.metadata.n_values == 100  # default


class TestCorrelationPayloadSchema:
    """Test correlation measurement payload schema."""

    def test_correlation_schema_exists(self):
        """Schema for correlation measurement should exist."""
        assert "correlation" in MeasurementPayloadSchemas.SCHEMAS
        schema = MeasurementPayloadSchemas.SCHEMAS["correlation"]

        assert schema["type"] == "object"
        assert "properties" in schema

    def test_correlation_schema_has_required_fields(self):
        """Schema should specify required fields."""
        schema = MeasurementPayloadSchemas.SCHEMAS["correlation"]

        assert "required" in schema
        assert "channel1" in schema["required"]
        assert "channel2" in schema["required"]

    def test_correlation_schema_has_example(self):
        """Schema should have a usage example."""
        schema = MeasurementPayloadSchemas.SCHEMAS["correlation"]

        assert "example" in schema
        example = schema["example"]
        assert example["channel1"] == 1
        assert example["channel2"] == 2

    def test_correlation_schema_channel1_property(self):
        """Schema should define channel1 as integer."""
        schema = MeasurementPayloadSchemas.SCHEMAS["correlation"]

        assert "channel1" in schema["properties"]
        assert schema["properties"]["channel1"]["type"] == "integer"

    def test_correlation_schema_channel2_property(self):
        """Schema should define channel2 as integer."""
        schema = MeasurementPayloadSchemas.SCHEMAS["correlation"]

        assert "channel2" in schema["properties"]
        assert schema["properties"]["channel2"]["type"] == "integer"

    def test_correlation_schema_binwidth_property(self):
        """Schema should define binwidth as optional integer."""
        schema = MeasurementPayloadSchemas.SCHEMAS["correlation"]

        assert "binwidth" in schema["properties"]
        assert schema["properties"]["binwidth"]["type"] == "integer"

    def test_correlation_schema_n_values_property(self):
        """Schema should define n_values as optional integer."""
        schema = MeasurementPayloadSchemas.SCHEMAS["correlation"]

        assert "n_values" in schema["properties"]
        assert schema["properties"]["n_values"]["type"] == "integer"


class TestCorrelationPayloadMapper:
    """Test payload mapper for correlation measurements."""

    def test_mapper_get_model_for_correlation(self):
        """Should return CorrelationMeasurementRequest for 'correlation' type."""
        model_class = MeasurementPayloadMapper.get_model_for_type("correlation")

        assert model_class == CorrelationMeasurementRequest

    def test_mapper_validate_and_parse_correlation_valid(self):
        """Should parse valid correlation payload."""
        payload = {
            "channel1": 1,
            "channel2": 2,
            "binwidth": 1000000000,
            "n_values": 100,
            "target_location": "desktop/MaasData/test",
        }
        result = MeasurementPayloadMapper.validate_and_parse("correlation", payload)

        assert isinstance(result, CorrelationMetadata)
        assert result.channel1 == 1
        assert result.channel2 == 2

    def test_mapper_validate_and_parse_correlation_minimal(self):
        """Should parse minimal correlation payload (only channels required)."""
        payload = {"channel1": 1, "channel2": 2}
        result = MeasurementPayloadMapper.validate_and_parse("correlation", payload)

        assert isinstance(result, CorrelationMetadata)
        assert result.channel1 == 1
        assert result.channel2 == 2
        assert result.binwidth == int(1e9)  # default
        assert result.n_values == 100  # default

    def test_mapper_validate_and_parse_correlation_missing_channel1(self):
        """Should raise ValidationError if channel1 is missing."""
        payload = {"channel2": 2}

        with pytest.raises(ValidationError):
            MeasurementPayloadMapper.validate_and_parse("correlation", payload)

    def test_mapper_validate_and_parse_correlation_missing_channel2(self):
        """Should raise ValidationError if channel2 is missing."""
        payload = {"channel1": 1}

        with pytest.raises(ValidationError):
            MeasurementPayloadMapper.validate_and_parse("correlation", payload)

    def test_mapper_validate_and_parse_correlation_invalid_channel1_type(self):
        """Should raise ValidationError if channel1 is not an integer."""
        payload = {"channel1": "not_int", "channel2": 2}

        with pytest.raises(ValidationError):
            MeasurementPayloadMapper.validate_and_parse("correlation", payload)

    def test_mapper_validate_and_parse_correlation_invalid_channel2_type(self):
        """Should raise ValidationError if channel2 is not an integer."""
        payload = {"channel1": 1, "channel2": "not_int"}

        with pytest.raises(ValidationError):
            MeasurementPayloadMapper.validate_and_parse("correlation", payload)

    def test_mapper_correlation_type_in_list_types(self):
        """Correlation should be in list of registered types."""
        types = MeasurementPayloadMapper.list_types()

        assert "correlation" in types

    def test_mapper_get_schema_correlation(self):
        """Should return schema for correlation measurement."""
        schema = MeasurementPayloadMapper.get_schema("correlation")

        assert schema["type"] == "object"
        assert "properties" in schema
        assert "channel1" in schema["properties"]

    def test_mapper_all_schemas_includes_correlation(self):
        """All schemas should include correlation."""
        schemas = MeasurementPayloadMapper.get_all_schemas()

        assert "correlation" in schemas


class TestCorrelationMeasurementTypeEnum:
    """Test MeasurementType enum includes correlation."""

    def test_measurement_type_has_correlation(self):
        """MeasurementType should have CORRELATION value."""
        assert hasattr(MeasurementType, "CORRELATION")
        assert MeasurementType.CORRELATION.value == "correlation"

    def test_measurement_type_correlation_is_string_enum(self):
        """CORRELATION should be a string enum."""
        assert isinstance(MeasurementType.CORRELATION, str)
        assert str(MeasurementType.CORRELATION) == "correlation"
