"""
# Extending MaaS: Adding New Measurement Types

## Overview

This guide explains how to extend the MaaS system to support new measurement types beyond 
`count_rate` and `save_raw_tags`. You'll learn:

- How to create new Pydantic models for your measurement type
- How to create a measurement handler class
- How to register your handler with the system
- How to update API routes (optional)
- How to customize base classes

---

## Step 1: Create Pydantic Models

Models are defined in `app/models.py`. They define the structure and validation for your measurement requests.

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

- **Field Validation**: Use `Field()` for constraints
  - `gt=0`: Greater than
  - `le=3600`: Less than or equal
  - `min_items=1`: Minimum list length
  - `description`: Documentation

- **Required vs Optional**: Use `...` (Ellipsis) for required, `None` for optional

- **Type Checking**: Pydantic automatically validates types

- **Error Messages**: FastAPI returns HTTP 422 with descriptive errors

---

## Step 2: Create a Measurement Handler

Handlers execute the actual measurement logic. They live in `app/services/`.

### Understanding Existing Handler

```python
# From app/services/save_raw_tags.py

class SaveRawTagsMeasurementHandler:
    """Handles save-raw-tags measurements."""
    
    def __init__(self):
        """Initialize the handler."""
        self.logger = configure_logging(__name__)
    
    def start(self, target_file_path: str, channels: list[int], duration: int):
        """
        Execute the measurement.
        
        Args:
            target_file_path: Where to save data
            channels: List of channel IDs to record
            duration: How long to measure (seconds)
        """
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
        """
        Execute energy spectrum measurement.
        
        Args:
            duration_seconds: How long to measure
            channels: List of channels to measure
            bin_count: Number of energy bins
            calibration_data: Calibration parameters (optional)
        
        Returns:
            dict: Spectrum results
        """
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
                # In real implementation: query detector hardware
                for channel in channels:
                    energy = int((time.time() * 1000) % bin_count)
                    self.histogram[channel][energy] += 1
                
                elapsed = time.time() - start_time
                time.sleep(0.1)  # Small delay to prevent CPU spin
            
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
6. **Logging**: Log start, progress (optional), and completion

---

## Step 3: Register Handler with System

### In main_distributed.py

Edit the `lifespan()` function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle."""
    global status_manager, job_processor
    
    # ... existing code ...
    
    job_processor = JobProcessor(status_manager)
    job_processor.register_handler("count_rate", CountRateMeasurementHandler)
    job_processor.register_handler("save_raw_tags", SaveRawTagsMeasurementHandler)
    
    # ADD YOUR HANDLER HERE:
    job_processor.register_handler("energy_spectrum", EnergySpectrumHandler)
    
    # ... rest of code ...
```

### In backend_worker.py

Edit the `__init__()` method:

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
```

---

## Step 4: Add API Endpoint (Optional)

If you want a dedicated endpoint for your measurement type, edit `app/api/routes_distributed.py`:

```python
from app.models import EnergySpectrumRequest

@router.post("/energy-spectrum", response_model=MeasurementResponse, status_code=201)
async def start_energy_spectrum_measurement(
    request: EnergySpectrumRequest,
) -> MeasurementResponse:
    """
    Start an energy spectrum measurement.
    
    Example:
        POST /api/v1/measurements/energy-spectrum
        {
            "duration_seconds": 60,
            "metadata": {
                "channel_list": [1, 2, 3],
                "bin_count": 256
            }
        }
    """
    logger.info(f"Received energy-spectrum measurement request: {request.dict()}")
    
    try:
        status_id = str(uuid.uuid4())
        
        # Create status in Redis
        status_manager.create_status(
            status_id=status_id,
            measurement_type="energy_spectrum",
            duration_seconds=request.duration_seconds,
            metadata=request.metadata.model_dump(),
        )
        
        # Enqueue job
        job_processor.process_job(
            status_id,
            "energy_spectrum",
            request.duration_seconds,
        )
        
        return MeasurementResponse(
            measurement_id=status_id,
            measurement_type="energy_spectrum",
            status="queued",
            started_at=datetime.utcnow(),
            message=f"Energy spectrum measurement queued. Use ID '{status_id}' to query status.",
        )
        
    except Exception as e:
        logger.error(f"Failed to start energy spectrum measurement: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))
```

**Note**: If you don't add a dedicated endpoint, clients can still use the generic endpoint (if implemented).

---

## Step 5: Testing Your New Handler

Create tests in `tests/test_energy_spectrum.py`:

```python
"""Tests for energy spectrum handler."""
import pytest
from app.services.energy_spectrum import EnergySpectrumHandler


def test_energy_spectrum_basic():
    """Test basic energy spectrum measurement."""
    handler = EnergySpectrumHandler()
    
    results = handler.start(
        duration_seconds=2,
        channels=[1, 2, 3],
        bin_count=256,
    )
    
    assert results["measurement_type"] == "energy_spectrum"
    assert results["total_counts"] > 0
    assert len(results["spectrum"]) == 3


def test_energy_spectrum_with_calibration():
    """Test with calibration data."""
    handler = EnergySpectrumHandler()
    calibration = {"offset": 0, "gain": 1.5}
    
    results = handler.start(
        duration_seconds=1,
        channels=[1],
        bin_count=512,
        calibration_data=calibration,
    )
    
    assert results["bin_count"] == 512
    assert results["channels"] == [1]
```

Run tests:
```bash
pytest tests/test_energy_spectrum.py -v
```

---

## Step 6: Customizing Base Classes

### Scenario: Modify Measurement Handler Base Class

If multiple handlers share common logic, create a base class.

#### Option A: Create Abstract Base Class

Edit `app/services/base_handler.py` (new file):

```python
"""Base class for measurement handlers."""
from abc import ABC, abstractmethod
from app.utils.logger import configure_logging


class MeasurementHandler(ABC):
    """Abstract base class for all measurement handlers."""
    
    def __init__(self):
        """Initialize the handler."""
        self.logger = configure_logging(self.__class__.__name__)
        self.is_running = False
    
    @abstractmethod
    def start(self, **kwargs) -> dict:
        """
        Execute the measurement.
        
        Must be implemented by subclasses.
        
        Args:
            **kwargs: Measurement-specific parameters
            
        Returns:
            dict: Measurement results
        """
        pass
    
    def stop(self):
        """Stop the measurement gracefully."""
        self.logger.info(f"Stopping {self.__class__.__name__}")
        self.is_running = False
    
    def validate_channels(self, channels: list[int]) -> bool:
        """Validate channel list."""
        if not channels or not isinstance(channels, list):
            raise ValueError("Channels must be a non-empty list")
        if not all(isinstance(ch, int) for ch in channels):
            raise ValueError("All channels must be integers")
        return True
```

#### Option B: Inherit from Base Class

Update your handlers:

```python
from app.services.base_handler import MeasurementHandler


class CountRateHandler(MeasurementHandler):
    """Count rate measurement inheriting from base."""
    
    def start(self, duration_seconds: int, **kwargs) -> dict:
        """Execute count rate measurement."""
        self.is_running = True
        try:
            # Implementation here
            return {"total_count": 12345}
        finally:
            self.is_running = False


class EnergySpectrumHandler(MeasurementHandler):
    """Energy spectrum inheriting from base."""
    
    def start(self, duration_seconds: int, channels: list[int], **kwargs) -> dict:
        """Execute energy spectrum measurement."""
        self.validate_channels(channels)  # Use base method
        self.is_running = True
        try:
            # Implementation here
            return {"spectrum": {...}}
        finally:
            self.is_running = False
```

### Scenario: Change Status Management

Edit `app/services/status_manager.py` to modify:

1. **TTL (Time-To-Live)**
   ```python
   # Change from 1 hour to 2 hours
   ex=7200  # Previously: ex=3600
   ```

2. **Status States**
   Edit enum in `status_manager.py`:
   ```python
   class MeasurementStatus(Enum):
       QUEUED = "queued"
       ACTIVE = "active"
       PAUSED = "paused"  # NEW
       COMPLETED = "completed"
       STOPPED = "stopped"
       FAILED = "failed"
   ```

3. **Add Custom Metadata**
   ```python
   def create_status(self, status_id, measurement_type, duration_seconds, metadata, 
                     user_id=None, tags=None):
       """
       Create status with additional custom fields.
       """
       status_obj = {
           "status_id": status_id,
           "measurement_type": measurement_type,
           "status": MeasurementStatus.QUEUED.value,
           "duration_seconds": duration_seconds,
           "created_at": datetime.utcnow().isoformat(),
           "updated_at": datetime.utcnow().isoformat(),
           "user_id": user_id,  # NEW
           "tags": tags or [],  # NEW
       }
       # ... rest of method
   ```

### Scenario: Change Job Processor Behavior

Edit `app/services/job_processor.py`:

1. **Add Job Priority**
   ```python
   class JobProcessor:
       def __init__(self, status_manager):
           self.status_manager = status_manager
           self.active_jobs = {}
           self.job_queue = []  # NEW: priority queue
   
       def process_job(self, status_id, measurement_type, duration, priority="normal"):
           """Process job with priority."""
           job_info = {
               "status_id": status_id,
               "measurement_type": measurement_type,
               "duration": duration,
               "priority": priority,
           }
           # Sort queue by priority
           self.job_queue.append(job_info)
           self.job_queue.sort(key=lambda x: 0 if x["priority"]=="high" else 1)
   ```

2. **Add Job Timeout**
   ```python
   import signal
   
   def _handle_timeout(self, signum, frame):
       """Handle job timeout."""
       raise TimeoutError("Measurement exceeded maximum duration")
   
   def _run_job_in_thread(self, status_id, measurement_type, duration):
       """Run job with timeout."""
       # Set signal alarm (Unix only)
       signal.signal(signal.SIGALRM, self._handle_timeout)
       signal.alarm(int(duration) + 10)  # 10 second buffer
       
       try:
           # Run job...
       finally:
           signal.alarm(0)  # Cancel alarm
   ```

---

## Step 7: Create Models for New Handler

### Complete Model Creation Checklist

1. **Create enum value** (if not exists)
   ```python
   class MeasurementType(str, Enum):
       MY_NEW_TYPE = "my_new_type"
   ```

2. **Create metadata model**
   ```python
   class MyTypeMetadata(BaseModel):
       required_field: str
       optional_field: Optional[int] = None
   ```

3. **Create request model**
   ```python
   class MyTypeRequest(BaseModel):
       measurement_type: MeasurementType = MeasurementType.MY_NEW_TYPE
       duration_seconds: int
       metadata: MyTypeMetadata
   ```

4. **Add to imports** in relevant files:
   - `app/models.py` ✓ (defined here)
   - `app/api/routes_distributed.py` (if adding endpoint)
   - `main_distributed.py` (for API docs)

---

## Testing Full Integration

### Test New Measurement Type End-to-End

```bash
# 1. Start the system
python -m uvicorn main_distributed:app --reload

# 2. In another terminal, run:
curl -X POST http://localhost:8000/api/v1/measurements/energy-spectrum \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 5,
    "metadata": {
      "channel_list": [1, 2],
      "bin_count": 256
    }
  }'

# 3. Save the measurement_id and query status
curl http://localhost:8000/api/v1/measurements/{measurement_id}/status

# 4. Run pytest
pytest tests/test_energy_spectrum.py -v
```

---

## Summary: Files to Modify

To add a new measurement type:

| File | Action | Purpose |
|------|--------|---------|
| `app/models.py` | Add | Pydantic models & enum |
| `app/services/my_handler.py` | Create | Handler implementation |
| `main_distributed.py` | Edit | Register handler |
| `backend_worker.py` | Edit | Register handler |
| `app/api/routes_distributed.py` | Edit (optional) | Add dedicated endpoint |
| `tests/test_my_handler.py` | Create | Unit tests |

---

## Common Patterns

### Pattern 1: Simple Handler (Short Duration)

```python
class SimpleHandler:
    def start(self, duration_seconds, **kwargs):
        """Quick measurement."""
        return {"result": "done"}
```

### Pattern 2: Long-Running Handler with Progress

```python
class LongHandler:
    def start(self, duration_seconds, **kwargs):
        """Long measurement with checks."""
        self.is_running = True
        for i in range(int(duration_seconds * 10)):
            if not self.is_running:  # Check stop flag
                break
            time.sleep(0.1)
        return {"result": "done"}
```

### Pattern 3: Handler with External Resource

```python
class ResourceHandler:
    def start(self, duration_seconds, resource_id, **kwargs):
        """Handler using external resource."""
        try:
            resource = acquire_resource(resource_id)
            # Use resource
            return {"result": "done"}
        finally:
            release_resource(resource)  # Always cleanup
```

---

## Troubleshooting

### Handler Not Called

```
Check:
1. Handler registered in main_distributed.py
2. Handler registered in backend_worker.py
3. measurement_type matches registration key
4. No typos in handler name
```

### Model Validation Errors

```
Check:
1. Field types match expected values
2. Required fields marked with ... (Ellipsis)
3. Optional fields have default values
4. Constraints (ge, le, min_items) are correct
```

### Status Not Updating

```
Check:
1. Redis is running (redis-cli ping)
2. StatusManager initialized correctly
3. Handler calling status_manager.update_status()
4. status_id is correct UUID
```

---

## Next Steps

1. Create your new Pydantic models
2. Implement your measurement handler
3. Register with JobProcessor
4. Write unit tests
5. Test with curl or PostMan
6. Add documentation for your measurement type
