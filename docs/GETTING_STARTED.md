# MaaS – Getting Started & Troubleshooting

A short guide for running the MaaS (Measurements as a Service) backend and fixing common problems.
Day-to-day measurements are done through the **MaaS GUI**; this guide covers starting the service
the GUI talks to, and what to check when something goes wrong.

---

## 1. Run the service

MaaS needs **three things running** on the measurement PC:

| Piece | What it does | How you start it |
|-------|--------------|------------------|
| **Redis** | Holds measurement status, channel bookings and the job queue | `memurai` (or the Redis Windows service) |
| **Web API** (`main.py`) | Receives requests from the GUI on **http://localhost:8000** | `python main.py` |
| **Worker** (`worker.py`) | Connects to the Time Tagger and actually runs the measurements | `python worker.py` |

If the worker is not running, requests are accepted but measurements stay in `queued` forever.

## 2. Starting the service

Open three terminals in the MaaS folder, in this order:

**Terminal 1 – Redis** (should be already running on the main PC)

```bash
start-service memurai
```

**Terminal 2 – Web API**

```bash
python main.py
```

Wait for `Web API layer initialized successfully`.

**Terminal 3 – Worker** (with the Time Tagger connected by USB)

```bash
python worker.py
```

### Check it is up

Open **http://localhost:8000/health** in a browser. You should see `"status": "healthy"` and
`"redis": "healthy"`. The interactive API page is at **http://localhost:8000/docs**.

### Stopping

Press `Ctrl+C` in the worker and Web API terminals. Running measurements are stopped and
**their partial data files are deleted**, so stop the service only when nobody is measuring.

---

## 3. Logging in

- First start creates a default account: **username `admin`, password `admin`**. Change it after
  the first login (from the GUI, or `PUT /auth/password`).
- Accounts created by an admin start with **password = username**; ask the user to change it.
- A login is valid for **1 week**. After that, requests fail with `Token expired` – log in again.

---

## 4. How a measurement flows (what to expect)

1. **Book channels** – you can only measure on channels booked under *your* username.
   Valid channels: `1–16`, `101–116`, `201–216`.
2. **Start a measurement** – you get back a `measurement_id` (a UUID). Keep it; every log line
   about that measurement contains it.
3. **Status** moves through: `queued` → `active` → `completed`
   (or `stopped` if you stopped it, `failed` if something went wrong – the status `message`
   says why).
4. **Results** are saved as a CSV file `~/Desktop/MaasData/<YYYYMMDD_HHMMSS>/<measurement-type>`
   unless a different target location was given. Stopping a measurement early **deletes** its
   file.
5. **Release channels** when done so others can use them. Channels are never released
   automatically.

---

## 5. Where to look: logs

All paths are relative to the MaaS folder.

| File | What's in it | Look here when… |
|------|--------------|-----------------|
| `logs/services/main.log` | Everything the Web API does, incl. errors with stack traces | A request from the GUI fails |
| `logs/services/worker.log` | Time Tagger connection and measurement execution | A measurement fails or never starts |
| `logs/measurements/measurement_status_log.jsonl` | One JSON line per status change of every measurement | You want the history of one measurement |
| `logs/audit.log` | One JSON line per create/stop/book/release call: who, what, HTTP status | You need to know who did what, or why a call was rejected |
| `request_logs/measurement_requests.txt` | Table of every measurement started, with its parameters | Checking what settings a measurement used |
| `request_logs/channel_requests.txt` | Table of every channel book / release | Finding out who holds a channel |

**Tracking one measurement:** search all logs for its `measurement_id`:

```bash
grep -r "<measurement_id>" logs request_logs
```

PowerShell:

```powershell
Get-ChildItem logs, request_logs -Recurse -File | Select-String "<measurement_id>"
```

**More detail:** set `LOG_LEVEL=DEBUG` before starting the API/worker
(PowerShell: `$env:LOG_LEVEL="DEBUG"`; bash: `export LOG_LEVEL=DEBUG`).

---

## 6. Troubleshooting

### The service won't start

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `Error 10061` / `Connection refused` to Redis, or `/health` shows `"redis": "unhealthy"` | Redis is not running | Start Redis (`Start-Service memurai`); check with `memurai-cli ping` (should answer `PONG`) |
| `ModuleNotFoundError: No module named 'Swabian'` (worker) | Time Tagger software not installed, or a different Python is being used | Install the Swabian software; make sure `python` is the same interpreter it was installed for |
| `ModuleNotFoundError` for anything else | Dependencies missing | `pip install -r requirements.txt` |
| Worker exits right after `Initializing TimeTagger...` | Time Tagger not plugged in, or already opened by another program (Time Tagger Lab, a Python script, a second worker) | Plug it in / close the other program, then restart the worker. Only one program can use the device at a time |
| `address already in use` / `Errno 10048` | Another copy of the API is already running on port 8000 | Close the other copy (or find it with `netstat -ano \| findstr :8000`) |

### Requests fail

| Error | Meaning | Fix |
|-------|---------|-----|
| `401 Not authenticated` / `Invalid token` | Not logged in, or the GUI is using an old token | Log in again |
| `401 Token expired` | Login is older than 1 week | Log in again |
| `403 Channel X is not booked by user '…'` | Measurement uses a channel you haven't booked | Book the channel first |
| `403 You can only book channels under your own username` | `user_name` in the request differs from the logged-in user | Use your own username |
| `409 Cannot book channels [...] - already booked` | Someone else holds the channel | Check `request_logs/channel_requests.txt` or the channel list in the GUI; ask them to release it (admins can release anyone's channels) |
| `400 Invalid channel` | Channel number outside `1–16`, `101–116`, `201–216` | Use a valid channel |
| `404 Measurement '…' not found` | Wrong ID, or Redis was restarted/cleared | Check the ID in `request_logs/measurement_requests.txt` |
| `422` with `Field required` / `missing` errors | A required parameter is missing or has the wrong type | Read the message – it names the missing field |
| `500` | Unexpected server error | Find the error and stack trace in `logs/services/main.log` |

### Measurements misbehave

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| Status stuck at `queued` | Worker not running | Start `python worker.py` |
| Measurement runs but all counts are zero | No signal on those inputs | Check the detector cabling and that you booked the channels the detectors are connected to |
| `failed` for another reason | See the status `message` | Look up the `measurement_id` in `logs/services/worker.log` for the full error |

### Forgot the admin password

Another admin can reset it. If there is no other admin, stop the service, delete (or rename)
`maas_auth.db`, and start again: the default `admin` / `admin` account is recreated.
**This removes all other user accounts.**

---

## 7. Further reading

**MaaS documentation** (in this repository)

- [README.md](../README.md) – project overview
- [README_USER_GUIDE.md](README_USER_GUIDE.md) – full API usage, measurement types and their parameters
- [CHANNEL_MANAGEMENT_GUIDE.md](CHANNEL_MANAGEMENT_GUIDE.md) – channel booking rules in detail
- [README_SYSTEM_FLOW.md](README_SYSTEM_FLOW.md) – how a request travels through the system
- [README_DEVELOPER_GUIDE.md](README_DEVELOPER_GUIDE.md) – development setup, tests, adding measurement types
- [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) – deployment steps and checks
- http://localhost:8000/docs – live, interactive list of every endpoint (while the service runs)

**Swabian Instruments Time Tagger**

- [Documentation home](https://www.swabianinstruments.com/static/documentation/TimeTagger/index.html)
- [Installation](https://www.swabianinstruments.com/static/documentation/TimeTagger/gettingStarted/installation.html)
- [API reference](https://www.swabianinstruments.com/static/documentation/TimeTagger/api/index.html)
- Measurement classes used by MaaS:
  [Counter](https://www.swabianinstruments.com/static/documentation/TimeTagger/api/measurements/event_counting.html#counter) ·
  [Correlation, Histogram, StartStop](https://www.swabianinstruments.com/static/documentation/TimeTagger/api/measurements/time_histograms.html) ·
  [FileWriter](https://www.swabianinstruments.com/static/documentation/TimeTagger/api/measurements/time_tag_streaming.html#filewriter) ·
  [Coincidences (virtual channel)](https://www.swabianinstruments.com/static/documentation/TimeTagger/api/VirtualChannels.html#coincidences)
