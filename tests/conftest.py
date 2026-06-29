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

    with patch("Swabian.TimeTagger.Counter", return_value=mock_counter), \
         patch("TimeTagger.Correlation", return_value=mock_correlation):
        yield
