"""Tests for CoincidencesMeasurementRequest model and payloads."""

import pytest
from pydantic import ValidationError

from app.models import (
    CoincidencesMeasurementRequest,
    CoincidencesLiveMeasurementRequest,
    CoincidencesMetadata,
    MeasurementType,
)


class TestCoincidencesMeasurementRequestModel:
    """Test CoincidencesMeasurementRequest model validation."""

    def test_model_creation_with_valid_metadata(self):
        """Should create valid CoincidencesMeasurementRequest."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2, 3]],
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
        assert request.channels == [[1, 2, 3]]
        assert request.coincidences == [[1, 2, 3]]
        assert request.user_name == "test_user"
        assert request.binwidth == 1000000000
        assert request.n_values == 10
        assert request.target_location == "desktop/MaasData/test"

    def test_model_default_measurement_type(self):
        """Should default to COINCIDENCES measurement type."""
        metadata = CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2, 3]])
        request = CoincidencesMeasurementRequest(duration_seconds=60, metadata=metadata)

        assert request.measurement_type == MeasurementType.COINCIDENCES

    def test_model_requires_duration_seconds(self):
        """Should require duration_seconds field."""
        metadata = CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2, 3]])
        
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
            "coincidences": [[1, 2, 3]],
            "binwidth": 1000000000,
            "n_values": 10,
            "target_location": "desktop/MaasData/test",
        }
        
        request = CoincidencesMeasurementRequest.model_validate(flat_payload)
        
        assert request.measurement_type == MeasurementType.COINCIDENCES
        assert request.duration_seconds == 60
        assert request.user_name == "test_user"
        assert request.channels == [[1, 2, 3]]
        assert request.coincidences == [[1, 2, 3]]
        assert request.binwidth == 1000000000
        assert request.n_values == 10
        assert request.target_location == "desktop/MaasData/test"

class TestCoincidencesMetadata:
    """Test CoincidencesMetadata validation."""

    def test_valid_metadata(self):
        """Should allow valid metadata creation with list of lists."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2, 3]],
            binwidth=1000000000,
            n_values=10,
            target_location="desktop/MaasData/test",
        )
        assert metadata.coincidences == [[1, 2, 3]]
        assert metadata.channels == [[1, 2, 3]]
        assert metadata.binwidth == 1000000000
        assert metadata.n_values == 10
        assert metadata.target_location == "desktop/MaasData/test"

    def test_missing_required_fields(self):
        """Should raise ValidationError when required fields are missing."""
        with pytest.raises(ValidationError):
            CoincidencesMetadata(coincidences=[[1, 2, 3]])

        with pytest.raises(ValidationError):
            CoincidencesMetadata(user_name="test_user")

    def test_default_fields(self):
        """Should set default fields correctly."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2, 3]],
        )
        assert metadata.binwidth == int(1e9)
        assert metadata.n_values == 1
        assert metadata.target_location == "desktop/MaasData/{datetime}/{measurement-type}"

    def test_simple_channel_list_deprecated_and_rejected(self):
        """Should reject simple 1D channel lists since they are deprecated."""
        with pytest.raises(ValidationError) as exc_info:
            CoincidencesMetadata(
                user_name="test_user",
                channels=[1, 2, 3],
            )
        assert "Simple 1D channel lists for coincidence are deprecated" in str(exc_info.value)

        with pytest.raises(ValidationError) as exc_info:
            CoincidencesMetadata(
                user_name="test_user",
                coincidences=[1, 2],
            )
        assert "Simple 1D channel lists for coincidence are deprecated" in str(exc_info.value)

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
                coincidences=[[1, 2, 3]],
                binwidth="invalid",
            )


class TestCoincidencesLiveMeasurementRequestModel:
    """Test CoincidencesLiveMeasurementRequest model validation."""

    def test_model_creation_with_valid_metadata(self):
        """Should create valid CoincidencesLiveMeasurementRequest."""
        metadata = CoincidencesMetadata(
            user_name="test_user", 
            coincidences=[[1, 2, 3]]
        )
        request = CoincidencesLiveMeasurementRequest(
            measurement_type=MeasurementType.COINCIDENCES_LIVE,
            metadata=metadata
        )
        assert request.measurement_type == MeasurementType.COINCIDENCES_LIVE
        assert request.channels == [[1, 2, 3]]
        assert request.coincidences == [[1, 2, 3]]
        assert request.user_name == "test_user"

    def test_model_default_measurement_type(self):
        """Should default to COINCIDENCES_LIVE measurement type."""
        metadata = CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2, 3]])
        request = CoincidencesLiveMeasurementRequest(metadata=metadata)
        
        assert request.measurement_type == MeasurementType.COINCIDENCES_LIVE

    def test_model_requires_metadata(self):
        """Should raise ValidationError if metadata is missing."""
        with pytest.raises(ValidationError):
            CoincidencesLiveMeasurementRequest()

    def test_wrap_flat_payload(self):
        """Should handle flat payload dictionary."""
        flat_payload = {
            "measurement_type": MeasurementType.COINCIDENCES_LIVE,
            "user_name": "test_user",
            "coincidences": [[1, 2, 3]],
            "binwidth": 500000,
            "duration_seconds": 123, # should be dropped
        }
        
        request = CoincidencesLiveMeasurementRequest.model_validate(flat_payload)
        
        assert request.measurement_type == MeasurementType.COINCIDENCES_LIVE
        assert request.channels == [[1, 2, 3]]
        assert request.coincidences == [[1, 2, 3]]
        assert request.binwidth == 500000
        assert not hasattr(request, "duration_seconds")


class TestMultipleCoincidencesModel:
    """Test multiple coincidences input (list of lists of channel numbers)."""

    def test_metadata_with_coincidences_list_of_lists(self):
        """Should accept multiple coincidences via coincidences field."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2], [2, 3, 5]],
            coincidence_window=5000,
            timestamp="ListedFirst",
        )
        assert metadata.coincidences == [[1, 2], [2, 3, 5]]
        assert metadata.coincidence_groups == [[1, 2], [2, 3, 5]]
        assert metadata.channels == [[1, 2], [2, 3, 5]]
        assert metadata.unique_channels == [1, 2, 3, 5]
        assert metadata.coincidence_window == 5000
        assert metadata.timestamp == "ListedFirst"

    def test_metadata_with_channels_list_of_lists(self):
        """Should accept multiple coincidences via channels field as list of lists."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            channels=[[1, 2], [3, 4]],
        )
        assert metadata.coincidences == [[1, 2], [3, 4]]
        assert metadata.coincidence_groups == [[1, 2], [3, 4]]
        assert metadata.unique_channels == [1, 2, 3, 4]

    def test_metadata_with_coincidence_groups_field(self):
        """Should accept multiple coincidences via coincidence_groups (Swabian parameter name)."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidence_groups=[[1, 2], [2, 4]],
            coincidenceWindow=2000,
        )
        assert metadata.coincidences == [[1, 2], [2, 4]]
        assert metadata.coincidence_window == 2000

    def test_request_with_multiple_coincidences(self):
        """Request model should expose coincidences and unique_channels properties."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2], [2, 3, 5]],
        )
        request = CoincidencesMeasurementRequest(
            duration_seconds=30,
            metadata=metadata,
        )
        assert request.coincidences == [[1, 2], [2, 3, 5]]
        assert request.coincidence_groups == [[1, 2], [2, 3, 5]]
        assert request.unique_channels == [1, 2, 3, 5]
        assert request.duration_seconds == 30

    def test_flat_payload_with_multiple_coincidences(self):
        """Flat payload containing coincidences list of lists should validate."""
        flat_payload = {
            "duration_seconds": 60,
            "measurement_type": "coincidences",
            "user_name": "test_user",
            "coincidences": [[1, 2], [2, 3]],
            "coincidence_window": 1500,
        }
        request = CoincidencesMeasurementRequest.model_validate(flat_payload)
        assert request.coincidences == [[1, 2], [2, 3]]
        assert request.unique_channels == [1, 2, 3]
        assert request.coincidence_window == 1500

    def test_live_request_with_multiple_coincidences(self):
        """Live request should support multiple coincidences."""
        metadata = CoincidencesMetadata(
            user_name="test_user",
            coincidences=[[1, 2], [3, 4, 5]],
        )
        request = CoincidencesLiveMeasurementRequest(metadata=metadata)
        assert request.coincidences == [[1, 2], [3, 4, 5]]
        assert request.unique_channels == [1, 2, 3, 4, 5]

    def test_invalid_group_with_single_channel(self):
        """Should reject coincidence group with fewer than 2 channels."""
        with pytest.raises(ValidationError):
            CoincidencesMetadata(
                user_name="test_user",
                coincidences=[[1]],
            )

    def test_invalid_group_with_non_integer(self):
        """Should reject coincidence group containing non-integers."""
        with pytest.raises(ValidationError):
            CoincidencesMetadata(
                user_name="test_user",
                coincidences=[[1, "invalid"]],
            )

    def test_invalid_empty_coincidences(self):
        """Should reject empty list of coincidences."""
        with pytest.raises(ValidationError):
            CoincidencesMetadata(
                user_name="test_user",
                coincidences=[],
            )

    def test_alias_models(self):
        """CoincidenceMetadata and CoincidenceMeasurementRequest aliases should be available."""
        from app.models import CoincidenceMetadata, CoincidenceMeasurementRequest
        meta = CoincidenceMetadata(user_name="test_user", coincidences=[[1, 2], [3, 4]])
        req = CoincidenceMeasurementRequest(duration_seconds=10, metadata=meta)
        assert req.coincidences == [[1, 2], [3, 4]]
