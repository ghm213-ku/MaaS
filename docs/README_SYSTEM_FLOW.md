# System Architecture & Request Flow

How MaaS is put together and what happens to a request from the moment it arrives until the
measurement finishes. For running the service see [GETTING_STARTED.md](GETTING_STARTED.md); for
the API itself see [README_USER_GUIDE.md](README_USER_GUIDE.md).

---

## 1. Components

```
 MaaS GUI / scripts
        │  HTTP + WebSocket (port 8000)
        ▼
┌───────────────────────────────┐
│ Web API  (main.py, FastAPI)   │  auth, validation, channel checks,
│                               │  enqueue jobs, status, live stream
└──────────────┬────────────────┘
               │  Redis 127.0.0.1:6379, DB 0
               ▼
┌───────────────────────────────┐
│ Redis                         │  job queue, status/metadata/results,
│                               │  channel bookings, stop + live-data pub/sub
└──────────────┬────────────────┘
               │
               ▼
┌───────────────────────────────┐
│ Worker  (worker.py)           │  owns the Time Tagger connection,
│                               │  runs each job in its own thread
└──────────────┬────────────────┘
               │  USB
               ▼
         Swabian Time Tagger
```

| Component | Code | Role |
|-----------|------|------|
| Web API | `main.py`, `app/api/*.py` | HTTP endpoints. Never talks to the Time Tagger |
| Auth middleware | `app/middleware/auth_middleware.py` | Checks the JWT on `/api/v1/*` and user-management routes |
| Audit route | `AuditRoute` in `app/api/audit_route.py` | Writes one line to `logs/audit.log` for every POST/PUT/DELETE |
| User store | `app/db/database.py` → `maas_auth.db` (SQLite) | Users and roles |
| StatusManager | `app/services/status_manager.py` | Measurement status and channel bookings in Redis |
| JobProcessor | `app/services/job_processor.py` | Queue push/pop, one thread per job, stop handling |
| Handlers | `app/services/*.py` | One class per measurement type, wrapping a Time Tagger measurement |
| FileLogger | `app/services/file_logger.py` | `request_logs/*.txt` and `logs/measurements/*.jsonl` |
| Worker | `worker.py` | Connects to the Time Tagger, registers handlers, pulls jobs |

**There must be exactly one worker.** The Time Tagger accepts a single software connection, so
a second worker (or Time Tagger Lab, or another script) cannot open the device. Measurements run
in parallel as threads inside that one worker.

### Measurement handlers

| Type (queue name) | Handler | Time Tagger class |
|-------------------|---------|-------------------|
| `count_rate`, `count_rate_live` | `CountRateMeasurementHandler`, `CountRateLiveMeasurementHandler` | `Counter` |
| `correlation` | `CorrelationMeasurementHandler` | `Correlation` |
| `coincidences` / `coincidence` | `CoincidencesMeasurementHandler` | `Coincidences` → `Counter` |
| `coincidences_live` / `coincidence_live` | `CoincidencesLiveMeasurementHandler` | `Coincidences` → `Counter` |
| `save_raw_tags` | `SaveRawTagsMeasurementHandler` | `FileWriter` |
| `startstop_live` | `StartStopLiveMeasurementHandler` | `StartStop` |
| `histogram_live` | `HistogramLiveMeasurementHandler` | `Histogram` |
| `correlation_live` | `CorrelationLiveMeasurementHandler` | `Correlation` |
| `set_parameters` | `SetParametersHandler` | `setTriggerLevel`, `setInputDelay` |

Handlers are registered only in `worker.py`. The web API just pushes job descriptions.

### Redis keys

| Key | Type | Content | Expiry |
|-----|------|---------|--------|
| `measurement:job_queue` | list | Pending jobs (JSON) | none |
| `measurement:status:{id}` | string | Status JSON | 1 h after last update (refreshed while running) |
| `measurement:metadata:{id}` | string | Request metadata | 1 h after creation (refreshed while running) |
| `measurement:results:{id}` | string | Result summary | 1 h after completion |
| `measurement:stop_channel` | pub/sub | IDs of measurements to stop (fast path) | – |
| `measurement:stop_requested:{id}` | string | Durable stop request, polled by the running job | 24 h, deleted once acknowledged |
| `measurement:stop_ack:{id}` | string | Worker's confirmation that a stopped job has ended | 1 h |
| `measurement:running` | hash | Jobs running on the worker: id → type, start time, pid | cleared at worker start |
| `measurement:data:{id}` | pub/sub | Live data updates | – |
| `channels:available`, `channels:booked`, `channels:booking_time` | set / hash / hash | Channel bookings | none |

---

## 2. Starting a measurement

```
GUI                Web API                         Redis                    Worker
 │ POST /count-rate   │                                │                        │
 │──────────────────▶ │ 1 check JWT                    │                        │
 │                    │ 2 validate body (422 if bad)   │                        │
 │                    │ 3 channels valid? (400)        │                        │
 │                    │   booked by user_name? (403)   │                        │
 │                    │ 4 create status = queued ────▶ │                        │
 │                    │ 5 RPUSH job_queue ───────────▶ │                        │
 │                    │ 6 log request to file          │                        │
 │ ◀── 201 {id} ──────│                                │                        │
 │                    │                                │ ◀── BLPOP (1 s) ───────│ 7
 │                    │                                │                        │ 8 new thread
 │                    │                                │ ◀── status = active ───│ 9
 │                    │                                │                        │ 10 run handler
 │                    │                                │ ◀── completed+results ─│ 11
```

1. **Auth** – the middleware rejects missing/invalid/expired tokens with 401.
2. **Validation** – the Pydantic model for the type (`app/models/measurements.py`) checks the body. Flat bodies
   without a `metadata` object are accepted and wrapped automatically.
3. **Channel check** – every channel must exist and be booked under `metadata.user_name`.
4. **Status** – a UUID is generated and stored as `queued`.
5. **Enqueue** – the job JSON goes onto `measurement:job_queue`.
6. **Request log** – one line in `request_logs/measurement_requests.txt`.
7. **Dequeue** – the worker polls the queue every second.
8. **Thread** – `JobProcessor.process_job` starts a thread named `job-<id>`.
9. **Active** – status becomes `active`; `started_at` is reset to this moment.
10. **Run** – placeholders in `target_location` are filled in, the metadata is validated again,
    and the handler runs the Time Tagger measurement for `duration_seconds` (or until stopped for
    live types). File-based types write their output file at the end.
11. **Finish** – status becomes `completed` with a result summary, or `failed` with the error in
    `message`.

Every status change is also appended to `logs/measurements/measurement_status_log.jsonl`.

Channels are **not** released at the end; see
[CHANNEL_MANAGEMENT_GUIDE.md](CHANNEL_MANAGEMENT_GUIDE.md).

---

## 3. Status query

`GET /api/v1/measurements/{id}/status` reads the status, metadata and results keys from Redis and
adds `duration_so_far` (seconds since `started_at`). It never touches the worker. After the keys
expire it returns 404.

---

## 4. Stopping

```
DELETE /measurements/{id}
  Web API: status queued/active? → SET measurement:stop_requested:<id>
                                 → set status = stopped
                                 → PUBLISH measurement:stop_channel <id>
                                 → wait up to STOP_ACK_TIMEOUT_SECONDS (3 s)
                                   for measurement:stop_ack:<id>
  Worker:  stop listener receives <id>          ─┐ whichever comes first
           job's watcher sees the stop flag     ─┘ (polled every 0.5 s)
           → handler.stop()
           → stops the Time Tagger measurement
           → deletes the output file written so far (count-rate, correlation,
             coincidences, save-raw-tags)
           → job thread ends → SET measurement:stop_ack:<id>
```

- Pub/sub is fire-and-forget, so the stop flag is what guarantees the stop: a
  message sent while the job is starting up, or while the worker is
  reconnecting to Redis, used to be lost and the job ran to its full duration.
- The response's `stop_acknowledged` is `true` once the worker confirmed the
  job ended, `false` if it didn't within the timeout (worker down or busy; the
  job still stops when a worker sees the flag). It is `null` when there was
  nothing to stop.
- A job stopped while still `queued` is skipped when the worker picks it up
  (and acknowledged then).
- If the measurement already finished, the call just returns its current status.
- The worker never overwrites `stopped` with `completed`.
- Channels stay booked.
- `python scripts/find_running_measurements.py` lists measurements that are
  still streaming data, with their status, to track down one that didn't stop.

---

## 5. Live data

Live handlers publish a JSON update to `measurement:data:{id}` at `refresh_rate` Hz. The web API's
WebSocket endpoint `/api/v1/measurements/stream/{id}` subscribes to that channel and forwards every
message to the client. The WebSocket checks the same JWT (header or `?token=`) and closes with
code 1008 if it is missing or invalid.

The live data is not stored; a client that connects late only sees updates from that point on.

---

## 6. Releasing channels

`POST /api/v1/channels/release/{user}` frees the channels in Redis and then enqueues a
`set_parameters` job that sets them back to 0.5 V trigger and 0 ps delay. The ID of that job is
returned as `parameter_reset_id`.

---

## 7. Worker startup and Redis loss

On startup the worker:

1. Connects to Redis and checks it with `PING`.
2. Opens the Time Tagger (`createTimeTagger()`), switches its built-in test signal off, sets the
   trigger level of channels 12 and 16 to 0 V, and publishes every channel's trigger level and
   delay for `GET /api/v1/channels/parameters`.
3. Registers the handlers and starts polling the queue.

If Redis becomes unreachable, the worker retries with exponential backoff (up to 5 times) and exits
if it still can't connect.

On `Ctrl+C` the worker stops all running jobs and closes Redis; the web API closes its Redis
connection and stops within 5 seconds even if WebSocket clients are still connected.

---

## 8. Tracing one request

1. Take the `measurement_id` from the response or from `request_logs/measurement_requests.txt`.
2. Search the logs for it:
   ```bash
   grep -r "<measurement_id>" logs request_logs
   ```
   - `logs/services/main.log` – received, validated, enqueued
   - `logs/services/worker.log` – picked up, started, finished or failed (with stack trace)
   - `logs/measurements/measurement_status_log.jsonl` – each status change with timestamp
3. Look at Redis directly (while the keys still exist):
   ```bash
   redis-cli GET measurement:status:<measurement_id>
   redis-cli LLEN measurement:job_queue
   ```
   A growing `LLEN` means the worker isn't picking jobs up.

`logs/audit.log` records each POST/PUT/DELETE with user ID, role, path, the HTTP status the client
received, and the error message. For a stop request, `target_hardware_id` is the measurement ID.
