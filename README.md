# MaaS – Measurements as a Service

MaaS lets several users share one Swabian Instruments Time Tagger over HTTP. Users log in, book
input channels, and start measurements (count rate, correlation, coincidences, raw time-tag
recording, and live histograms). The service returns right away with a measurement ID, runs the
measurement in the background, and saves the data to a file or streams it live.

Most users work through the **MaaS GUI**, which calls this service.

---

## Quick start

**Requirements:** Python 3.10+, the Swabian Time Tagger software, Redis (Memurai on Windows) on
`127.0.0.1:6379`, and the Time Tagger connected by USB.

```bash
pip install -r requirements.txt
```

Start the web API and the worker in two terminals from this folder:

```bash
python main.py
```

```bash
python worker.py
```

Then open http://localhost:8000/health (should say `healthy`) or the interactive API page at
http://localhost:8000/docs. The first start creates the login `admin` / `admin`; change it
straight away.

`run.bat` / `run.sh` install the dependencies and start the web API only; start the worker
separately.

Full instructions and troubleshooting: **[docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)**.

---

## How it fits together

```
MaaS GUI ──HTTP/WebSocket──▶ Web API (main.py) ──▶ Redis ──▶ Worker (worker.py) ──USB──▶ Time Tagger
```

- **Web API** checks the login, validates the request, checks that the channels are booked by the
  user, and queues the job.
- **Redis** holds the job queue, measurement status, channel bookings, and live data.
- **Worker** owns the Time Tagger connection and runs each measurement in its own thread. Run
  exactly one.

A typical session: log in → book channels → start measurements → poll status or watch the live
stream → release channels. Channels are never booked or released automatically.

---

## Documentation

| Document | For | Contents |
|----------|-----|----------|
| [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) | Everyone | Start the service, find logs, fix common errors |
| [docs/README_USER_GUIDE.md](docs/README_USER_GUIDE.md) | API users | Login, channels, every measurement type and its fields, status, live data, errors |
| [docs/CHANNEL_MANAGEMENT_GUIDE.md](docs/CHANNEL_MANAGEMENT_GUIDE.md) | API users, admins | Booking rules and permissions |
| [docs/README_SYSTEM_FLOW.md](docs/README_SYSTEM_FLOW.md) | Developers | Components, request flow, Redis keys, stopping, live data |
| [docs/README_DEVELOPER_GUIDE.md](docs/README_DEVELOPER_GUIDE.md) | Developers | Code layout, tests, debugging, adding a measurement type |
| [docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md) | Admins | Setting up and updating the measurement PC |

Swabian Time Tagger documentation:
[home](https://www.swabianinstruments.com/static/documentation/TimeTagger/index.html) ·
[API reference](https://www.swabianinstruments.com/static/documentation/TimeTagger/api/index.html)

---

## Measurement types

| Endpoint (`POST /api/v1/measurements/…`) | What it does | Output |
|------------------------------------------|--------------|--------|
| `count-rate` | Counts per channel over time | CSV file |
| `correlation` | Time-difference histogram between two channels | CSV file |
| `coincidences` | Coincidence counts for groups of channels | CSV file |
| `save-raw-tags` | Records every time tag | `.ttbin` file |
| `count-rate-live`, `coincidences-live` | As above, streamed | WebSocket |
| `histogram-live`, `startstop-live`, `correlation-live` | Live time histograms | WebSocket |

`POST /api/v1/set-parameters` changes a channel's trigger level and input delay. Fields and
examples are in the [user guide](docs/README_USER_GUIDE.md).

---

## Project layout

```
main.py            web API entry point
worker.py          worker entry point (Time Tagger)
app/api/           HTTP endpoints and login
app/services/      job queue, status and channel storage, logging
app/models/        request and response models
app/handlers/      one measurement handler per type (run by the worker)
tests/             pytest suite (runs without Redis or a Time Tagger)
scripts/           manual hardware smoke checks (need a real Time Tagger)
docs/              documentation
logs/, request_logs/   created at runtime
```

---

## Tests

```bash
pytest
```

The suite mocks Redis and the Time Tagger and checks that it writes nothing into the repository
or into `~/Desktop/MaasData`. Each test has a 30-second timeout.
