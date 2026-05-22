"""Tests for payload definitions and JSON-to-class mapping."""

import pytest
from pydantic import BaseModel, ValidationError

from app.payloads import (
    MeasurementPayloadMapper,
    MeasurementPayloadSchemas,
    get_measurement_type_from_payload,
    validate_payload_for_type,
)
from app.models import CountRateMeasurementRequest, MeasurementType


class TestMeasurementPayloadSchemas:
    """Test payload schema definitions."""

    def test_count_rate_schema_exists(self):
        """Schema for count-rate measurement should exist."""
        assert "count_rate" in MeasurementPayloadSchemas.SCHEMAS
        schema = MeasurementPayloadSchemas.SCHEMAS["count_rate"]
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_count_rate_schema_has_example(self):
        """Count-rate schema should have a usage example."""
        schema = MeasurementPayloadSchemas.COUNT_RATE_SCHEMA
        assert "example" in schema
        example = schema["example"]
        assert "channels" in example
        assert example["channels"] == [1, 2, 3]


class TestMeasurementPayloadMapper:
    """Test payload mapper functionality."""

    def test_get_model_for_count_rate(self):
        """Should return CountRateMeasurementRequest for 'count_rate' type."""
        model_class = MeasurementPayloadMapper.get_model_for_type("count_rate")
        assert model_class == CountRateMeasurementRequest

    def test_get_model_for_unknown_type_raises_error(self):
        """Should raise ValueError for unknown measurement type."""
        with pytest.raises(ValueError, match="Unknown measurement type"):
            MeasurementPayloadMapper.get_model_for_type("unknown_type")

    def test_validate_and_parse_count_rate_valid(self):
        """Should successfully parse valid count-rate payload."""
        payload = {
            "channels": [1, 2, 3],
            "binwidth": 1000000000,
            "n_values": 1,
            "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
        }
        result = MeasurementPayloadMapper.validate_and_parse("count_rate", payload)

        assert isinstance(result, CountRateMeasurementRequest)
        assert result.channels == [1, 2, 3]
        assert result.binwidth == 1000000000
        assert result.n_values == 1

    def test_validate_and_parse_count_rate_minimal(self):
        """Should parse minimal valid count-rate payload (only channels required)."""
        payload = {"channels": [1]}
        result = MeasurementPayloadMapper.validate_and_parse("count_rate", payload)

        assert isinstance(result, CountRateMeasurementRequest)
        assert result.channels == [1]
        assert result.binwidth == int(1e9)  # default
        assert result.n_values == 1  # default

    def test_validate_and_parse_missing_measurement_type_ok(self):
        """Should handle payload with custom parameters."""
        # The new format requires channels as only mandatory field
        payload = {"channels": [1, 2], "binwidth": 500000000, "n_values": 10}
        result = MeasurementPayloadMapper.validate_and_parse("count_rate", payload)

        # Should succeed
        assert isinstance(result, CountRateMeasurementRequest)
        assert result.channels == [1, 2]
        assert result.binwidth == 500000000
        assert result.n_values == 10

    def test_validate_and_parse_invalid_duration(self):
        """Should raise ValidationError for invalid channels field."""
        payload = {
            "channels": "not_a_list",  # Should be list[int]
        }
        with pytest.raises(ValidationError):
            MeasurementPayloadMapper.validate_and_parse("count_rate", payload)

    def test_list_types(self):
        """Should return list of registered measurement types."""
        types = MeasurementPayloadMapper.list_types()
        assert "count_rate" in types
        assert isinstance(types, list)

    def test_register_model(self):
        """Should allow registering new measurement types."""

        class CustomMeasurementRequest(BaseModel):
            measurement_type: str
            custom_param: str

        # Register a new type
        MeasurementPayloadMapper.register_model("custom", CustomMeasurementRequest)

        # Verify it was registered
        model_class = MeasurementPayloadMapper.get_model_for_type("custom")
        assert model_class == CustomMeasurementRequest
        assert "custom" in MeasurementPayloadMapper.list_types()

    def test_get_schema_count_rate(self):
        """Should return schema for count-rate measurement."""
        schema = MeasurementPayloadMapper.get_schema("count_rate")
        assert schema["type"] == "object"
        assert "properties" in schema

    def test_get_schema_unknown_type(self):
        """Should raise ValueError for unknown type."""
        with pytest.raises(ValueError, match="Schema not found"):
            MeasurementPayloadMapper.get_schema("unknown")

    def test_get_all_schemas(self):
        """Should return all schemas."""
        schemas = MeasurementPayloadMapper.get_all_schemas()
        assert "count_rate" in schemas
        assert isinstance(schemas, dict)


class TestPayloadHelpers:
    """Test helper functions."""

    def test_get_measurement_type_from_payload_valid(self):
        """Should extract measurement type from payload."""
        payload = {"measurement_type": "count_rate", "duration_seconds": 60}
        mtype = get_measurement_type_from_payload(payload)
        assert mtype == "count_rate"

    def test_get_measurement_type_from_payload_missing(self):
        """Should raise ValueError if measurement_type is missing."""
        payload = {"duration_seconds": 60}
        with pytest.raises(ValueError, match="measurement_type"):
            get_measurement_type_from_payload(payload)

    def test_validate_payload_for_type_valid(self):
        """Should validate payload for type."""
        payload = {
            "channels": [1, 2],
            "binwidth": 1000000000,
            "n_values": 1,
            "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
        }
        result = validate_payload_for_type("count_rate", payload)

        assert isinstance(result, CountRateMeasurementRequest)
        assert result.channels == [1, 2]

    def test_validate_payload_for_type_invalid_type(self):
        """Should raise ValueError for unknown type."""
        payload = {"measurement_type": "unknown"}
        with pytest.raises(ValueError, match="Unknown measurement type"):
            validate_payload_for_type("unknown", payload)

    def test_validate_payload_for_type_invalid_data(self):
        """Should raise ValidationError for invalid data."""
        payload = {
            "measurement_type": "count_rate",
            "duration_seconds": "invalid",
        }
        with pytest.raises(ValidationError):
            validate_payload_for_type("count_rate", payload)


class TestPayloadEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_empty_metadata(self):
        """Should handle multiple channels."""
        payload = {
            "channels": [1, 2, 3, 4, 5],
        }
        result = MeasurementPayloadMapper.validate_and_parse("count_rate", payload)
        assert result.channels == [1, 2, 3, 4, 5]

    def test_large_duration(self):
        """Should handle large binwidth values."""
        payload = {
            "channels": [1],
            "binwidth": 10000000000,  # Large binwidth
        }
        result = MeasurementPayloadMapper.validate_and_parse("count_rate", payload)
        assert result.binwidth == 10000000000

    def test_complex_metadata(self):
        """Should handle complex custom target paths."""
        payload = {
            "channels": [1, 2, 3],
            "binwidth": 1000000000,
            "n_values": 100,
            "target_location": "C:\\custom\\path\\measurement_{datetime}.csv",
        }
        result = MeasurementPayloadMapper.validate_and_parse("count_rate", payload)
        assert result.target_location == "C:\\custom\\path\\measurement_{datetime}.csv"
