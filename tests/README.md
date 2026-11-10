# Tests

The suite runs without Redis or a Time Tagger: `conftest.py` replaces `Swabian` with a mock,
patches Redis with `fakeredis`, and points the user database, logs and `~` at a temporary sandbox.
After every test it checks that nothing in the repository or the real `~/Desktop/MaasData` changed.

## Layout

The folders mirror the `app/` packages:

| Folder | Covers |
|--------|--------|
| `api/` | HTTP and WebSocket endpoints, login and auth middleware, the GUI request/response contract |
| `handlers/` | measurement handlers against the mocked Time Tagger, including Swabian API conformance |
| `models/` | request/metadata validation, flat payloads, the measurement-type registry |
| `services/` | job processor, status manager, file logger |
| `integration/` | web layer → Redis → job processor → handler, end to end |
| `test_worker.py` | worker start-up (test signal, `--no-hardware`, flags) |

## Running

```bash
pytest                                   # everything (settings in pytest.ini)
```

```bash
pytest tests/handlers                    # one area
```

```bash
pytest -k coincidences                   # by name
```

```bash
pytest --cov=app --cov-report=term-missing
```

Every test has a 30-second limit (`pytest-timeout`); on Windows a timeout aborts the whole run,
so keep measurement durations in tests short.

See [docs/README_DEVELOPER_GUIDE.md](../docs/README_DEVELOPER_GUIDE.md) for adding tests with a
new measurement type.
