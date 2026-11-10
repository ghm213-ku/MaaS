"""Stop requests can't be lost, and the worker acknowledges them.

Uses fakeredis and a fake live handler, so no Redis server or TimeTagger is needed.
"""

import asyncio
import threading
import time
from unittest.mock import MagicMock, patch

import fakeredis
import pytest

import app.services.job_processor as jp_module
from app.handlers.base import MeasurementHandler
from app.handlers.count_rate_live import CountRateLiveMeasurementHandler
from app.models import CountRateMetadata
from app.services.job_processor import (
    RUNNING_JOBS_KEY,
    STOP_ACK_PREFIX,
    STOP_REQUEST_PREFIX,
    JobProcessor,
)
from app.services.status_manager import MeasurementStatus, StatusManager

LIVE_METADATA = {"user_name": "test_user", "channels": [1], "refresh_rate": 50}


class FakeLiveHandler(MeasurementHandler):
    """Streams until stopped, like the real live handlers."""

    on_init = None  # optional hook called from __init__ (simulates a stop during setup)

    def __init__(self, tagger=None):
        super().__init__(tagger)
        if FakeLiveHandler.on_init:
            FakeLiveHandler.on_init()

    async def start(self, duration_seconds, metadata):
        await self._stream_live_data(duration_seconds, 50, lambda: None)
        return {"ran": True}

    async def stop(self):
        self._stopped = True
        if self._stop_event:
            self._stop_event.set()
        return {}


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)


@pytest.fixture
def status_manager(fake_redis):
    with patch("app.services.status_manager.redis.Redis", return_value=fake_redis):
        yield StatusManager()


@pytest.fixture
def processor(status_manager, monkeypatch):
    monkeypatch.setattr(jp_module, "STOP_POLL_INTERVAL_SECONDS", 0.05)
    FakeLiveHandler.on_init = None
    proc = JobProcessor(status_manager, tagger=MagicMock())
    proc.register_handler("count_rate_live", FakeLiveHandler)
    yield proc
    proc.close()
    FakeLiveHandler.on_init = None


def _start(processor, status_manager, status_id="m1"):
    status_manager.create_status(status_id, "count_rate_live", None, LIVE_METADATA)
    processor.process_job(status_id, "count_rate_live", None, dict(LIVE_METADATA))
    return status_id


def _wait_until(condition, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return False


def test_stop_without_pubsub_is_picked_up_from_flag(processor, status_manager, fake_redis):
    """A dead stop listener no longer means the stop is lost."""
    processor.close()  # the pub/sub fast path is gone
    status_id = _start(processor, status_manager)
    assert _wait_until(lambda: fake_redis.hexists(RUNNING_JOBS_KEY, status_id))

    processor.stop_job(status_id)

    assert processor.wait_for_stop_ack(status_id, timeout=3)
    assert status_manager.get_status(status_id)["status"] == MeasurementStatus.STOPPED.value
    assert not fake_redis.hexists(RUNNING_JOBS_KEY, status_id)
    assert not fake_redis.exists(f"{STOP_REQUEST_PREFIX}{status_id}")
    assert status_id not in processor.active_jobs


def test_stop_via_pubsub_is_acknowledged(processor, status_manager):
    status_id = _start(processor, status_manager)
    assert _wait_until(lambda: status_id in processor.active_handlers)

    processor.stop_job(status_id)

    assert processor.wait_for_stop_ack(status_id, timeout=3)
    assert status_manager.get_status(status_id)["status"] == MeasurementStatus.STOPPED.value


def test_stop_while_queued_skips_job_and_acknowledges(processor, status_manager, fake_redis):
    status_manager.create_status("q1", "count_rate_live", None, LIVE_METADATA)
    processor.stop_job("q1")
    assert not processor.is_stop_acknowledged("q1")

    processor.process_job("q1", "count_rate_live", None, dict(LIVE_METADATA))

    assert processor.wait_for_stop_ack("q1", timeout=3)
    assert "skipped" in fake_redis.get(f"{STOP_ACK_PREFIX}q1")
    assert status_manager.get_status("q1")["status"] == MeasurementStatus.STOPPED.value


def test_stop_during_setup_is_not_lost(processor, status_manager):
    """Stop arrives after the queued-check but before the handler is registered."""
    FakeLiveHandler.on_init = lambda: processor.stop_job("s1")
    _start(processor, status_manager, "s1")

    assert processor.wait_for_stop_ack("s1", timeout=3)
    assert status_manager.get_status("s1")["status"] == MeasurementStatus.STOPPED.value


def test_stopped_status_overwritten_by_active_is_restored(processor, status_manager):
    """Stop lands between the queued-check and the ACTIVE update."""
    real_update = status_manager.update_status
    fired = threading.Event()

    def update_status(status_id, status, message, results=None):
        if status == MeasurementStatus.ACTIVE.value and not fired.is_set():
            fired.set()
            processor.stop_job(status_id)  # STOPPED, then overwritten below
        return real_update(status_id, status, message, results)

    status_manager.update_status = update_status
    _start(processor, status_manager, "r1")

    assert processor.wait_for_stop_ack("r1", timeout=3)
    assert status_manager.get_status("r1")["status"] == MeasurementStatus.STOPPED.value


def test_no_ack_without_a_worker(processor, status_manager):
    status_manager.create_status("orphan", "count_rate_live", None, LIVE_METADATA)
    processor.stop_job("orphan")
    assert not processor.wait_for_stop_ack("orphan", timeout=0.3)


def test_new_stop_clears_old_ack(processor, fake_redis, status_manager):
    status_manager.create_status("a1", "count_rate_live", None, LIVE_METADATA)
    fake_redis.set(f"{STOP_ACK_PREFIX}a1", "{}")
    processor.stop_job("a1")
    assert not processor.is_stop_acknowledged("a1")


def test_adopt_jobs_from_keeps_running_jobs_stoppable(status_manager):
    old = JobProcessor(status_manager, tagger=MagicMock())
    old.active_handlers["x"] = ("handler", "loop")
    old.active_jobs["x"] = "thread"

    new = JobProcessor(status_manager, tagger=MagicMock())
    new.adopt_jobs_from(old)

    assert new.active_handlers is old.active_handlers
    assert new.active_jobs is old.active_jobs
    assert old._closed
    new.close()


def test_stop_listener_resubscribes_after_connection_error(status_manager):
    processor = JobProcessor(status_manager, tagger=None)
    broken = MagicMock()
    broken.listen.side_effect = ConnectionError("redis went away")
    working = MagicMock()
    working.listen.return_value = iter([{"type": "message", "data": "late-stop"}])
    processor._pubsub = broken
    processor._on_stop_message = MagicMock()

    with patch.object(processor, "_subscribe", return_value=working), patch.object(jp_module.time, "sleep"):
        processor._listen_for_stops()

    processor._on_stop_message.assert_called_once_with("late-stop")


@pytest.mark.asyncio
async def test_live_handler_start_does_not_clear_an_earlier_stop():
    """stop() before start() used to be undone by start() resetting _stopped."""
    handler = CountRateLiveMeasurementHandler(tagger=MagicMock())
    handler.status_id = "h1"
    handler.redis_client = MagicMock()
    await handler.stop()

    metadata = CountRateMetadata(user_name="test_user", channels=[1], binwidth=int(1e9), n_values=1)
    await asyncio.wait_for(handler.start(None, metadata), timeout=2)
