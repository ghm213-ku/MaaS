# Developer Guide

For people changing the MaaS code: project layout, running locally, tests, debugging, and adding
a new measurement type. Read [README_SYSTEM_FLOW.md](README_SYSTEM_FLOW.md) first for the
architecture.

---

## 1. Setup

- Python 3.10+
- Swabian Time Tagger software (provides `from Swabian import TimeTagger`; not on PyPI)
- Redis (Memurai on Windows) on `127.0.0.1:6379`

```bash
pip install -r requirements.txt
```

### Run

```bash
python main.py      # web API on http://localhost:8000
python worker.py    # worker, connects to the Time Tagger
```

Worker flags for development:

| Flag | Effect |
|------|--------|
| *(none)* | Normal run. Built-in test signal off on all channels |
| `--testing` | Built-in test signal on for channels 1–5, so you get counts without detectors |
| `--no-hardware` | Don't open a Time Tagger. Jobs reach the worker but fail with *requires a Time Tagger* |

Other settings:

| Setting | Where | Default |
|---------|-------|---------|
| Log level | env `LOG_LEVEL` (read in `config.py`) | `INFO` |
| SQLite user DB path | env `MAAS_DB_PATH` | `maas_auth.db` in the repo root |
| Audit log folder | env `MAAS_LOGS_DIR` | `logs/` |
| JWT signing key | env `JWT_SECRET`, else the `.jwt_secret` file (created on first run) | – |
| Redis host/port | hard-coded `127.0.0.1:6379`, DB 0, in `main.py`, `worker.py` and the WebSocket route | – |
| API port | hard-coded `8000` in `main.py` | – |

`config.py` also defines `SERVICE_PORT` and SSL certificate settings, and `app/utils/ssl_utils.py`
can generate a self-signed certificate, but `main.py` does not use either: the API runs on plain
HTTP.

---

## 2. Project layout

```
main.py                     web API entry point (FastAPI app, lifespan, /health)
worker.py                   worker entry point (Time Tagger, handler registration, job loop)
config.py                   log level/format (other settings unused)
app/
  api/routes.py             measurement, channel and set-parameters endpoints; WebSocket stream;
                            AuditRoute (audit log for POST/PUT/DELETE)
  api/auth.py               /auth/login, user management, password change
  middleware/auth_middleware.py   JWT check for /api/v1/* and /auth/users, /auth/password
  db/database.py            SQLite users/roles; seeds roles and admin/admin on import
  models.py                 Pydantic request/response models, MeasurementType enum
  payloads.py               MeasurementPayloadMapper: measurement type -> request model
  services/
    measurement.py          MeasurementHandler base class
    count_rate.py, count_rate_live.py, correlation.py, coincidences.py,
    coincidences_live.py, save_raw_tags.py, time_histograms_live.py,
    set_parameters.py       one handler per measurement type
    counter_utils.py        shared Counter result summary
    channel_parameters.py   publishes/reads per-channel trigger level and delay
    status_manager.py       Redis status + channel bookings
    job_processor.py        queue, threads, stop listener
    file_logger.py          request_logs/*.txt, logs/measurements/*.jsonl
    audit_logger.py         logs/audit.log (JSON lines, rotated at 50 MB x 10)
  utils/logger.py           console + file logging setup
  utils/path_utils.py       {datetime}/{measurement-type}/~ expansion for output paths
tests/                      pytest suite (see section 4)
```

---

## 3. Handlers

All handlers subclass `MeasurementHandler` (`app/services/measurement.py`):

```python
class MyHandler(MeasurementHandler):
    async def start(self, duration_seconds, metadata) -> dict: ...
    async def stop(self) -> dict: ...
```

What the `JobProcessor` gives each handler (a new instance per job):

- `self.tagger` – the worker's Time Tagger object
- `self.status_id` – the measurement ID
- `self.redis_client` – for publishing live data to `measurement:data:{status_id}`
- `metadata` – the validated metadata model for the type, with `target_location` /
  `target_file_path` already expanded

`start()` runs in its own thread with its own asyncio loop. Its return value becomes the
`results` of the status. `stop()` is called from the stop listener when a `DELETE` arrives. It
should end the Time Tagger measurement, set `self._stopped = True` so `start()` skips saving, and
delete any partial output with `self._delete_output_file(path)`.

---

## 4. Tests

```bash
pytest                       # whole suite (pytest.ini sets testpaths, -v, asyncio_mode=auto)
pytest tests/test_channel_api.py
pytest -k coincidences
```

The tests need neither Redis nor a Time Tagger:

- `tests/conftest.py` replaces `Swabian` with a `MagicMock` and patches `redis.Redis` /
  `redis.asyncio.Redis` with `fakeredis`.
- Before any app module is imported, it points `MAAS_DB_PATH`, `MAAS_LOGS_DIR`, `JWT_SECRET` and
  `HOME`/`USERPROFILE` at a temporary sandbox.
- After every test it checks that nothing in the repo or in the real `~/Desktop/MaasData` was
  written. A test that writes there fails.

`pytest.ini` gives every test a 30-second limit (`pytest-timeout`). On Windows a timeout aborts the
whole run, so keep measurement durations in tests short.

`tests/test_timetagger_conformance.py` checks that handlers call the Swabian API with valid
arguments, and `tests/test_gui_contract.py` pins the request/response shapes the GUI relies on.
Update them when you change either.

---

## 5. Debugging

Logs (also printed to the console):

| File | Written by |
|------|-----------|
| `logs/services/main.log` | web API (root logger, all modules) |
| `logs/services/worker.log` | worker |
| `logs/measurements/measurement_status_log.jsonl` | every status change |
| `logs/audit.log` | every POST/PUT/DELETE |
| `request_logs/measurement_requests.txt`, `request_logs/channel_requests.txt` | accepted requests |

Every measurement log line is prefixed with `[<measurement_id>]`, so
`grep -r <id> logs request_logs` follows one request through both processes.

Redis:

```bash
redis-cli                         # memurai-cli with Memurai
KEYS measurement:*:<id>           # status / metadata / results of one measurement
GET measurement:status:<id>
LLEN measurement:job_queue        # >0 and growing → worker not consuming
HGETALL channels:booked           # who holds which channel
SUBSCRIBE measurement:data:<id>   # watch live data
MONITOR                           # every command (noisy)
```

Do **not** run `FLUSHDB` on a shared machine: it also wipes all channel bookings.

Common problems:

| Symptom | Cause |
|---------|-------|
| Jobs stay `queued` | Worker not running or crashed; see `worker.log` |
| `failed` – `requires a Time Tagger` | Worker started with `--no-hardware` |
| Worker exits at startup | Time Tagger unplugged or opened by another process (only one connection allowed) |
| `ModuleNotFoundError: Swabian` | Time Tagger software not installed for this Python |
| Validation error in `worker.log` but the request was accepted | The worker validates metadata again after filling in defaults and paths; the two checks disagree |
| Ctrl+C on the API hangs | Fixed: shutdown waits at most 5 s (`timeout_graceful_shutdown`) |

---

## 6. Adding a measurement type

Example: a new `my_measure` type at `POST /api/v1/measurements/my-measure`.

1. **Enum** – add `MY_MEASURE = "my_measure"` to `MeasurementType` in `app/models.py`.
2. **Models** – in `app/models.py` add:
   - `MyMeasureMetadata` with the fields, including `user_name: str` and the channels;
   - `MyMeasureRequest` with `measurement_type`, `duration_seconds` and `metadata`. Copy the
     `wrap_flat_payload` validator from an existing request so flat bodies keep working.
3. **Payload mapper** – add `"my_measure": MyMeasureRequest` to
   `MeasurementPayloadMapper._PAYLOAD_MODELS` in `app/payloads.py`. The worker uses this to find
   the metadata model; without it the job fails with *Unknown measurement type*.
4. **Handler** – create `app/services/my_measure.py` with a `MeasurementHandler` subclass (see
   section 3). Return a small summary dict from `start()`; write bulk data to the file or to the
   live channel, not into the result.
5. **Register** – in `worker.py`, import the handler and call
   `self.job_processor.register_handler("my_measure", MyMeasureHandler)`.
6. **Route** – in `app/api/routes.py` add an endpoint on `measurement_router` that calls
   `_handle_measurement_request(...)`, like `start_count_rate_measurement`. Pass the channel list
   so the booking check runs. The audit log picks up the new endpoint automatically.
7. **Tests** – model validation, handler (with the mocked Time Tagger), and the route. Run
   `pytest`.
8. **Docs** – add the type to the table in [README_USER_GUIDE.md](README_USER_GUIDE.md).

The `MeasurementType` enum and the `register_handler` names must match exactly; this string is
what travels through the queue.

---

## 7. Further reading

- [README_SYSTEM_FLOW.md](README_SYSTEM_FLOW.md) – request flow, Redis keys, stop and live data
- [README_USER_GUIDE.md](README_USER_GUIDE.md) – the API from a client's point of view
- [CHANNEL_MANAGEMENT_GUIDE.md](CHANNEL_MANAGEMENT_GUIDE.md) – booking rules
- [Swabian Time Tagger API reference](https://www.swabianinstruments.com/static/documentation/TimeTagger/api/index.html)
