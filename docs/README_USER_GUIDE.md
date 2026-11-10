# MaaS API User Guide

This guide describes the MaaS HTTP API: how to log in, book channels, start and stop
measurements, and read their status. Most users drive MaaS through the **MaaS GUI**, which makes
these calls for you; read this guide if you script against the API directly or want to understand
what the GUI is doing.

To start the service and fix common problems, see [GETTING_STARTED.md](GETTING_STARTED.md).

- Base URL: `http://localhost:8000`
- Interactive API docs (every endpoint and schema): `http://localhost:8000/docs`

---

## 1. Workflow at a glance

1. **Log in** → get a token.
2. **Book** the channels you need under your username.
3. **Start** a measurement → get a `measurement_id`.
4. **Poll** its status (or stream live data over WebSocket).
5. **Stop** it early if needed.
6. **Release** your channels when you are done.

Channels are **never** booked or released automatically. They stay booked after a measurement
completes, stops or fails, until you release them.

---

## 2. Log in

```bash
curl -X POST http://localhost:8000/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "alice", "password": "secret"}'
```

```json
{ "token": "eyJhbGciOi...", "expires_in": 604800 }
```

Send the token on every `/api/v1/...` call:

```
Authorization: Bearer <token>
```

The token is valid for 1 week (`expires_in` is in seconds). `/health`, `/docs` and
`/auth/login` do not need a token.

The examples below assume `TOKEN` holds your token:

```bash
TOKEN=eyJhbGciOi...
```

### Account endpoints

| Endpoint | Who | Purpose |
|----------|-----|---------|
| `POST /auth/login` | anyone | Get a token |
| `PUT /auth/password` | any logged-in user | Change your own password (`old_password`, `new_password`) |
| `POST /auth/users` | admin | Create a user (`username`, `role_id`). Initial password = username |
| `DELETE /auth/users/{username}` | admin | Delete a user |
| `PUT /auth/users/{username}/password` | admin | Reset a user's password (`new_password`) |

Roles: `admin`, `operator`, `viewer`. At the moment all roles can use every `/api/v1` endpoint;
only the user-management endpoints are limited to admins.

---

## 3. Channels

There are **48 channels**: `1–16`, `101–116`, `201–216`. Each channel can be booked by one user at
a time, and a measurement can only use channels booked under the `user_name` it sends.

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/channels/` | GET | Every channel with its status, owner and booking time |
| `/api/v1/channels/available` | GET | Counts, free channel numbers, and which user holds which channels |
| `/api/v1/channels/parameters` | GET | Current trigger voltage and input delay of each channel |
| `/api/v1/channels/book` | POST | Book channels under your own username |
| `/api/v1/channels/release/{user_name}` | POST | Release some of a user's channels |

**Book:**

```bash
curl -X POST http://localhost:8000/api/v1/channels/book \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"user_name": "alice", "channel_numbers": [1, 2]}'
```

**Release** (the listed channels must all be booked by that user, otherwise nothing is released):

```bash
curl -X POST http://localhost:8000/api/v1/channels/release/alice \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"channel_numbers": [1, 2]}'
```

Releasing also resets those channels to **trigger 0.5 V / delay 0 ps**. The response contains
`parameter_reset_id`, the ID of that reset job, which you can poll like a measurement.

| Rule | Normal user | Admin |
|------|-------------|-------|
| Book | Only under your own username | Only under your own username |
| Release | Only your own channels | Any user's channels |

For more detail see [CHANNEL_MANAGEMENT_GUIDE.md](CHANNEL_MANAGEMENT_GUIDE.md).

---

## 4. Measurements

All measurement endpoints are `POST /api/v1/measurements/<type>` and take:

```json
{
  "duration_seconds": 10,
  "metadata": { "user_name": "alice", "...": "type-specific fields" }
}
```

`metadata.user_name` is **required** for every type and must own all channels used.
The response (HTTP 201) is:

```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "queued",
  "started_at": "2026-11-10T10:00:00",
  "message": "Count-rate measurement queued with channels [1, 2]. Use ID '...' to query status or stop."
}
```

### Measurement types

Times (`binwidth`, `coincidence_window`, `input_delay`) are in **picoseconds**.

| Endpoint | Required metadata | Optional metadata (default) | Saves a file |
|----------|------------------|-----------------------------|--------------|
| `count-rate` | `channels` | `binwidth` (1e9 = 1 s), `n_values` (1), `target_location` | yes |
| `correlation` | `channel1`, `channel2` | `binwidth` (1000), `n_values` or `n_bins` (1000), `target_location` | yes |
| `coincidences` (alias `coincidence`) | `coincidences` (list of lists, e.g. `[[1, 2], [2, 3, 5]]`) | `coincidence_window` (1000), `timestamp` (`Last`), `binwidth` (1e9), `n_values` (1), `target_location` | yes |
| `save-raw-tags` | `channel_list`, `target_file_path` | – | yes (`.ttbin`) |
| `count-rate-live` | `channels` | `binwidth` (1e9), `n_values` (1), `refresh_rate` (25 Hz) | no, streams |
| `coincidences-live` (alias `coincidence-live`) | `coincidences` | as `coincidences`, plus `refresh_rate` (25 Hz) | no, streams |
| `histogram-live` | `start_channel`, `click_channel` | `binwidth` (1000), `n_bins` (1000), `refresh_rate` (25 Hz) | no, streams |
| `startstop-live` | `start_channel`, `click_channel` | `binwidth` (1000), `refresh_rate` (25 Hz) | no, streams |
| `correlation-live` | `channel1`, `channel2` | `binwidth` (1000), `n_bins` (1000), `refresh_rate` (25 Hz) | no, streams |

Notes:

- **`duration_seconds`** is required for `count-rate`, `correlation`, `coincidences` and
  `save-raw-tags`. For `count-rate-live` and `coincidences-live` it is optional: omit it to stream
  until stopped. `histogram-live`, `startstop-live` and `correlation-live` always run until stopped.
- **Coincidences** must be a list of lists; a flat list like `[1, 2]` is rejected. `channels` and
  `coincidence_groups` are accepted as other names for `coincidences`, and `coincidenceWindow` for
  `coincidence_window`. `timestamp` is one of `Last`, `First`, `ListedFirst`, `Average`.

### Example: count rate

```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 10,
    "metadata": {
      "user_name": "alice",
      "channels": [1, 2],
      "binwidth": 1000000000,
      "n_values": 10
    }
  }'
```

### Example: save raw tags

```bash
curl -X POST http://localhost:8000/api/v1/measurements/save-raw-tags \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 30,
    "metadata": {
      "user_name": "alice",
      "channel_list": [1, 2],
      "target_file_path": "C:\\data\\run_001.ttbin"
    }
  }'
```

### Where results are saved

`target_location` (and `target_file_path`) is a **file path** on the PC running the worker.
Placeholders:

- `{datetime}` → start time as `YYYYMMDD_HHMMSS`, e.g. `20261110_143045`
- `{measurement-type}` → e.g. `count_rate`
- `~` → the home folder of the user running the worker

The default is `~/Desktop/MaasData/{datetime}/{measurement-type}`, which gives a CSV file such as
`C:\Users\<you>\Desktop\MaasData\20261110_143045\count_rate`. If the path is an existing folder or
ends with `/` or `\`, a file named `<type>_<datetime>.csv` (`.ttbin` for raw tags) is created
inside it. Missing folders are created.

### Changing channel settings

`POST /api/v1/set-parameters` sets the trigger voltage and/or input delay of booked channels:

```bash
curl -X POST http://localhost:8000/api/v1/set-parameters \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"metadata": {"user_name": "alice", "channels": [1, 2], "trigger_voltage": 0.5, "input_delay": 1000}}'
```

It runs as a short job with its own `measurement_id`.

---

## 5. Status

```bash
curl http://localhost:8000/api/v1/measurements/<measurement_id>/status \
  -H "Authorization: Bearer $TOKEN"
```

```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "completed",
  "started_at": "2026-11-10T10:00:00.120000",
  "duration_so_far": 10.4,
  "metadata": { "user_name": "alice", "channels": [1, 2], "...": "..." },
  "results": { "status": "completed", "total_count": 123456, "...": "..." },
  "message": "count_rate measurement completed successfully"
}
```

| Status | Meaning |
|--------|---------|
| `queued` | Accepted, waiting for the worker. Stays here if the worker is not running |
| `active` | Running on the Time Tagger |
| `completed` | Finished; `results` holds a summary (counts, duration) and the data is in the saved file |
| `stopped` | Stopped by a `DELETE` request |
| `failed` | Something went wrong; `message` says what |

`results` is a short summary; its fields depend on the measurement type. The full data is in the
saved file, or in the live stream.

Status is kept for **1 hour after its last update**, then a status query returns 404. The request
logs keep a permanent record (see [GETTING_STARTED.md](GETTING_STARTED.md#5-where-to-look-logs)).

---

## 6. Stopping a measurement

```bash
curl -X DELETE http://localhost:8000/api/v1/measurements/<measurement_id> \
  -H "Authorization: Bearer $TOKEN"
```

- A `queued` or `active` measurement becomes `stopped`.
- **Any data file it has already written is deleted.** Use a shorter `duration_seconds` instead
  of stopping early if you want to keep the data.
- Channels stay booked; release them separately.
- Calling it on a measurement that has already finished returns its current status and changes
  nothing.

---

## 7. Live data (WebSocket)

Live measurements publish updates at `refresh_rate` to:

```
ws://localhost:8000/api/v1/measurements/stream/<measurement_id>
```

Authenticate with an `Authorization: Bearer <token>` header or, if your client can't set headers,
`?token=<token>`. Without a valid token the connection is closed with code 1008.

Each message is a JSON object with `type`, `status_id`, `timestamp` and:

| Type | Fields |
|------|--------|
| `count_rate` (count-rate-live) | `data`: counts per channel for the last `n_values` bins; `final`: `true` on the last update of a timed run |
| `histogram_live`, `startstop_live`, `correlation_live` | `data`: counts per bin; `index`: bin times in ps |
| `coincidences_live` | `streams`: one entry per coincidence group with `coincidence`, `virtual_channel`, `rate` (latest bin, counts/s) and `data` (last `n_values` bins) |

---

## 8. Errors

Errors return JSON with a `detail` field.

| HTTP | Typical `detail` | Cause |
|------|------------------|-------|
| 400 | `Invalid channel numbers: [999]. Valid channels: [...]` | Channel outside 1–16, 101–116, 201–216 |
| 401 | `Not authenticated` / `Invalid token` / `Token expired` | Missing, bad or expired token |
| 401 | `Invalid credentials` | Wrong username or password at login |
| 403 | `Channel 3 is not booked by user 'alice'` | Measurement uses a channel you haven't booked |
| 403 | `You can only book channels under your own username` | `user_name` differs from the logged-in user |
| 403 | `You can only release your own channels` | Non-admin releasing someone else's channels |
| 404 | `Measurement '...' not found` | Wrong ID, or status already expired (1 hour) |
| 409 | `Cannot book channels [1, 2] - already booked` | Another user holds the channel |
| 409 | `Cannot release channels [5] - not booked by alice` | Releasing channels the user doesn't hold |
| 422 | List of `Field required` / type errors | Missing or wrongly typed field in the request body |
| 500 | Error text | Unexpected server error, see `logs/services/main.log` |

---

## 9. Python example

```python
import time
import requests

BASE = "http://localhost:8000"
USER = "alice"

token = requests.post(f"{BASE}/auth/login",
                      json={"username": USER, "password": "secret"}).json()["token"]
s = requests.Session()
s.headers["Authorization"] = f"Bearer {token}"

s.post(f"{BASE}/api/v1/channels/book",
       json={"user_name": USER, "channel_numbers": [1, 2]}).raise_for_status()
try:
    r = s.post(f"{BASE}/api/v1/measurements/count-rate", json={
        "duration_seconds": 10,
        "metadata": {"user_name": USER, "channels": [1, 2], "n_values": 10},
    })
    r.raise_for_status()
    mid = r.json()["measurement_id"]

    while True:
        st = s.get(f"{BASE}/api/v1/measurements/{mid}/status").json()
        if st["status"] in ("completed", "stopped", "failed"):
            break
        time.sleep(1)
    print(st["status"], st["message"], st["results"])
finally:
    s.post(f"{BASE}/api/v1/channels/release/{USER}",
           json={"channel_numbers": [1, 2]})
```
