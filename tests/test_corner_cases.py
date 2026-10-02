import pytest
from unittest.mock import MagicMock
from fastapi import HTTPException
from app.api.auth import update_own_password, UpdatePasswordRequest
from starlette.requests import Request

@pytest.mark.asyncio
async def test_update_own_password_no_user_id():
    req = UpdatePasswordRequest(old_password="old", new_password="new")
    request_mock = MagicMock(spec=Request)
    # create a mock state object that explicitly does not have user_id
    class State:
        pass
    request_mock.state = State()
    
    with pytest.raises(HTTPException) as exc:
        await update_own_password(req, request_mock)
    assert exc.value.status_code == 401
    assert exc.value.detail == "Not authenticated"

@pytest.mark.asyncio
async def test_update_own_password_user_not_found(monkeypatch):
    req = UpdatePasswordRequest(old_password="old", new_password="new")
    request_mock = MagicMock(spec=Request)
    
    class State:
        user_id = 9999
    request_mock.state = State()
    
    # mock get_user_by_id to return None
    import app.api.auth
    monkeypatch.setattr(app.api.auth, "get_user_by_id", lambda x: None)
    
    with pytest.raises(HTTPException) as exc:
        await update_own_password(req, request_mock)
    assert exc.value.status_code == 404
    assert exc.value.detail == "User not found"

from app.api.routes import get_job_processor, get_status_manager, set_processors

def test_get_job_processor_uninitialized():
    set_processors(None, None, None)
    with pytest.raises(RuntimeError) as exc:
        get_job_processor()
    assert "not initialized" in str(exc.value)

def test_get_status_manager_uninitialized():
    set_processors(None, None, None)
    with pytest.raises(RuntimeError) as exc:
        get_status_manager()
    assert "not initialized" in str(exc.value)

from app.api.routes import _handle_measurement_request
from app.models import MeasurementType

def test_handle_measurement_request_user_mismatch():
    mock_processor = MagicMock()
    mock_status_manager = MagicMock()
    # Channels 1, 2 booked by 'other_user'
    mock_status_manager.get_booked_channels.return_value = {1: "other_user", 2: "other_user"}
    
    with pytest.raises(HTTPException) as exc:
        _handle_measurement_request(
            "test_req",
            MeasurementType.COUNT_RATE,
            None,
            {},
            [1, 2],
            mock_processor,
            mock_status_manager,
            None,
            "test_user"
        )
    assert exc.value.status_code == 403
    assert "not booked by user" in exc.value.detail

from app.api.routes import book_channels, release_channels, stop_measurement
from app.models import ChannelBookRequest

def test_book_channels_file_logger_exception():
    mock_sm = MagicMock()
    mock_sm.book_channels.return_value = {"user_name": "user", "booked_channels": [1], "booking_time": "time"}
    mock_fl = MagicMock()
    mock_fl.log_channel_book_request.side_effect = Exception("File IO error")
    
    req = ChannelBookRequest(user_name="user", channels=[1])
    # This should not raise an exception because the error is caught and logged
    res = book_channels(req, mock_sm, mock_fl)
    assert res.booked_channels == [1]

def test_release_channels_file_logger_exception():
    mock_sm = MagicMock()
    mock_sm.release_channels.return_value = {"user_name": "user", "released_channels": [1], "total_released": 1}
    mock_fl = MagicMock()
    mock_fl.log_channel_release_request.side_effect = Exception("File IO error")
    mock_processor = MagicMock()
    
    # This should not raise an exception
    res = release_channels("user", mock_processor, mock_sm, mock_fl)
    assert res.released_channels == [1]

def test_stop_measurement_exception():
    mock_sm = MagicMock()
    mock_sm.get_status.return_value = {"status": "active"}
    mock_processor = MagicMock()
    mock_processor.stop_job.side_effect = Exception("Stop failed")
    
    with pytest.raises(HTTPException) as exc:
        stop_measurement("some-id", mock_processor, mock_sm)
    assert exc.value.status_code == 500
    assert "Stop failed" in str(exc.value.detail)

def test_handle_measurement_request_file_logger_exception():
    mock_processor = MagicMock()
    mock_status_manager = MagicMock()
    mock_status_manager.get_booked_channels.return_value = {1: "test_user"}
    
    mock_fl = MagicMock()
    mock_fl.log_measurement_request.side_effect = Exception("File IO error")
    
    res = _handle_measurement_request(
        "test_req",
        MeasurementType.COUNT_RATE,
        None,
        {},
        [1],
        mock_processor,
        mock_status_manager,
        mock_fl,
        "test_user"
    )
    assert res.status == "queued"
