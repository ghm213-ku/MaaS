"""Tests for SaveRawTagsMeasurmentRequest model with mocked tagger."""
import pytest
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime
from pydantic import ValidationError

from app.models import SaveRawTagsMeasurmentRequest, SaveRawTagsMetadata, MeasurementType
from app.handlers.save_raw_tags import SaveRawTagsMeasurementHandler


@pytest.fixture
def mock_tagger():
    """Create a mocked TimeTagger object."""
    mock = MagicMock()
    mock.startFor = MagicMock()
    mock.waitUntilFinished = MagicMock()
    mock.stop = MagicMock()
    return mock


@pytest.fixture
def mock_file_writer():
    """Create a mocked FileWriter object."""
    mock = MagicMock()
    mock.startFor = MagicMock()
    mock.waitUntilFinished = MagicMock()
    mock.stop = MagicMock()
    return mock


class TestSaveRawTagsMeasurmentRequestModel:
    """Test SaveRawTagsMeasurmentRequest model validation."""
    
    def test_model_creation_with_valid_metadata(self):
        """Should create a valid SaveRawTagsMeasurmentRequest with proper metadata."""
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1, 2, 3],
            target_file_path="C:\\Users\\s257050\\Desktop\\fileWriter"
        )
        request = SaveRawTagsMeasurmentRequest(
            measurement_type=MeasurementType.SAVE_RAW_TAGS,
            duration_seconds=60,
            metadata=metadata
        )
        
        assert request.measurement_type == MeasurementType.SAVE_RAW_TAGS
        assert request.duration_seconds == 60
        assert request.metadata.channel_list == [1, 2, 3]
        assert request.metadata.target_file_path == "C:\\Users\\s257050\\Desktop\\fileWriter"
    
    def test_model_default_measurement_type(self):
        """Should default to SAVE_RAW_TAGS measurement type."""
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1, 2],
            target_file_path="C:\\test"
        )
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=60,
            metadata=metadata
        )
        
        assert request.measurement_type == MeasurementType.SAVE_RAW_TAGS
    
    def test_model_requires_duration_seconds(self):
        """Should require duration_seconds field."""
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1, 2],
            target_file_path="C:\\test"
        )
        with pytest.raises(ValidationError) as exc_info:
            SaveRawTagsMeasurmentRequest(
                metadata=metadata
            )
        
        assert "duration_seconds" in str(exc_info.value)
    
    def test_model_requires_metadata(self):
        """Should require metadata field."""
        with pytest.raises(ValidationError) as exc_info:
            SaveRawTagsMeasurmentRequest(
                duration_seconds=60
            )
        
        assert "metadata" in str(exc_info.value)
    
    def test_metadata_requires_channel_list(self):
        """Metadata should require channel_list field."""
        with pytest.raises(ValidationError) as exc_info:
            SaveRawTagsMetadata(user_name="test_user", 
                target_file_path="C:\\path"
            )
        
        assert "channel_list" in str(exc_info.value)
    
    def test_metadata_requires_target_file_path(self):
        """Metadata should require target_file_path field."""
        with pytest.raises(ValidationError) as exc_info:
            SaveRawTagsMetadata(user_name="test_user", 
                channel_list=[1, 2, 3]
            )
        
        assert "target_file_path" in str(exc_info.value)
    
    def test_model_metadata_with_channel_list(self):
        """Metadata should contain channel_list."""
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1, 2, 3, 4],
            target_file_path="C:\\path"
        )
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=60,
            metadata=metadata
        )
        
        assert request.metadata.channel_list == [1, 2, 3, 4]
        assert len(request.metadata.channel_list) == 4
    
    def test_model_metadata_with_target_file_path(self):
        """Metadata should contain target_file_path."""
        test_path = "D:\\data\\measurements\\raw_tags.dat"
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1],
            target_file_path=test_path
        )
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=30,
            metadata=metadata
        )
        
        assert request.metadata.target_file_path == test_path
    
    def test_model_dict_serialization(self):
        """Should serialize to dictionary correctly."""
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1, 2, 3],
            target_file_path="C:\\test"
        )
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=60,
            metadata=metadata
        )
        
        request_dict = request.dict()
        assert request_dict["measurement_type"] == "save_raw_tags"
        assert request_dict["duration_seconds"] == 60
        assert request_dict["metadata"]["channel_list"] == [1, 2, 3]
        assert request_dict["metadata"]["target_file_path"] == "C:\\test"
    
    def test_model_json_serialization(self):
        """Should serialize to JSON correctly."""
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1, 2, 3],
            target_file_path="C:\\test"
        )
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=60,
            metadata=metadata
        )
        
        json_str = request.json()
        assert "save_raw_tags" in json_str
        assert "channel_list" in json_str
        assert "target_file_path" in json_str
    
    def test_model_parse_from_dict(self):
        """Should parse from dictionary correctly."""
        data = {
            "measurement_type": "save_raw_tags",
            "duration_seconds": 45,
            "metadata": {"user_name": "test_user", 
                "channel_list": [2, 3, 4],
                "target_file_path": "D:\\output"
            }
        }
        
        request = SaveRawTagsMeasurmentRequest(**data)
        assert request.duration_seconds == 45
        assert request.metadata.channel_list == [2, 3, 4]
    
    def test_metadata_channel_list_validation_type(self):
        """Channel list should be a list of integers."""
        with pytest.raises(ValidationError) as exc_info:
            SaveRawTagsMetadata(user_name="test_user", 
                channel_list="not_a_list",  # String that cannot be converted to list
                target_file_path="C:\\test"
            )
        
        assert len(exc_info.value.errors()) > 0
    
    def test_metadata_target_file_path_validation_type(self):
        """Target file path should be a string."""
        with pytest.raises(ValidationError) as exc_info:
            SaveRawTagsMetadata(user_name="test_user", 
                channel_list=[1, 2, 3],
                target_file_path=12345  # int instead of string
            )
        
        assert "target_file_path" in str(exc_info.value)


class TestSaveRawTagsMeasurementHandlerWithMockedTagger:
    """Test SaveRawTagsMeasurementHandler with mocked tagger."""
    
    def test_handler_initialization_with_mocked_tagger(self, mock_tagger):
        """Handler should initialize correctly with mocked tagger."""
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        
        assert handler.tagger == mock_tagger
        assert handler._measurement_task is None
        assert handler._start_time is None
    
    @pytest.mark.asyncio
    async def test_start_measurement_with_metadata(self, mock_tagger, mock_file_writer):
        """Should start measurement using data from metadata."""
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        
        channels = [1, 2, 3]
        file_path = "C:\\test\\output.dat"
        # start() waits duration + 1 s for the (mocked) FileWriter; keep it short
        duration = 0.1

        with patch("Swabian.TimeTagger.FileWriter", return_value=mock_file_writer):
            # Extract from metadata like the API would
            metadata = SaveRawTagsMetadata(user_name="test_user", channel_list=channels, target_file_path=file_path)
            
            await handler.start(duration, metadata)
            
            assert handler._start_time is not None
            assert isinstance(handler._start_time, datetime)
    
    def test_handler_with_single_channel(self, mock_tagger):
        """Handler should work with single channel in metadata."""
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1],
            target_file_path="C:\\single_channel.dat"
        )
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=30,
            metadata=metadata
        )
        
        assert len(request.metadata.channel_list) == 1
        assert request.metadata.channel_list[0] == 1
    
    def test_handler_with_multiple_channels(self, mock_tagger):
        """Handler should work with multiple channels in metadata."""
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        channels = [1, 2, 3, 4, 5, 6, 7, 8]
        
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=channels,
            target_file_path="C:\\multi_channel.dat"
        )
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=120,
            metadata=metadata
        )
        
        assert len(request.metadata.channel_list) == 8
        assert request.metadata.channel_list == channels
    
    def test_handler_with_various_durations(self, mock_tagger):
        """Handler should accept various duration values."""
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        
        durations = [10, 30, 60, 300, 1800]
        for duration in durations:
            metadata = SaveRawTagsMetadata(user_name="test_user", 
                channel_list=[1, 2],
                target_file_path="C:\\test.dat"
            )
            request = SaveRawTagsMeasurmentRequest(
                duration_seconds=duration,
                metadata=metadata
            )
            
            assert request.duration_seconds == duration
    
    def test_handler_with_different_file_paths(self, mock_tagger):
        """Handler should work with different file path formats."""
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        
        file_paths = [
            "C:\\Users\\test\\output.dat",
            "D:\\Data\\measurement_001.dat",
            "\\\\server\\share\\tags.dat",
            "./local_output.dat",
            "tags_2024_04_30.dat"
        ]
        
        for file_path in file_paths:
            metadata = SaveRawTagsMetadata(user_name="test_user", 
                channel_list=[1, 2, 3],
                target_file_path=file_path
            )
            request = SaveRawTagsMeasurmentRequest(
                duration_seconds=60,
                metadata=metadata
            )
            
            assert request.metadata.target_file_path == file_path
    
    def test_mocked_tagger_is_used_correctly(self, mock_tagger):
        """Verify that mocked tagger is accessible from handler."""
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        
        # Verify mock is the tagger
        assert handler.tagger is mock_tagger
        
        # Verify mock methods are callable
        assert callable(handler.tagger.startFor)
        assert callable(handler.tagger.waitUntilFinished)
        assert callable(handler.tagger.stop)
    
    @pytest.mark.asyncio
    async def test_handler_metadata_extraction(self, mock_tagger):
        """Test that metadata is correctly extracted in handler operations."""
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        
        # Create a request with metadata
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1, 2],
            target_file_path="C:\\measurement.dat"
        )
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=45,
            metadata=metadata
        )
        
        # Verify metadata contains the required fields
        assert hasattr(request.metadata, 'channel_list')
        assert hasattr(request.metadata, 'target_file_path')
        
        # Extract and verify
        channels = request.metadata.channel_list
        file_path = request.metadata.target_file_path
        
        assert channels == [1, 2]
        assert file_path == "C:\\measurement.dat"


class TestMetadataValidationErrors:
    """Test validation error handling for missing or invalid metadata fields."""

    @pytest.mark.parametrize(
        "invalid_kwargs, expected_error_field",
        [
            ({"target_file_path": "C:\\test.dat"}, "channel_list"),
            ({"channel_list": [1, 2, 3]}, "target_file_path"),
            ({"channel_list": "1,2,3", "target_file_path": "C:\\test.dat"}, "channel_list"),
            ({"channel_list": [1, 2, 3], "target_file_path": 123}, "target_file_path"),
        ]
    )
    def test_metadata_validation_errors(self, invalid_kwargs, expected_error_field):
        with pytest.raises(ValidationError) as exc_info:
            SaveRawTagsMetadata(user_name="test_user", **invalid_kwargs)
        
        error = exc_info.value
        assert len(error.errors()) > 0
        assert any(expected_error_field in str(e) for e in error.errors())

    @pytest.mark.parametrize(
        "invalid_kwargs, expected_error_field",
        [
            ({"duration_seconds": 60}, "metadata"),
            ({"duration_seconds": 60, "metadata": {"user_name": "test_user", "channel_list": [1, 2, 3]}}, "target_file_path"),
        ]
    )
    def test_request_validation_errors(self, invalid_kwargs, expected_error_field):
        with pytest.raises(ValidationError) as exc_info:
            SaveRawTagsMeasurmentRequest(**invalid_kwargs)
        
        error = exc_info.value
        assert len(error.errors()) > 0
        assert any(expected_error_field in str(e) for e in error.errors())


class TestIntegrationWithMockedTaggerAndModel:
    """Integration tests combining model validation with handler operations."""
    
    def test_model_to_handler_workflow(self, mock_tagger):
        """Complete workflow from model creation to handler usage."""
        # Create metadata model
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1, 2, 3],
            target_file_path="C:\\output\\measurement.dat"
        )
        
        # Create request model
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=60,
            metadata=metadata
        )
        
        # Create handler with mocked tagger
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        
        # Extract data from request
        duration = request.duration_seconds
        channels = request.metadata.channel_list
        file_path = request.metadata.target_file_path
        
        # Verify all data is correctly extracted
        assert duration == 60
        assert channels == [1, 2, 3]
        assert file_path == "C:\\output\\measurement.dat"
        assert handler.tagger is mock_tagger
    
    def test_mocked_tagger_file_writer_interaction(self, mock_tagger, mock_file_writer):
        """Test interaction between mocked tagger and FileWriter."""
        metadata = SaveRawTagsMetadata(user_name="test_user", 
            channel_list=[1, 2, 3],
            target_file_path="C:\\test.dat"
        )
        request = SaveRawTagsMeasurmentRequest(
            duration_seconds=60,
            metadata=metadata
        )
        
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        
        # Simulate FileWriter creation with mocked tagger
        with patch("Swabian.TimeTagger.FileWriter", return_value=mock_file_writer):
            channels = request.metadata.channel_list
            file_path = request.metadata.target_file_path
            
            # FileWriter would be created like this in the handler
            assert channels == [1, 2, 3]
            assert file_path == "C:\\test.dat"


class TestSaveRawTagsMeasurementHandlerStop:
    """Test stop method in SaveRawTagsMeasurementHandler."""
    
    @pytest.mark.asyncio
    async def test_stop_sets_stop_event(self, mock_tagger):
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        handler._stop_event = MagicMock()
        handler._fileWriter = MagicMock()
        handler._target_file_path = "test.dat"
        handler._channel_list = [1, 2]
        handler._start_time = datetime.now()
        
        with patch.object(handler, '_delete_output_file') as mock_delete:
            res = await handler.stop()
            
            assert handler._stopped is True
            handler._stop_event.set.assert_called_once()
            assert res["status"] == "stopped"

    @pytest.mark.asyncio
    async def test_stop_stops_file_writer_and_handles_exception(self, mock_tagger):
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        handler._fileWriter = MagicMock()
        handler._fileWriter.stop.side_effect = Exception("Writer error")
        handler._target_file_path = "test.dat"
        
        with patch('app.handlers.save_raw_tags.logger.error') as mock_logger_error:
            with patch.object(handler, '_delete_output_file') as mock_delete:
                await handler.stop()
                mock_logger_error.assert_called_with("Failed to stop file writer: Writer error")

    @pytest.mark.asyncio
    async def test_stop_does_not_free_shared_tagger(self, mock_tagger):
        """The worker's tagger is shared by all jobs; freeing it breaks every later job."""
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        handler._target_file_path = "test.dat"

        with patch('app.handlers.save_raw_tags.TimeTagger.freeTimeTagger') as mock_free:
            with patch.object(handler, '_delete_output_file'):
                await handler.stop()
            mock_free.assert_not_called()

    @pytest.mark.asyncio
    async def test_completed_run_does_not_free_shared_tagger(self, mock_tagger):
        handler = SaveRawTagsMeasurementHandler(tagger=mock_tagger)
        metadata = SaveRawTagsMetadata(user_name="test_user", channel_list=[1, 2], target_file_path="test.ttbin")

        with patch('app.handlers.save_raw_tags.TimeTagger') as mock_tt:
            await handler.start(0.01, metadata)
            mock_tt.freeTimeTagger.assert_not_called()
            mock_tt.FileWriter.return_value.stop.assert_called_once()
