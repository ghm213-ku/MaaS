"""Behaviour the MaaS GUI relies on.

- Live count-rate / coincidences accept duration_seconds (Time Tagger startFor)
  and publish a last update flagged "final" once the acquisition is complete.
- Coincidence groups are always published on their own ":stream_{i}" channel.
- Channel trigger/delay values are recorded from the hardware and served by
  GET /api/v1/channels/parameters.
- Releasing channels returns the ID of the parameter-reset job.
- The status endpoint returns the job's message (e.g. why it failed).
"""

import asyncio
import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from main import app
from app.api import routes
from app.models import CoincidencesMetadata, CountRateMetadata, SetParametersMetadata
from app.services.channel_parameters import (
    CHANNEL_PARAMETERS_KEY,
    get_channel_parameters,
    record_channel_parameters,
)
from app.services.coincidences_live import CoincidencesLiveMeasurementHandler
from app.services.count_rate_live import CountRateLiveMeasurementHandler
from app.services.job_processor import JobProcessor
from app.services.set_parameters import SetParametersHandler
from app.services.status_manager import StatusManager


def _published(mock_redis, channel):
    return [json.loads(c[0][1]) for c in mock_redis.publish.call_args_list if c[0][0] == channel]


class FakeRedisHash:
    """Just enough of redis for the channel-parameters hash."""

    def __init__(self):
        self.hashes = {}

    def hset(self, key, mapping):
        self.hashes.setdefault(key, {}).update(mapping)

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))


# ---------- timed live acquisitions ----------


@pytest.mark.asyncio
async def test_count_rate_live_timed_publishes_final_frame():
    counter = MagicMock()
    counter.getData.return_value = [[1, 2], [3, 4]]
    counter.getDataTotalCounts.return_value = [3, 7]
    counter.getCaptureDuration.return_value = int(2e9)
    redis_client = MagicMock()
    handler = CountRateLiveMeasurementHandler(tagger=MagicMock())
    handler.status_id = "sid"
    handler.redis_client = redis_client
    metadata = CountRateMetadata(user_name="u", channels=[1, 2], binwidth=int(1e9), n_values=2, refresh_rate=100)

    with patch("app.services.count_rate_live.TimeTagger.Counter", return_value=counter):
        await handler.start(0.05, metadata)

    counter.startFor.assert_called_once_with(int(0.05 * 1e12))
    counter.waitUntilFinished.assert_called_once()
    frames = _published(redis_client, "measurement:data:sid")
    assert frames[-1]["final"] is True
    assert frames[-1]["data"] == [[1, 2], [3, 4]]
    assert all(f["final"] is False for f in frames[:-1])


@pytest.mark.asyncio
async def test_count_rate_live_untimed_has_no_final_frame():
    counter = MagicMock()
    counter.getData.return_value = [[1], [2]]
    redis_client = MagicMock()
    handler = CountRateLiveMeasurementHandler(tagger=MagicMock())
    handler.status_id = "sid"
    handler.redis_client = redis_client
    metadata = CountRateMetadata(user_name="u", channels=[1, 2], refresh_rate=100)

    with patch("app.services.count_rate_live.TimeTagger.Counter", return_value=counter):
        task = asyncio.create_task(handler.start(None, metadata))
        await asyncio.sleep(0.05)
        await handler.stop()
        await task

    counter.startFor.assert_not_called()
    assert not any(f["final"] for f in _published(redis_client, "measurement:data:sid"))


@pytest.fixture
def mock_tt():
    tt = MagicMock()
    tt.Coincidences.return_value.getChannels.return_value = [20]
    tt.Counter.return_value.getData.return_value = [[5, 6, 7]]
    with patch("app.services.coincidences.TimeTagger", tt):
        yield tt


@pytest.mark.asyncio
async def test_coincidences_live_single_group_publishes_stream_channel_and_final(mock_tt):
    redis_client = MagicMock()
    handler = CoincidencesLiveMeasurementHandler(tagger=MagicMock())
    handler.status_id = "sid"
    handler.redis_client = redis_client
    metadata = CoincidencesMetadata(user_name="u", coincidences=[[1, 2]], n_values=3, refresh_rate=100)

    await handler.start(duration_seconds=0.05, metadata=metadata)

    mock_tt.Counter.return_value.startFor.assert_called_once_with(int(0.05 * 1e12))
    mock_tt.Counter.return_value.waitUntilFinished.assert_called_once()
    stream = _published(redis_client, "measurement:data:sid:stream_0")
    assert stream, "a single group must still be published on :stream_0"
    assert stream[-1]["type"] == "coincidences_live_stream"
    assert stream[-1]["data"] == [5, 6, 7]
    assert stream[-1]["final"] is True
    main = _published(redis_client, "measurement:data:sid")
    assert main[-1]["final"] is True


# ---------- channel parameters ----------


def test_record_and_read_channel_parameters():
    redis_client = FakeRedisHash()
    tagger = MagicMock()
    tagger.getTriggerLevel.side_effect = lambda ch: {1: 0.5, 12: 0.0}[ch]
    tagger.getInputDelay.side_effect = lambda ch: {1: 250, 12: 0}[ch]

    record_channel_parameters(redis_client, tagger, [12, 1])

    assert get_channel_parameters(redis_client) == [
        {"channel_number": 1, "trigger_voltage": 0.5, "input_delay": 250},
        {"channel_number": 12, "trigger_voltage": 0.0, "input_delay": 0},
    ]


@pytest.mark.asyncio
async def test_set_parameters_records_hardware_values():
    redis_client = FakeRedisHash()
    tagger = MagicMock()
    tagger.getTriggerLevel.return_value = 0.25
    tagger.getInputDelay.return_value = 1000
    handler = SetParametersHandler(tagger=tagger)
    handler.redis_client = redis_client

    await handler.start(0, SetParametersMetadata(channels=[3], user_name="u", input_delay=1000, trigger_voltage=0.25))

    tagger.setTriggerLevel.assert_called_once_with(3, 0.25)
    assert get_channel_parameters(redis_client) == [
        {"channel_number": 3, "trigger_voltage": 0.25, "input_delay": 1000}
    ]


# ---------- API ----------


@pytest.fixture
def api():
    status_manager = MagicMock(spec=StatusManager)
    status_manager.redis_client = FakeRedisHash()
    processor = MagicMock(spec=JobProcessor)
    app.dependency_overrides[routes.get_status_manager] = lambda: status_manager
    app.dependency_overrides[routes.get_job_processor] = lambda: processor
    app.dependency_overrides[routes.get_file_logger] = lambda: None
    try:
        yield TestClient(app), status_manager, processor
    finally:
        app.dependency_overrides.clear()


def test_get_channel_parameters_endpoint(api):
    client, status_manager, _ = api
    status_manager.redis_client.hset(
        CHANNEL_PARAMETERS_KEY,
        mapping={"16": json.dumps({"trigger_voltage": 0.0, "input_delay": 0})},
    )

    resp = client.get("/api/v1/channels/parameters")

    assert resp.status_code == 200
    assert resp.json() == {"channels": [{"channel_number": 16, "trigger_voltage": 0.0, "input_delay": 0}]}


def test_list_channels_without_trailing_slash_is_not_redirected(api):
    client, status_manager, _ = api
    status_manager.get_all_channels.return_value = []
    status_manager.get_channel_stats.return_value = {
        "total_channels": 0, "available_channels": 0, "booked_channels": 0,
    }

    resp = client.get("/api/v1/channels", follow_redirects=False)

    assert resp.status_code == 200


@pytest.mark.parametrize("endpoint,payload,duration", [
    ("count-rate-live", {"channels": [1]}, 0.5),
    ("coincidences-live", {"coincidences": [[1, 2]]}, 2),
    ("count-rate-live", {"channels": [1]}, None),
])
def test_live_endpoints_pass_duration_to_job(api, endpoint, payload, duration):
    client, status_manager, processor = api
    status_manager.get_booked_channels.return_value = {1: "u", 2: "u"}
    body = {"metadata": {**payload, "user_name": "u"}}
    if duration is not None:
        body["duration_seconds"] = duration

    resp = client.post(f"/api/v1/measurements/{endpoint}", json=body)

    assert resp.status_code == 201, resp.text
    assert processor.enqueue_job.call_args.kwargs["duration_seconds"] == duration


def test_release_returns_parameter_reset_id(api):
    client, status_manager, processor = api
    status_manager.release_channels.return_value = {
        "user_name": "u", "released_channels": [3], "total_released": 1,
    }

    with patch.object(routes, "_authorize_channel_release"):
        resp = client.post("/api/v1/channels/release/u", json={"channel_numbers": [3]})

    assert resp.status_code == 200, resp.text
    reset_id = resp.json()["parameter_reset_id"]
    assert reset_id
    assert processor.enqueue_job.call_args.kwargs["status_id"] == reset_id


def test_status_includes_failure_message(api):
    client, status_manager, _ = api
    status_manager.get_status.return_value = {
        "measurement_type": "set_parameters",
        "status": "failed",
        "started_at": "2026-01-01T00:00:00",
        "message": "Job failed: invalid trigger level",
    }
    status_manager.get_metadata.return_value = {}
    status_manager.get_results.return_value = None

    resp = client.get("/api/v1/measurements/abc/status")

    assert resp.status_code == 200
    assert resp.json()["status"] == "failed"
    assert resp.json()["message"] == "Job failed: invalid trigger level"
