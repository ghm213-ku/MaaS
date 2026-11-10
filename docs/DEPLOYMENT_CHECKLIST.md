# Deployment Checklist

Use this list when setting MaaS up on the measurement PC, or after updating it. MaaS runs on
**one PC**, the one the Time Tagger is plugged into: one Redis, one web API, one worker.

For day-to-day starting and troubleshooting see [GETTING_STARTED.md](GETTING_STARTED.md).

---

## 1. Install

- [ ] Python 3.10+ on `PATH` (`python --version`)
- [ ] Swabian Time Tagger software installed for that same Python:
      `python -c "from Swabian import TimeTagger; print('OK')"`
- [ ] Redis running on `127.0.0.1:6379`. On Windows this is Memurai:
      `Get-Service memurai` shows `Running`, and the service start type is **Automatic**
- [ ] Dependencies installed from the MaaS folder: `pip install -r requirements.txt`
- [ ] Time Tagger connected by USB and **not** open in Time Tagger Lab or another program

## 2. Before first use

- [ ] Run the test suite (needs neither Redis nor the Time Tagger): `pytest`
- [ ] Set a JWT secret: either set the `JWT_SECRET` environment variable, or delete `.jwt_secret`
      so a new random one is created on first start. Do not reuse the secret from the repository
- [ ] Start the service once (section 3), log in as `admin` / `admin` and **change the password**
      (GUI, or `PUT /auth/password`)
- [ ] Create a user account for each person (`POST /auth/users`, admin only). New accounts start
      with password = username; each user changes it on first login
- [ ] Decide who can reach port 8000. The API listens on all network interfaces over plain HTTP
      (no TLS). If the GUI runs on the same PC, block port 8000 for other machines in Windows
      Firewall; otherwise allow only the GUI machines
- [ ] Turn on Redis persistence (snapshotting) if channel bookings should survive a reboot.
      Measurement status is short-lived anyway (1 hour)

## 3. Start

In the MaaS folder, in this order:

```bash
python main.py
```

```bash
python worker.py
```

- [ ] `main.py` logs `Web API layer initialized successfully`
- [ ] `worker.py` logs `Backend worker started`
- [ ] Start the worker **without** `--testing` or `--no-hardware` (those are for development only)
- [ ] Start **only one worker**. The Time Tagger allows one connection, and measurements already
      run in parallel inside the worker
- [ ] Start **only one web API process** (no `--workers N`, no gunicorn with several workers): the
      app keeps its state in one process

## 4. Verify

- [ ] `http://localhost:8000/health` shows `"status": "healthy"` and `"redis": "healthy"`
- [ ] Log in from the GUI
- [ ] Book a channel, run a short count-rate measurement, see it reach `completed`, and find the
      CSV under `~/Desktop/MaasData/<YYYYMMDD_HHMMSS>/`
- [ ] Release the channel; `GET /api/v1/channels/available` shows it free again
- [ ] `logs/services/main.log`, `logs/services/worker.log` and `logs/audit.log` are being written

## 5. After updating the code

- [ ] Stop the worker and the API (`Ctrl+C`). **Any running measurement is stopped and its partial
      data file deleted**, so wait until nobody is measuring
- [ ] `git pull`, then `pip install -r requirements.txt`
- [ ] `pytest`
- [ ] Start again (section 3) and verify (section 4)

Restarting does not affect users, channel bookings or the queue: these live in `maas_auth.db` and
Redis.

## 6. Housekeeping

| What | Where | Notes |
|------|-------|-------|
| Measurement data | `~/Desktop/MaasData/` (default) | Never deleted by MaaS; archive or clean up yourself |
| Service logs | `logs/services/*.log` | Grow without limit; rotate or truncate periodically |
| Status history | `logs/measurements/measurement_status_log.jsonl` | Grows without limit |
| Request logs | `request_logs/*.txt` | Grow without limit |
| Audit log | `logs/audit.log` | Rotates automatically (10 × 50 MB) |
| Users | `maas_auth.db` | Back this file up; deleting it resets to just `admin` / `admin` |
| Stale channel bookings | `GET /api/v1/channels/available` | An admin can release any user's channels |

## 7. If something breaks

| Problem | Action |
|---------|--------|
| API down | Restart `python main.py`. Status, bookings and queued jobs are in Redis and are kept |
| Worker down | Restart `python worker.py`. Queued jobs are picked up; jobs that were running are lost and stay `active` until their status expires (1 hour) |
| Redis down | Start Memurai (`Start-Service memurai`), then restart the worker (it gives up after 5 reconnect attempts) |
| Time Tagger not found | Check USB, close other Time Tagger software, restart the worker |

More symptoms and fixes: [GETTING_STARTED.md](GETTING_STARTED.md#6-troubleshooting).
