import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from app.api.channels import book_channels, list_all_channels, list_available_channels, release_channels
from app.api.measurements import (
    get_measurement_status,
    list_measurements,
    start_coincidences_live_measurement,
    start_coincidences_measurement,
    start_correlation_measurement,
    start_count_rate_live_measurement,
    start_save_raw_tags_measurement,
    stop_measurement,
)
from app.models import (
    SaveRawTagsMeasurmentRequest,
    CountRateLiveMeasurementRequest,
    CorrelationMeasurementRequest,
    CoincidencesMeasurementRequest,
    CoincidencesLiveMeasurementRequest,
    ChannelBookRequest,
    ChannelReleaseRequest,
    MeasurementType,
    CountRateMetadata,
    SaveRawTagsMetadata,
    CorrelationMetadata,
    CoincidencesMetadata
)

@pytest.mark.asyncio
async def test_start_count_rate_live_measurement():
    request = CountRateLiveMeasurementRequest(
        measurement_type=MeasurementType.COUNT_RATE_LIVE,
        metadata=CountRateMetadata(user_name="test_user", channels=[1, 2], binwidth=1000000000, n_values=1)
    )
    mock_status_manager = MagicMock()
    mock_status_manager.get_booked_channels.return_value = {1: "test_user", 2: "test_user", 3: "test_user", 4: "test_user"}
    mock_status_manager.book_channels.return_value = {"booked_channels": [1, 2], "booking_time": "time"}
    mock_job_processor = MagicMock()
    mock_file_logger = MagicMock()
    
    # Success
    res = start_count_rate_live_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert res.status == "queued"
    
    # Booking fails
    mock_status_manager.validate_channels.side_effect = ValueError("Booking failed")
    with pytest.raises(HTTPException) as exc:
        start_count_rate_live_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 400
    
    # Exception
    mock_status_manager.validate_channels.side_effect = Exception("Unknown")
    with pytest.raises(HTTPException) as exc:
        start_count_rate_live_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_start_save_raw_tags_measurement():
    request = SaveRawTagsMeasurmentRequest(
        measurement_type=MeasurementType.SAVE_RAW_TAGS,
        duration_seconds=10.0,
        metadata=SaveRawTagsMetadata(user_name="test_user", channel_list=[1, 2], target_file_path="test")
    )
    mock_status_manager = MagicMock()
    mock_status_manager.get_booked_channels.return_value = {1: "test_user", 2: "test_user", 3: "test_user", 4: "test_user"}
    mock_status_manager.book_channels.return_value = {"booked_channels": [1, 2], "booking_time": "time"}
    mock_job_processor = MagicMock()
    mock_file_logger = MagicMock()
    
    # Success
    res = start_save_raw_tags_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert res.status == "queued"
    
    # Booking fails
    mock_status_manager.validate_channels.side_effect = ValueError("Booking failed")
    with pytest.raises(HTTPException) as exc:
        start_save_raw_tags_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 400
    
    # Exception
    mock_status_manager.validate_channels.side_effect = Exception("Unknown")
    with pytest.raises(HTTPException) as exc:
        start_save_raw_tags_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_start_correlation_measurement():
    request = CorrelationMeasurementRequest(
        measurement_type=MeasurementType.CORRELATION,
        duration_seconds=10.0,
        metadata=CorrelationMetadata(user_name="test_user", channel1=1, channel2=2)
    )
    mock_status_manager = MagicMock()
    mock_status_manager.get_booked_channels.return_value = {1: "test_user", 2: "test_user", 3: "test_user", 4: "test_user"}
    mock_status_manager.book_channels.return_value = {"booked_channels": [1, 2], "booking_time": "time"}
    mock_job_processor = MagicMock()
    mock_file_logger = MagicMock()
    
    res = start_correlation_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert res.status == "queued"
    
    mock_status_manager.validate_channels.side_effect = ValueError("Booking failed")
    with pytest.raises(HTTPException) as exc:
        start_correlation_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 400
    
    mock_status_manager.validate_channels.side_effect = Exception("Unknown")
    with pytest.raises(HTTPException) as exc:
        start_correlation_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_start_coincidences_measurement():
    request = CoincidencesMeasurementRequest(
        measurement_type=MeasurementType.COINCIDENCES,
        duration_seconds=10.0,
        metadata=CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2]])
    )
    mock_status_manager = MagicMock()
    mock_status_manager.get_booked_channels.return_value = {1: "test_user", 2: "test_user", 3: "test_user", 4: "test_user"}
    mock_status_manager.book_channels.return_value = {"booked_channels": [1, 2], "booking_time": "time"}
    mock_job_processor = MagicMock()
    mock_file_logger = MagicMock()
    
    res = start_coincidences_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert res.status == "queued"
    
    mock_status_manager.validate_channels.side_effect = ValueError("Booking failed")
    with pytest.raises(HTTPException) as exc:
        start_coincidences_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 400
    
    mock_status_manager.validate_channels.side_effect = Exception("Unknown")
    with pytest.raises(HTTPException) as exc:
        start_coincidences_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_start_coincidences_live_measurement():
    request = CoincidencesLiveMeasurementRequest(
        measurement_type=MeasurementType.COINCIDENCES_LIVE,
        metadata=CoincidencesMetadata(user_name="test_user", coincidences=[[1, 2]])
    )
    mock_status_manager = MagicMock()
    mock_status_manager.get_booked_channels.return_value = {1: "test_user", 2: "test_user"}
    mock_status_manager.book_channels.return_value = {"booked_channels": [1, 2], "booking_time": "time"}
    mock_job_processor = MagicMock()
    mock_file_logger = MagicMock()
    
    res = start_coincidences_live_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert res.status == "queued"
    
    mock_status_manager.validate_channels.side_effect = ValueError("Booking failed")
    with pytest.raises(HTTPException) as exc:
        start_coincidences_live_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 400
    
    mock_status_manager.validate_channels.side_effect = Exception("Unknown")
    with pytest.raises(HTTPException) as exc:
        start_coincidences_live_measurement(request, mock_job_processor, mock_status_manager, mock_file_logger)
    assert exc.value.status_code == 500

@pytest.mark.asyncio
async def test_channels_endpoints():
    mock_sm = MagicMock()
    mock_sm.get_all_channels.return_value = []
    mock_sm.get_channel_stats.return_value = {
        "total_channels": 16,
        "available_channels": 16,
        "booked_channels": 0,
        "utilization_percent": 0.0
    }
    
    res = list_all_channels(mock_sm)
    assert res.channels == []
    
    mock_sm.get_all_channels.side_effect = Exception("Error")
    with pytest.raises(HTTPException):
        list_all_channels(mock_sm)

    mock_sm = MagicMock()
    mock_sm.get_available_channels.return_value = []
    mock_sm.get_channel_stats.return_value = {
        "total_channels": 16,
        "available_channels": 16,
        "booked_channels": 0,
        "utilization_percent": 0.0
    }
    res = list_available_channels(mock_sm)
    assert res.available_channel_numbers == []
    
    mock_sm.get_available_channels.side_effect = Exception("Error")
    with pytest.raises(HTTPException):
        list_available_channels(mock_sm)

    mock_sm = MagicMock()
    req = ChannelBookRequest(channel_numbers=[1, 2], user_name="test_user")
    mock_sm.book_channels.return_value = {"booked_channels": [1, 2], "user_name": "test_user", "booking_time": "time", "total_booked": 2}
    res = book_channels(req, mock_sm, MagicMock())
    assert res.booked_channels == [1, 2]

    mock_sm.book_channels.side_effect = ValueError("Err")
    with pytest.raises(HTTPException) as exc:
        book_channels(req, mock_sm)
    assert exc.value.status_code == 409
    
    mock_sm.book_channels.side_effect = Exception("Err")
    with pytest.raises(HTTPException):
        book_channels(req, mock_sm, MagicMock())

    mock_sm = MagicMock()
    mock_sm.release_channels.return_value = {"released_channels": [1], "user_name": "test_user", "total_released": 1}
    release_req = ChannelReleaseRequest(channel_numbers=[1])
    res = release_channels("test_user", release_req, mock_sm, MagicMock(), MagicMock())
    assert res.released_channels == [1]
    
    mock_sm.release_channels.side_effect = Exception("Err")
    with pytest.raises(HTTPException):
        release_channels("me", release_req, status_manager=mock_sm, file_logger=MagicMock(), processor=MagicMock())

@pytest.mark.asyncio
async def test_measurements_endpoints():
    mock_sm = MagicMock()
    mock_sm.get_status.return_value = {
        "status": "running", 
        "started_at": "2023-01-01T00:00:00.000",
        "measurement_type": "count_rate",
        "duration_seconds": 10.0,
        "message": "msg",
        "metadata": {"user_name": "test_user", },
        "results": {}
    }
    mock_jp = MagicMock()
    mock_sm.get_metadata.return_value = {}
    mock_sm.get_results.return_value = {}
    
    # stop
    mock_jp.stop_job.return_value = True
    res = stop_measurement("id", mock_jp, mock_sm)
    assert res.status == "running"
    
    mock_jp.stop_job.return_value = False
    res2 = stop_measurement("id", mock_jp, mock_sm)
    assert res2.status == "running"
    
    mock_jp.stop_job.side_effect = Exception("Err")
    res3 = stop_measurement("id", mock_jp, mock_sm)
    assert res3.status == "running"

    # get_measurement_status
    res = get_measurement_status("id", mock_sm)
    assert res.status == "running"
    
    mock_sm.get_status.return_value = None
    with pytest.raises(HTTPException) as exc:
        get_measurement_status("id", mock_sm)
    assert exc.value.status_code == 404
    
    mock_sm.get_status.side_effect = Exception("Err")
    with pytest.raises(HTTPException):
        get_measurement_status("id", mock_sm)
        
    # list_measurements
    mock_sm.health_check.return_value = True
    res = list_measurements(mock_sm)
    assert "service" in res
    
    mock_sm.health_check.side_effect = Exception("Err")
    with pytest.raises(HTTPException):
        list_measurements(mock_sm)
