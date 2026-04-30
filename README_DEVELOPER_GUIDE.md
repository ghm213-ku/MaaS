"""
# Developer Guide - Debugging & Running MaaS

## Overview

This guide is for developers: how to run the system locally, debug issues, extend functionality, 
and understand the codebase.

---

## Quick Start (Development)

### Prerequisites

```bash
# Check Python version (3.10+ required)
python --version

# Install dependencies
pip install -r requirements.txt

# Start Redis (required)
redis-server
# If on Windows without WSL: use Redis from Docker or Windows Redis installer
```

### Run in Development Mode (Single Process)

```bash
# Start the application with auto-reload
python -m uvicorn main_distributed:app --reload --port 8000

# Visit: http://localhost:8000/docs for API documentation
```

### Run in Production-like Mode (Two Processes)

```bash
# Terminal 1: Web Layer
python -m uvicorn main_distributed:app --host 0.0.0.0 --port 8000

# Terminal 2: Backend Worker
python backend_worker.py
```

---

## Project Structure

```
MaaS/
├── app/
│   ├── __init__.py
│   ├── models.py                 ← Pydantic request/response models
│   ├── payloads.py              ← Legacy payload models
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py            ← Original monolithic routes (legacy)
│   │   └── routes_distributed.py ← NEW: Distributed API endpoints
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── count_rate.py        ← Count-rate measurement handler
│   │   ├── save_raw_tags.py     ← Save-raw-tags measurement handler
│   │   ├── measurement.py       ← Original monolithic service (legacy)
│   │   ├── status_manager.py    ← NEW: Redis status management
│   │   ├── job_processor.py     ← NEW: Thread-based job execution
│   │   └── base_handler.py      ← (Optional) Base handler class
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py            ← Logging configuration
│       └── ssl_utils.py         ← SSL/TLS utilities
│
├── tests/
│   ├── conftest.py
│   ├── test_*.py               ← Various unit tests
│   └── test_distributed_integration.py ← NEW: Integration tests
│
├── main_distributed.py          ← NEW: Web layer entry point
├── main.py                      ← Original monolithic entry point
├── backend_worker.py            ← NEW: Backend worker entry point
├── config.py
├── requirements.txt
│
├── README_*.md                 ← Specialized documentation
├── QUICKSTART.md              ← Legacy quickstart
└── certs/                      ← SSL certificates
```

---

## Code Structure Deep Dive

### Entry Point: main_distributed.py

```python
# This is the main web layer entry point
# - Initializes FastAPI app
# - Sets up lifespan (startup/shutdown)
# - Creates StatusManager (Redis connection)
# - Creates JobProcessor (thread pool)
# - Includes API routes
```

**Key Function**: `lifespan()`
- Runs on app startup: initializes services
- Runs on app shutdown: cleanup (optional)

**How to modify**:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup code here
    global status_manager, job_processor
    status_manager = StatusManager(...)  # Modify Redis config here
    
    yield  # App runs while yielded
    
    # Shutdown code here (optional)
```

### API Routes: app/api/routes_distributed.py

```python
# Each route follows this pattern:

@router.post("/count-rate", response_model=MeasurementResponse, status_code=201)
async def start_count_rate_measurement(request):
    # 1. Validate request (Pydantic does this automatically)
    # 2. Generate status_id
    # 3. Create status in Redis (status_manager.create_status)
    # 4. Enqueue job (job_processor.process_job)
    # 5. Return response immediately
```

**Key Functions**:
- `start_count_rate_measurement()` - Start count-rate job
- `start_save_raw_tags_measurement()` - Start save-raw-tags job
- `stop_measurement()` - Stop running job
- `get_measurement_status()` - Query status
- `set_processors()` - Dependency injection

### Status Manager: app/services/status_manager.py

```python
# Manages all persistent state in Redis
class StatusManager:
    def create_status(status_id, measurement_type, duration, metadata)
    def get_status(status_id)
    def update_status(status_id, status, message, results)
    def get_metadata(status_id)
    def get_results(status_id)
    def delete_status(status_id)
    def health_check()
```

**Key Concepts**:
- Redis keys: `measurement:status:{id}`, `measurement:metadata:{id}`, `measurement:results:{id}`
- TTL: 3600 seconds (1 hour) by default
- JSON storage: all data stored as JSON strings in Redis

**How to debug**:
```bash
# Connect to Redis CLI
redis-cli

# List all measurement keys
KEYS measurement:*

# Get a specific status
GET measurement:status:550e8400-e29b-41d4-a716-446655440000

# View all keys and their TTL
KEYS measurement:*
TTL measurement:status:{id}
```

### Job Processor: app/services/job_processor.py

```python
# Manages job execution in threads
class JobProcessor:
    def process_job(status_id, measurement_type, duration)
    def stop_job(status_id)
    def get_job_status(status_id)
    def register_handler(measurement_type, handler_class)
    
    def _run_job_in_thread(status_id, measurement_type, duration)  # Private
    def _handle_count_rate(...)  # Private
    def _handle_save_raw_tags(...)  # Private
```

**Key Concepts**:
- Each job runs in its own thread
- `active_jobs` dict tracks running threads
- Handler classes registered at startup
- Status updated in Redis before, during, and after execution

**How to debug**:
```python
# In code:
print(job_processor.active_jobs)  # See active jobs
print(job_processor.handlers)     # See registered handlers
```

### Measurement Handlers

Handlers implement specific measurement logic.

**count_rate.py**:
```python
class CountRateMeasurementHandler:
    def start(self, duration_seconds, **metadata)
        # Count events for duration_seconds
        # Return {"total_count": N, ...}
```

**save_raw_tags.py**:
```python
class SaveRawTagsMeasurementHandler:
    def start(self, target_file_path, channels, duration_seconds)
        # Save events to file for duration_seconds
        # Return {"file_path": path, "total_events": N, ...}
```

**To create new handler**: See README_EXTENDING.md

---

## Debugging

### Level 1: Check System Health

```bash
# Web layer responsive?
curl http://localhost:8000/health

# Redis accessible?
redis-cli ping

# Both services running?
ps aux | grep python
ps aux | grep redis
```

### Level 2: Check Logs

```bash
# Web layer logs (in terminal running uvicorn)
# Look for: ERROR, WARNING, INFO messages

# Check specific measurement in logs:
grep -r "550e8400-e29b-41d4-a716-446655440000" .

# Backend worker logs (in terminal running backend_worker.py)
# Look for: handler execution, status updates, errors
```

### Level 3: Query Redis Directly

```bash
redis-cli

# Check status exists
GET measurement:status:550e8400-e29b-41d4-a716-446655440000

# Check metadata
GET measurement:metadata:550e8400-e29b-41d4-a716-446655440000

# Check results
GET measurement:results:550e8400-e29b-41d4-a716-446655440000

# Check all keys for this ID
KEYS measurement:*:550e8400-e29b-41d4-a716-446655440000
```

### Level 4: Add Debug Output

Edit **main_distributed.py**:
```python
# In lifespan():
logger.info(f"StatusManager initialized: {status_manager}")
logger.info(f"JobProcessor initialized: {job_processor}")
logger.info(f"Handlers registered: {job_processor.handlers}")
```

Edit **routes_distributed.py**:
```python
# In start_count_rate_measurement():
logger.debug(f"Request received: {request.dict()}")
logger.debug(f"Generated status_id: {status_id}")
logger.debug(f"Status created in Redis")
logger.debug(f"Job enqueued: {status_id}")
```

### Level 5: Step-by-Step Testing

```python
# Create a test script: test_debug.py

import asyncio
from app.services.status_manager import StatusManager
from app.services.job_processor import JobProcessor
from app.services.count_rate import CountRateMeasurementHandler

async def test():
    # Step 1: Create StatusManager
    status_mgr = StatusManager(redis_host="localhost")
    print("✓ StatusManager created")
    
    # Step 2: Create JobProcessor
    processor = JobProcessor(status_mgr)
    processor.register_handler("count_rate", CountRateMeasurementHandler)
    print("✓ JobProcessor created and handler registered")
    
    # Step 3: Create status
    status_id = "test-123"
    status_mgr.create_status(status_id, "count_rate", 2, {"detector": "test"})
    print("✓ Status created in Redis")
    
    # Step 4: Get status
    status = status_mgr.get_status(status_id)
    print(f"✓ Status: {status}")
    
    # Step 5: Process job
    processor.process_job(status_id, "count_rate", 2)
    print("✓ Job enqueued, waiting for completion...")
    
    # Step 6: Wait and check
    import time
    for i in range(10):
        status = status_mgr.get_status(status_id)
        print(f"  Status: {status['status']}")
        if status['status'] == 'completed':
            print(f"✓ Completed: {status_mgr.get_results(status_id)}")
            break
        time.sleep(0.5)

asyncio.run(test())
```

Run it:
```bash
python test_debug.py
```

---

## Running Tests

### Unit Tests

```bash
# Run all tests
pytest tests/ -v

# Run specific test file
pytest tests/test_distributed_integration.py -v

# Run specific test
pytest tests/test_distributed_integration.py::TestStatusManagerWithRedis::test_create_and_retrieve_status -v

# Run with coverage
pytest tests/ --cov=app --cov-report=html
```

### Integration Tests

```bash
# Full integration test suite (requires Redis)
pytest tests/test_distributed_integration.py -v

# Specific integration test class
pytest tests/test_distributed_integration.py::TestDistributedWorkflow -v
```

### Adding New Tests

Create file `tests/test_my_feature.py`:

```python
"""Tests for my feature."""
import pytest
from app.services.my_service import MyService

@pytest.fixture
def my_service():
    """Fixture for MyService."""
    return MyService()

def test_basic_functionality(my_service):
    """Test basic functionality."""
    result = my_service.do_something()
    assert result is not None
```

Run:
```bash
pytest tests/test_my_feature.py -v
```

---

## Debugging Common Issues

### Issue 1: "Connection Refused" Error

```python
# Error: ConnectionRefusedError: [Errno 111] Connection refused

# Debug:
redis-cli ping  # Should return PONG

# Solution:
redis-server  # Start Redis first
```

### Issue 2: Timeout / Measurement Never Completes

```python
# Debug:
# 1. Check Redis for status
redis-cli GET measurement:status:{id}

# 2. Check backend worker is running
ps aux | grep backend_worker.py

# 3. Check logs for exceptions

# 4. Manually inspect handler:
from app.services.count_rate import CountRateMeasurementHandler
handler = CountRateMeasurementHandler()
result = handler.start(duration_seconds=2)
print(result)
```

### Issue 3: Results Are Null

```python
# Debug:
# 1. Check if status is really COMPLETED
redis-cli GET measurement:status:{id}

# 2. Check if results key exists
redis-cli GET measurement:results:{id}

# 3. Check handler is returning results:
# Add to handler:
logger.debug(f"Returning results: {results}")
```

### Issue 4: Status Doesn't Update

```python
# Debug:
# 1. Verify StatusManager has Redis connection:
status_manager.health_check()  # Should return True

# 2. Check Redis connection:
redis-cli ping

# 3. Manually update status:
status_manager.update_status(status_id, "active", "test", None)
redis-cli GET measurement:status:{id}  # Check it updated
```

---

## Performance Monitoring

### Monitor Response Times

```python
# Add timing to routes_distributed.py:
import time

@router.post("/count-rate", ...)
async def start_count_rate_measurement(request):
    start_time = time.time()
    
    # ... implementation ...
    
    elapsed = time.time() - start_time
    logger.info(f"Request completed in {elapsed*1000:.1f}ms")
    
    return response
```

### Monitor Redis Performance

```bash
redis-cli

# Monitor all commands in real-time
MONITOR

# Check memory usage
INFO memory

# Check slow queries
SLOWLOG GET 10
```

### Monitor Thread Usage

```python
# Add to job_processor.py:
import threading

def print_active_threads(self):
    """Print currently active threads."""
    logger.info(f"Active threads: {threading.active_count()}")
    for thread in threading.enumerate():
        logger.info(f"  - {thread.name} (daemon={thread.daemon})")
    logger.info(f"Active jobs: {len(self.active_jobs)}")

# Call it periodically:
processor.print_active_threads()
```

---

## Code Style & Best Practices

### Logging

```python
from app.utils.logger import configure_logging

logger = configure_logging(__name__)

# Use appropriate levels:
logger.debug("Detailed info for debugging")
logger.info("General informational messages")
logger.warning("Warning about potential issues")
logger.error("Error occurred but can recover")
logger.critical("Fatal error, service may crash")

# Include context:
logger.info(f"[{status_id}] Starting measurement")
```

### Error Handling

```python
# Good: Specific exception handling
try:
    result = handler.start(**kwargs)
except ValueError as e:
    logger.error(f"Invalid input: {e}")
    status_manager.update_status(status_id, "failed", str(e))
except Exception as e:
    logger.error(f"Unexpected error: {e}", exc_info=True)
    status_manager.update_status(status_id, "failed", str(e))

# Good: Always cleanup
try:
    resource = acquire_resource()
    use_resource(resource)
finally:
    release_resource(resource)
```

### Type Hints

```python
# Good: Include type hints
def process_job(self, status_id: str, measurement_type: str, duration_seconds: int) -> None:
    """Process a measurement job."""
    ...

# Good: Return type hint
def get_status(self, status_id: str) -> Optional[dict]:
    """Get status or None if not found."""
    ...
```

### Docstrings

```python
# Good: Comprehensive docstrings
def create_status(
    self,
    status_id: str,
    measurement_type: str,
    duration_seconds: int,
    metadata: dict,
) -> None:
    """
    Create a new measurement status in Redis.
    
    Args:
        status_id: Unique UUID for this measurement
        measurement_type: Type of measurement (count_rate, save_raw_tags, etc.)
        duration_seconds: Expected duration of measurement
        metadata: Custom metadata dict for this measurement
    
    Returns:
        None
    
    Raises:
        redis.ConnectionError: If Redis not accessible
    
    Example:
        status_manager.create_status(
            "550e8400-e29b-41d4-a716-446655440000",
            "count_rate",
            30,
            {"detector": "main"},
        )
    """
    ...
```

---

## Extending the System

### Add New Measurement Type

1. **Add Pydantic model** in `app/models.py`
2. **Create handler** in `app/services/my_handler.py`
3. **Register handler** in `main_distributed.py` and `backend_worker.py`
4. **Add route** (optional) in `app/api/routes_distributed.py`
5. **Write tests** in `tests/test_my_handler.py`

See **README_EXTENDING.md** for detailed guide.

### Modify Status Manager

```python
# Edit app/services/status_manager.py:

# Change TTL:
ex=7200  # 2 hours instead of 1 hour

# Add custom status states:
class MeasurementStatus(Enum):
    PAUSED = "paused"  # NEW

# Add custom fields:
def create_status(self, status_id, measurement_type, duration, metadata, user_id=None):
    status_obj["user_id"] = user_id  # NEW
```

### Modify Job Processor

```python
# Edit app/services/job_processor.py:

# Add priority queue:
import heapq

def process_job(self, status_id, measurement_type, duration, priority=0):
    heapq.heappush(self.job_queue, (priority, status_id, ...))

# Add timeout:
signal.alarm(duration + 10)  # Add 10s buffer
```

---

## Useful Commands

```bash
# Check if services running
ps aux | grep python
ps aux | grep redis

# Kill service
pkill -f "uvicorn main_distributed"
pkill -f "backend_worker.py"

# Check port in use
netstat -tlnp | grep 8000

# View Redis memory
redis-cli INFO memory

# Clear Redis cache
redis-cli FLUSHDB

# Backup Redis data
redis-cli --rdb /tmp/dump.rdb

# Monitor Redis in real-time
redis-cli MONITOR

# Run linting
flake8 app/
pylint app/

# Format code
black app/

# Type checking
mypy app/
```

---

## Troubleshooting Development

### "ModuleNotFoundError: No module named 'app'"

```bash
# You're not in the right directory
pwd  # Should be MaaS directory
cd /path/to/MaaS

# Or add path:
export PYTHONPATH="${PYTHONPATH}:/path/to/MaaS"
```

### "Port 8000 already in use"

```bash
# Find process using port
netstat -tlnp | grep 8000

# Kill it:
pkill -f "uvicorn"

# Or use different port:
python -m uvicorn main_distributed:app --port 8001
```

### "pytest: command not found"

```bash
# pytest not installed
pip install pytest pytest-asyncio

# Or already in requirements.txt:
pip install -r requirements.txt
```

### "Redis connection timeout"

```bash
# Redis not running
redis-server

# Or check connection string in code
redis-cli ping

# Try different host:
StatusManager(redis_host="127.0.0.1", redis_port=6379)
```

---

## Next Steps

1. Read the codebase starting with `main_distributed.py`
2. Run tests to understand expected behavior
3. Try adding a new measurement type (see README_EXTENDING.md)
4. Set up debugging in your IDE
5. Monitor performance and optimize hot paths

## Additional Resources

- **System Flow**: See README_SYSTEM_FLOW.md
- **User Guide**: See README_USER_GUIDE.md
- **Extending**: See README_EXTENDING.md
- **API Docs**: Visit http://localhost:8000/docs
