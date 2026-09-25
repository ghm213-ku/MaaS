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

# Also ensure we're in the right working directory
os.chdir(project_root)

from unittest.mock import MagicMock
sys.modules['Swabian'] = MagicMock()
sys.modules['Swabian.TimeTagger'] = MagicMock()
sys.modules['TimeTagger'] = MagicMock()


@pytest.fixture(autouse=True)
def mock_redis_globally():
    """Globally mock redis using fakeredis for unit tests."""
    import fakeredis
    from unittest.mock import patch
    
    # Create fake redis server to share state between sync and async instances
    server = fakeredis.FakeServer()
    fake_sync = fakeredis.FakeRedis(server=server, decode_responses=True)
    fake_async = fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    
    # We patch redis.Redis and redis.asyncio.from_url
    with patch("redis.Redis", return_value=fake_sync), \
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

    # After each test, ensure all pending tasks are cancelled
    try:
        loop = asyncio.get_event_loop()
        pending = asyncio.all_tasks(loop)
        for task in pending:
            task.cancel()
        # Give tasks a moment to process the cancellation
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
    mock_counter.isFinished.return_value = False
    mock_counter.isRunning.return_value = True

    mock_correlation = MagicMock()
    mock_correlation.getData.return_value = [[0.1, 0.2]]
    mock_correlation.isFinished.return_value = False
    mock_correlation.isRunning.return_value = True

    import sys
    sys.modules['Swabian'] = MagicMock()
    sys.modules['Swabian.TimeTagger'] = MagicMock()
    sys.modules['TimeTagger'] = MagicMock()

    with patch("Swabian.TimeTagger.Counter", return_value=mock_counter), \
         patch("TimeTagger.Correlation", return_value=mock_correlation):
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
