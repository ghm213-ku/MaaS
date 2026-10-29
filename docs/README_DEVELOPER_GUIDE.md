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
python -m uvicorn main:app --reload --port 8000

# Visit: http://localhost:8000/docs for API documentation
```

### Run in Production-like Mode (Two Processes)

```bash
# Terminal 1: Web Layer
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Backend worker
python worker.py
```

---

## Project Structure

```
MaaS/
├── app/
│   ├── __init__.py
│   ├── models.py                ← Pydantic request/response models
│   ├── payloads.py              ← Measurement payload mapping and schemas
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py            ← Distributed API endpoints with unified handler
│   │
│   ├── services/
│   │   ├── __init__.py
│   │   ├── count_rate.py        ← Count-rate measurement handler
│   │   ├── save_raw_tags.py     ← Save-raw-tags measurement handler
│   │   ├── coincidences.py      ← Coincidences measurement handler
│   │   ├── coincidences_live.py ← Live streaming for Coincidences
│   │   ├── correlation.py       ← Correlation measurement handler
│   │   ├── time_histograms_live.py ← Live streaming for StartStop, Histogram, Correlation
│   │   ├── measurement.py       ← Original monolithic service (legacy)
│   │   ├── status_manager.py    ← Redis status management
│   │   ├── job_processor.py     ← Thread-based job execution
│   │   └── file_logger.py       ← Legacy logging functionality
│   │
│   └── utils/
│       ├── __init__.py
│       ├── logger.py            ← Logging configuration
│       ├── path_utils.py        ← Path formatting utilities
│       └── ssl_utils.py         ← SSL/TLS utilities
│
├── tests/
│   ├── conftest.py
│   ├── test_*.py               ← Various unit tests
│   └── test_distributed_integration.py ← Integration tests
│
├── main.py                      ← Web layer entry point
├── worker.py                    ← Backend worker entry point
├── config.py
├── requirements.txt
│
├── docs/
│   ├── README_DEVELOPER_GUIDE.md
│   ├── README_SYSTEM_FLOW.md
│   └── README_USER_GUIDE.md
└── worker.py                    ← Backend process for job execution
```

---

## Code Structure Deep Dive

### Entry Point: main.py

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

### API Routes: app/api/routes.py

```python
# Endpoints are simplified using a unified helper:

@router.post("/count-rate", response_model=MeasurementResponse, status_code=201)
async def start_count_rate_measurement(request: CountRateMeasurementRequest):
    return await _handle_measurement_request(
        request=request,
        measurement_type="count_rate",
        status_manager=status_manager,
        job_processor=job_processor,
    )
```

**Key Functions**:
- `_handle_measurement_request()` - Unified orchestrator for starting measurements
- `start_count_rate_measurement()` - Wrapper for count-rate
- `start_save_raw_tags_measurement()` - Wrapper for save-raw-tags
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
    # dynamically resolves metadata using MeasurementPayloadMapper
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

**coincidences.py**:
```python
class CoincidencesMeasurementHandler:
    def start(self, duration_seconds, coincidences: list[list[int]], coincidence_window=1000, timestamp="Last", **metadata)
        # Input strictly requires list[list[int]] (e.g. [[1, 2]] or [[1, 2], [2, 3]]). Simple 1D lists are deprecated.
        # Configures Swabian TimeTagger.Coincidences virtual channels
        # Measures coincidence counts using TimeTagger.Counter and saves output
        # Return {"status": "completed", "duration": N, "count": N}
```

**coincidences_live.py**:
```python
class CoincidencesLiveMeasurementHandler:
    def start(self, duration_seconds, coincidences: list[list[int]], coincidence_window=1000, refresh_rate=25, **metadata)
        # Input strictly requires list[list[int]] (e.g. [[1, 2]] or [[1, 2], [2, 3, 5]]). Simple 1D lists are deprecated.
        # Configures Swabian TimeTagger.Coincidences(tagger, coincidences, coincidence_window, timestamp)
        # Obtains virtual channels for each coincidence group via coinc.getChannels()
        # Reads live count rates across all virtual channels and publishes:
        #   - Multiplexed channel measurement:data:{status_id} with full "streams" metadata
        #   - Dedicated per-stream sub-channels measurement:data:{status_id}:stream_{index}
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

# Backend worker logs (in terminal running worker.py)
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

Edit **main.py**:
```python
# In lifespan():
logger.info(f"StatusManager initialized: {status_manager}")
logger.info(f"JobProcessor initialized: {job_processor}")
logger.info(f"Handlers registered: {job_processor.handlers}")
```

Edit **routes.py**:
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
ps aux | grep worker.py

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
# Add timing to routes.py:
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
```

---

# Part 2: Extending MaaS with New Measurement Types

## Overview

This section explains how to extend MaaS to support new measurement types beyond `count_rate` and `save_raw_tags`. You'll learn:

- How to create new Pydantic models
- How to create a measurement handler
- How to register your handler with the system
- How to add API endpoints

---

## Step 1: Create Pydantic Models

Models are defined in `app/models.py` and define request validation and structure.

### Understanding Existing Models

```python
# From app/models.py - Example: SaveRawTagsMetadata

class SaveRawTagsMetadata(BaseModel):
    """Metadata specific to save-raw-tags measurements."""
    channel_list: list[int]  # Required: list of channel IDs
    target_file_path: str    # Required: where to save data


class SaveRawTagsMeasurmentRequest(BaseModel):
    """Request model for save-raw-tags measurements."""
    measurement_type: MeasurementType = MeasurementType.SAVE_RAW_TAGS
    duration_seconds: int  # Required: how long to measure
    metadata: SaveRawTagsMetadata  # Required: specific to this measurement type
```

### Example: Add Energy Spectrum Measurement

Edit `app/models.py` and add:

```python
class EnergySpectrumMetadata(BaseModel):
    """Metadata specific to energy spectrum measurements."""
    channel_list: list[int] = Field(
        ..., 
        description="Channels to measure spectrum for",
        min_items=1,
    )
    bin_count: int = Field(
        256, 
        description="Number of energy bins",
        ge=32,
        le=4096,
    )
    calibration_data: Optional[dict] = Field(
        None,
        description="Energy calibration parameters",
    )


class EnergySpectrumRequest(BaseModel):
    """Request model for energy spectrum measurements."""
    measurement_type: MeasurementType = MeasurementType.ENERGY_SPECTRUM
    duration_seconds: int = Field(
        ...,
        description="Measurement duration in seconds",
        gt=0,
        le=3600,
    )
    metadata: EnergySpectrumMetadata


# Also update the MeasurementType enum:
class MeasurementType(str, Enum):
    """Supported measurement types."""
    COUNT_RATE = "count_rate"
    SAVE_RAW_TAGS = "save_raw_tags"
    ENERGY_SPECTRUM = "energy_spectrum"  # NEW
```

### Key Model Features

- **Field Validation**: Use `Field()` for constraints (gt, le, min_items, etc.)
- **Required vs Optional**: Use `...` (Ellipsis) for required, `None` for optional
- **Type Checking**: Pydantic automatically validates types
- **Error Messages**: FastAPI returns HTTP 422 with descriptive validation errors

---

## Step 2: Create a Measurement Handler

Handlers execute the actual measurement logic and live in `app/services/`.

### Understanding Existing Handler

```python
# From app/services/save_raw_tags.py

class SaveRawTagsMeasurementHandler:
    """Handles save-raw-tags measurements."""
    
    def __init__(self):
        """Initialize the handler."""
        self.logger = configure_logging(__name__)
    
    def start(self, target_file_path: str, channels: list[int], duration: int):
        """Execute the measurement."""
        self.logger.info(f"Starting save-raw-tags measurement")
        # Measurement logic here
        self.logger.info(f"Measurement complete")
```

### Example: Create Energy Spectrum Handler

Create file `app/services/energy_spectrum.py`:

```python
"""Energy spectrum measurement handler."""
import time
from app.utils.logger import configure_logging

logger = configure_logging(__name__)


class EnergySpectrumHandler:
    """Handles energy spectrum measurements."""
    
    def __init__(self):
        """Initialize the handler."""
        self.logger = logger
        self.is_running = False
        self.histogram = {}
    
    def start(self, duration_seconds: int, channels: list[int], bin_count: int = 256, calibration_data: dict = None):
        """Execute energy spectrum measurement."""
        self.is_running = True
        self.logger.info(
            f"Starting energy spectrum measurement: "
            f"duration={duration_seconds}s, channels={channels}, bins={bin_count}"
        )
        
        try:
            # Initialize histogram bins
            self.histogram = {ch: [0] * bin_count for ch in channels}
            
            start_time = time.time()
            elapsed = 0
            
            while elapsed < duration_seconds and self.is_running:
                # Simulate acquiring spectrum data
                for channel in channels:
                    energy = int((time.time() * 1000) % bin_count)
                    self.histogram[channel][energy] += 1
                
                elapsed = time.time() - start_time
                time.sleep(0.1)
            
            self.logger.info(f"Energy spectrum measurement complete")
            
            return {
                "measurement_type": "energy_spectrum",
                "duration": elapsed,
                "channels": channels,
                "bin_count": bin_count,
                "spectrum": self.histogram,
                "total_counts": sum(sum(bins) for bins in self.histogram.values()),
            }
            
        except Exception as e:
            self.logger.error(f"Error in energy spectrum measurement: {e}", exc_info=True)
            raise
        finally:
            self.is_running = False
    
    def stop(self):
        """Stop the measurement."""
        self.logger.info("Stopping energy spectrum measurement")
        self.is_running = False
```

### Handler Best Practices

1. **Logger Setup**: Always initialize logger in `__init__`
2. **Error Handling**: Wrap in try/except, log errors
3. **Stop Support**: Check `self.is_running` flag for graceful shutdown
4. **Resource Cleanup**: Use finally block for cleanup
5. **Return Results**: Return dict with measurement results
6. **Logging**: Log start and completion

---

## Step 3: Register Handler with System

Handler registration happens ONLY in the backend worker (`worker.py`), not in the web layer.

Edit the `__init__()` method of the worker:

```python
def __init__(self):
    """Initialize the backend worker."""
    self.status_manager = StatusManager(...)
    self.job_processor = JobProcessor(self.status_manager)
    
    # Register handlers
    self.job_processor.register_handler("count_rate", CountRateMeasurementHandler)
    self.job_processor.register_handler("save_raw_tags", SaveRawTagsMeasurementHandler)
    
    # ADD YOUR HANDLER HERE:
    self.job_processor.register_handler("energy_spectrum", EnergySpectrumHandler)
    
    logger.info("Backend worker initialized")
```

**Why this design?**
- ✅ Lightweight web layer scales independently
- ✅ Backend workers own handler lifecycle
- ✅ Clear separation: HTTP vs job processing
- ✅ Add handlers without restarting web layer

---

## Step 4: Add Dedicated API Endpoint

Add a dedicated endpoint in `app/api/routes.py`:

```python
from app.models import EnergySpectrumRequest

@router.post("/energy-spectrum", response_model=MeasurementResponse, status_code=201)
async def start_energy_spectrum_measurement(
    request: EnergySpectrumRequest,
) -> MeasurementResponse:
    """Start an energy spectrum measurement."""
    return await _handle_measurement_request(
        request=request,
        measurement_type="energy_spectrum",
        status_manager=status_manager,
        job_processor=job_processor,
    )
```

---

## Step 5: Add Tests

Create file `tests/test_energy_spectrum.py`:

```python
"""Tests for energy spectrum handler."""
import pytest
from app.services.energy_spectrum import EnergySpectrumHandler

@pytest.fixture
def handler():
    """Fixture for EnergySpectrumHandler."""
    return EnergySpectrumHandler()

def test_energy_spectrum_basic(handler):
    """Test basic energy spectrum measurement."""
    result = handler.start(
        duration_seconds=1,
        channels=[1, 2, 3],
        bin_count=256,
    )
    
    assert result["measurement_type"] == "energy_spectrum"
    assert result["channels"] == [1, 2, 3]
    assert result["bin_count"] == 256
    assert result["total_counts"] > 0

def test_energy_spectrum_stop(handler):
    """Test stopping energy spectrum measurement."""
    import threading
    
    # Start in thread
    thread = threading.Thread(
        target=handler.start,
        kwargs={"duration_seconds": 10, "channels": [1], "bin_count": 256}
    )
    thread.start()
    
    import time
    time.sleep(0.2)
    
    # Stop it
    handler.stop()
    thread.join(timeout=2)
    
    assert not handler.is_running
```

---

## Step 6: Testing Your Extension

Run all tests:
```bash
pytest tests/ -v
```

Run your new tests:
```bash
pytest tests/test_energy_spectrum.py -v
```

Test the endpoint:
```bash
curl -X POST http://localhost:8000/api/v1/measurements/energy-spectrum \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 10,
    "metadata": {
      "channel_list": [1, 2, 3],
      "bin_count": 512
    }
  }'
```

---

## Checklist for Adding New Measurement Type

- [ ] Added metadata model in `app/models.py`
- [ ] Added request model in `app/models.py`
- [ ] Updated `MeasurementType` enum in `app/models.py`
- [ ] Created handler in `app/services/my_handler.py`
- [ ] Handler has `start()` and `stop()` methods
- [ ] Handler returns dict with results
- [ ] Registered handler in `worker.py`
- [ ] (Optional) Added API endpoint in `app/api/routes.py`
- [ ] Created tests in `tests/test_my_handler.py`
- [ ] All tests pass: `pytest tests/ -v`
- [ ] Tested API endpoint manually
- [ ] Updated documentation if needed

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
3. **Register handler** in `main.py` and `worker.py`
4. **Add route** (optional) in `app/api/routes.py`
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
pkill -f "uvicorn main"
pkill -f "worker.py"

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
python -m uvicorn main:app --port 8001
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

1. Read the codebase starting with `main.py`
2. Run tests to understand expected behavior
3. Try adding a new measurement type (see README_EXTENDING.md)
4. Set up debugging in your IDE
5. Monitor performance and optimize hot paths

## Additional Resources

- **System Flow**: See README_SYSTEM_FLOW.md
- **User Guide**: See README_USER_GUIDE.md
- **Extending**: See README_EXTENDING.md
- **API Docs**: Visit http://localhost:8000/docs
