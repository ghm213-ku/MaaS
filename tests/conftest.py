"""Pytest configuration and shared fixtures."""

import pytest
import asyncio
import sys
import os
from pathlib import Path

# Add the project root to the path (for safety)
project_root = str(Path(__file__).parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# ---------------------------------------------------------------------------
# Test isolation: tests must never touch the live DB, live log folders, the
# repo working tree, or the real ~/Desktop/MaasData.
#
# Everything below runs at conftest import, i.e. BEFORE any test module imports
# the app, because several app modules write at import time (DB init, audit
# log handler, main.py's root log file, the .jwt_secret file).
# ---------------------------------------------------------------------------
import logging
import shutil
import sqlite3
import tempfile
import time

_REAL_HOME = Path(os.path.expanduser("~"))
_SANDBOX = Path(tempfile.mkdtemp(prefix="maas_tests_"))
_SANDBOX_HOME = _SANDBOX / "home"
_SANDBOX_HOME.mkdir()

os.environ["MAAS_DB_PATH"] = str(_SANDBOX / "maas_auth_test.db")
os.environ["MAAS_LOGS_DIR"] = str(_SANDBOX / "logs")
os.environ["JWT_SECRET"] = "test-only-jwt-secret-not-used-in-production"
# expanduser("~") is used for the default ~/Desktop/MaasData target location
os.environ["HOME"] = os.environ["USERPROFILE"] = str(_SANDBOX_HOME)


# Locations that must be byte-for-byte unchanged after every test.
_GUARDED_ROOTS = [Path(project_root), _REAL_HOME / "Desktop" / "MaasData"]
_GUARD_SKIP_DIRS = {".git", "__pycache__", ".pytest_cache"}
_GUARD_SKIP_FILES = {".coverage", "coverage.xml"}


def _snapshot_tree(root: Path) -> dict:
    """Map every path under root to (size, mtime) so any write is detectable."""
    snap = {}
    if not root.exists():
        return snap
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _GUARD_SKIP_DIRS]
        for d in dirnames:
            snap[os.path.join(dirpath, d)] = "dir"
        for f in filenames:
            if f in _GUARD_SKIP_FILES:
                continue
            p = os.path.join(dirpath, f)
            try:
                st = os.stat(p)
                snap[p] = (st.st_size, st.st_mtime_ns)
            except OSError:
                pass
    return snap


def _diff_snapshots(before: dict, after: dict) -> list:
    changes = [f"created:  {p}" for p in after.keys() - before.keys()]
    changes += [f"deleted:  {p}" for p in before.keys() - after.keys()]
    changes += [f"modified: {p}" for p in before.keys() & after.keys() if before[p] != after[p]]
    return sorted(changes)


def _rmtree_with_retry(path: Path, attempts: int = 10) -> None:
    """Remove a directory, retrying briefly for Windows file-lock races."""
    for i in range(attempts):
        try:
            shutil.rmtree(path)
            return
        except FileNotFoundError:
            return
        except OSError:
            if i == attempts - 1:
                raise
            time.sleep(0.1)


def _close_sandbox_log_handlers() -> None:
    """Close file handlers pointing into the sandbox so it can be deleted."""
    loggers = [logging.getLogger()] + [
        lg for lg in logging.Logger.manager.loggerDict.values() if isinstance(lg, logging.Logger)
    ]
    for lg in loggers:
        for h in list(lg.handlers):
            if str(getattr(h, "baseFilename", "")).startswith(str(_SANDBOX)):
                h.close()
                lg.removeHandler(h)


@pytest.fixture(scope="session", autouse=True)
def _session_sandbox():
    """Verify isolation is active and run tests from inside the sandbox."""
    from app.db import database
    from app.services import audit_logger

    assert Path(database.DB_PATH).parent == _SANDBOX, f"Tests would use live DB: {database.DB_PATH}"
    assert Path(audit_logger.LOGS_DIR).parent == _SANDBOX, f"Tests would use live logs: {audit_logger.LOGS_DIR}"
    # Relative paths (request_logs/, desktop/MaasData/...) resolve against the
    # cwd, so tests run from the sandbox, never from the repo.
    os.chdir(_SANDBOX)
    yield
    os.chdir(project_root)


@pytest.fixture(autouse=True)
def _isolate_test(monkeypatch):
    """Run each test in its own scratch dir and undo everything it wrote.

    - cwd and home point at a fresh per-test directory, deleted after the test
    - the sandbox auth DB is restored to its pre-test state after the test
    - fails the test if it changed anything in the repo or the real MaasData
    """
    from app.db import database

    before = {root: _snapshot_tree(root) for root in _GUARDED_ROOTS}

    test_dir = Path(tempfile.mkdtemp(prefix="t_", dir=_SANDBOX))
    test_home = test_dir / "home"
    test_home.mkdir()
    monkeypatch.chdir(test_dir)
    monkeypatch.setenv("HOME", str(test_home))
    monkeypatch.setenv("USERPROFILE", str(test_home))

    db_backup = sqlite3.connect(":memory:")
    with sqlite3.connect(database.DB_PATH) as src:
        src.backup(db_backup)

    yield test_dir

    with sqlite3.connect(database.DB_PATH) as dst:
        db_backup.backup(dst)
    db_backup.close()

    monkeypatch.chdir(_SANDBOX)
    _rmtree_with_retry(test_dir)

    leaks = []
    for root in _GUARDED_ROOTS:
        leaks += _diff_snapshots(before[root], _snapshot_tree(root))
    if leaks:
        pytest.fail("Test wrote outside its sandbox:\n  " + "\n  ".join(leaks), pytrace=False)


@pytest.fixture
def tmp_path(tmp_path):
    """Built-in tmp_path, but deleted by the test itself instead of kept around."""
    yield tmp_path
    _rmtree_with_retry(tmp_path)

from unittest.mock import MagicMock
sys.modules['Swabian'] = MagicMock()
sys.modules['Swabian.TimeTagger'] = MagicMock()
sys.modules['TimeTagger'] = MagicMock()

# main.py and worker.py open "logs/services/*.log" relative to the cwd at import
# time. Import them from inside the sandbox so those files land there, then go
# back to the repo so pytest still resolves `testpaths` correctly during collection.
os.chdir(_SANDBOX)
try:
    import main  # noqa: E402,F401
    import worker  # noqa: E402,F401
finally:
    os.chdir(project_root)


def pytest_unconfigure(config):
    """Delete the session sandbox; runs even if collection or the run aborts."""
    import gc

    os.chdir(project_root)
    _close_sandbox_log_handlers()
    gc.collect()  # finalize any unclosed sqlite connections still locking the DB file (Windows)
    shutil.rmtree(_SANDBOX, ignore_errors=True)
    if _SANDBOX.exists():
        sys.stderr.write(f"\nWARNING: could not fully remove test sandbox {_SANDBOX}\n")


@pytest.fixture(autouse=True)
def mock_redis_globally():
    """Globally mock redis using fakeredis for unit tests."""
    import fakeredis
    from unittest.mock import patch
    
    # Create fake redis server to share state between sync and async instances
    server = fakeredis.FakeServer()
    fake_sync = fakeredis.FakeRedis(server=server, decode_responses=True)
    fake_async = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    
    # Patch every way the app/tests construct a client so nothing reaches a real Redis
    with patch("redis.Redis", return_value=fake_sync), \
         patch("redis.StrictRedis", return_value=fake_sync), \
         patch("redis.asyncio.Redis", return_value=fake_async), \
         patch("redis.asyncio.from_url", return_value=fake_async):
        yield

@pytest.fixture(scope="session")
def event_loop():
    """Create an event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.fixture(autouse=True)
def reset_event_loop():
    """Reset event loop between tests and clean up pending tasks."""
    yield

    # After each test, ensure all pending tasks are cancelled if a loop is running
    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None and not loop.is_closed():
            pending = asyncio.all_tasks(loop)
            for task in pending:
                task.cancel()
            if pending:
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    except Exception:
        pass


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async (deselect with '-m \"not asyncio\"')"
    )


@pytest.fixture(autouse=True)
def mock_timetagger_classes():
    """Globally mock TimeTagger Counter and Correlation classes for unit tests."""
    from unittest.mock import MagicMock, patch

    mock_counter = MagicMock()
    mock_counter.getData.return_value = [[100, 200]]
    # Totals since the last clear, and 1 s of capture (in ps)
    mock_counter.getDataTotalCounts.return_value = [100, 200]
    mock_counter.getCaptureDuration.return_value = int(1e12)
    mock_counter.isFinished.return_value = False
    mock_counter.isRunning.return_value = True

    mock_correlation = MagicMock()
    mock_correlation.getData.return_value = [1, 2]
    mock_correlation.getIndex.return_value = [-1000, 0]
    mock_correlation.isFinished.return_value = False
    mock_correlation.isRunning.return_value = True

    import sys
    sys.modules['Swabian'] = MagicMock()
    sys.modules['Swabian.TimeTagger'] = MagicMock()
    sys.modules['TimeTagger'] = MagicMock()

    with patch("Swabian.TimeTagger.Counter", return_value=mock_counter), \
         patch("Swabian.TimeTagger.Correlation", return_value=mock_correlation):
        yield

@pytest.fixture(autouse=True)
def mock_auth_middleware(request):
    """Mock auth middleware to allow all tests to pass without a real JWT token."""
    if "test_auth" in request.module.__name__:
        yield
        return
        
    from unittest.mock import patch
    with patch("app.middleware.auth_middleware.decode_access_token") as mock_decode:
        mock_decode.return_value = {"sub": 1, "role": "admin"}
        yield mock_decode

@pytest.fixture(autouse=True)
def inject_auth_header_into_testclient(request):
    """Monkey-patch TestClient to always include a valid Authorization header."""
    if "test_auth" in request.module.__name__:
        yield
        return
        
    from fastapi.testclient import TestClient
    original_request = TestClient.request

    def request_with_auth(self, method, url, **kwargs):
        headers = kwargs.get("headers")
        if not headers:
            headers = {}
        else:
            headers = dict(headers)
            
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = "Bearer dummy_token"
            
        kwargs["headers"] = headers
        return original_request(self, method, url, **kwargs)

    TestClient.request = request_with_auth
    yield
    TestClient.request = original_request

@pytest.fixture(autouse=True)
def inject_auth_header_into_asyncclient(request):
    """Monkey-patch httpx.AsyncClient to always include a valid Authorization header."""
    if "test_auth" in request.module.__name__:
        yield
        return
        
    from httpx import AsyncClient
    original_request = AsyncClient.request

    async def request_with_auth(self, method, url, **kwargs):
        headers = kwargs.get("headers")
        if not headers:
            headers = {}
        else:
            headers = dict(headers)
            
        if "Authorization" not in headers and "authorization" not in headers:
            headers["Authorization"] = "Bearer dummy_token"
            
        kwargs["headers"] = headers
        return await original_request(self, method, url, **kwargs)

    AsyncClient.request = request_with_auth
    yield
    AsyncClient.request = original_request
