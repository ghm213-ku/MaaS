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
    """Reset event loop between tests."""
    # This helps prevent event loop issues in pytest
    pass


def pytest_configure(config):
    """Configure pytest."""
    config.addinivalue_line(
        "markers", "asyncio: mark test as async (deselect with '-m \"not asyncio\"')"
    )
