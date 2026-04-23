# MaaS - Measurement as a Service

A high-performance, extensible Python service for managing measurements over local HTTPS APIs. Designed for concurrent, long-running measurements with automatic lifecycle management.

## Features

- **FastAPI Framework**: Modern, async-first REST API with automatic documentation
- **HTTPS Support**: Auto-generates self-signed certificates for secure local network communication
- **Extensible Architecture**: Easy to add new measurement types with the `MeasurementHandler` interface
- **Concurrent Measurements**: Handle multiple simultaneous measurements with unique IDs
- **Auto-Stop Capability**: Optional automatic measurement stop after specified duration
- **Comprehensive Logging**: Detailed debug logs with measurement-specific context for troubleshooting
- **Type-Safe Models**: Pydantic models with validation and automatic API documentation
- **Lifecycle Management**: Proper async cleanup on shutdown

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Run the Service

```bash
python main.py
```

The service will:
- Auto-generate SSL certificates in `certs/` folder
- Start listening on `https://0.0.0.0:8443`
- Provide API documentation at `https://localhost:8443/docs`

### 3. Test with cURL (ignoring self-signed cert)

```bash
# Start a measurement
curl -k -X POST https://localhost:8443/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "measurement_type": "count_rate",
    "duration_seconds": 30,
    "metadata": {"detector": "det_001"}
  }'

# Response: {"measurement_id": "uuid-here", "status": "active", ...}

# Check status
curl -k https://localhost:8443/api/v1/measurements/{measurement_id}/status

# Stop measurement
curl -k -X DELETE https://localhost:8443/api/v1/measurements/{measurement_id}
```

## API Endpoints

### Start Count-Rate Measurement

**POST** `/api/v1/measurements/count-rate`

Request body:
```json
{
  "measurement_type": "count_rate",
  "duration_seconds": 60,
  "metadata": {"detector_id": "det_001", "source": "lab_B"}
}
```

Response:
```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "active",
  "started_at": "2026-04-16T10:30:00.123456",
  "message": "Count-rate measurement started. Use ID '...' to query status or stop."
}
```

### Get Measurement Status

**GET** `/api/v1/measurements/{measurement_id}/status`

Response:
```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "active",
  "started_at": "2026-04-16T10:30:00.123456",
  "duration_so_far": 12.345,
  "metadata": {"detector_id": "det_001"},
  "results": null
}
```

### Stop Measurement (DELETE)

**DELETE** `/api/v1/measurements/{measurement_id}`

Response:
```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "stopped",
  "started_at": "2026-04-16T10:30:00.123456",
  "message": "Measurement stopped successfully. Results: {...}"
}
```

### Health Check

**GET** `/health`

Response: `{"status": "healthy", "service": "Measurement as a Service (MaaS)"}`

---

## Architecture

### Core Components

1. **MeasurementService** (`app/services/measurement.py`)
   - Central service managing all active measurements
   - Tracks measurement lifecycle (active → stopped)
   - Provides APIs for starting, stopping, and querying measurements
   - Thread/async-safe with proper locking

2. **MeasurementHandler** (Abstract, `app/services/measurement.py`)
   - Base class for measurement implementations
   - Define your own by inheriting and implementing `start()` and `stop()` methods
   - Example: `CountRateMeasurementHandler`

3. **Measurement** (`app/services/measurement.py`)
   - Represents a single active measurement instance
   - Manages duration timers, handler lifecycle, and results collection
   - Thread-safe operations with async locks

4. **CountRateMeasurementHandler** (`app/services/count_rate.py`)
   - Example measurement type implementation
   - Placeholder implementation - replace the `_count_rate_loop()` with actual measurement logic

5. **FastAPI Routes** (`app/api/routes.py`)
   - REST API endpoints for start/stop/status operations
   - Input validation via Pydantic models
   - Comprehensive error handling with proper HTTP status codes

6. **Models** (`app/models.py`)
   - `CountRateMeasurementRequest`: Request validation
   - `MeasurementResponse`, `MeasurementStatusResponse`: Response schemas
   - Type-safe with automatic OpenAPI documentation

---

## Testing

The project includes comprehensive unit and integration tests. See [tests/README.md](tests/README.md) for details.

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_payloads.py -v
```

---

## Payload Definitions & JSON Mapping

### Overview

The service uses centralized JSON payload definitions with automatic validation and mapping to Pydantic models via the `MeasurementPayloadMapper`.

### Accessing Payload Schemas

```python
from app.payloads import MeasurementPayloadMapper

# Get schema for specific type
schema = MeasurementPayloadMapper.get_schema("count_rate")

# Get all schemas
all_schemas = MeasurementPayloadMapper.get_all_schemas()

# List available types
types = MeasurementPayloadMapper.list_types()  # ['count_rate', ...]
```

### JSON-to-Class Mapping

Payloads are automatically mapped to Pydantic models:

```python
from app.payloads import MeasurementPayloadMapper

# Validate and parse a JSON payload
payload_dict = {
    "measurement_type": "count_rate",
    "duration_seconds": 60,
    "metadata": {"detector": "det_001"}
}

validated_model = MeasurementPayloadMapper.validate_and_parse("count_rate", payload_dict)
# Returns: CountRateMeasurementRequest instance
```

### Adding New Measurement Types

The service is designed to easily support multiple measurement types. Here's how to add a new one:

### Step 1: Create a Handler

```python
# app/services/your_measurement.py
from app.services.measurement import MeasurementHandler

class YourMeasurementHandler(MeasurementHandler):
    async def start(self, duration_seconds, metadata):
        """Initialize and start your measurement"""
        logger.info("Starting your measurement")
        # Your implementation here
    
    async def stop(self):
        """Stop and return results"""
        logger.info("Stopping your measurement")
        return {"your_result": "value"}
```

### Step 2: Register the Handler

In `main.py`, add to the lifespan function:

```python
measurement_service.register_handler("your_type", YourMeasurementHandler)
```

### Step 3: Add API Endpoint (Optional)

If your measurement type needs different parameters, add a new endpoint in `app/api/routes.py`:

```python
@router.post("/your-measurement", response_model=MeasurementResponse)
async def start_your_measurement(request: YourMeasurementRequest):
    # Route implementation
```

### Step 4: Update Models and Register Payload

Add request/response models in `app/models.py`:

```python
class YourMeasurementRequest(BaseModel):
    your_param: str
    # Your fields
```

Register the payload model in `app/payloads.py`:

```python
from app.payloads import MeasurementPayloadMapper

# Register your model
MeasurementPayloadMapper.register_model("your_type", YourMeasurementRequest)

# Add schema (optional, for documentation)
MeasurementPayloadSchemas.SCHEMAS["your_type"] = {
    "type": "object",
    "properties": {
        "your_param": {"type": "string"},
    }
}
```

---

## Configuration

Edit `config.py` to customize:

- `SERVICE_HOST`: Bind address (default: `0.0.0.0`)
- `SERVICE_PORT`: HTTPS port (default: `8443`)
- `LOG_LEVEL`: Logging verbosity (default: `INFO`)
- `SSL_CERT_DAYS`: Certificate validity period (default: `365`)

You can also use environment variables:

```bash
SERVICE_PORT=9443 LOG_LEVEL=DEBUG python main.py
```

---

## Logging

The service provides detailed logging at each layer:

- **API Routes**: Request/response logging with measurement IDs
- **MeasurementService**: Lifecycle events (start, stop, register handlers)
- **Measurements**: Per-measurement operations with unique ID context
- **Handlers**: Implementation-specific debug information
- **SSL Utils**: Certificate generation and validation logs

Check logs to debug:

```
2026-04-16 10:30:00 - app.services.measurement - INFO - [550e8400] Measurement created
2026-04-16 10:30:00 - app.services.measurement - INFO - [550e8400] Starting measurement
2026-04-16 10:30:00 - app.services.count_rate - INFO - Starting count-rate measurement
```

---

## Development

### Project Structure

```
MaaS/
├── main.py                          # Entry point
├── config.py                        # Configuration
├── requirements.txt                 # Dependencies
├── certs/                           # Generated SSL certificates (gitignored)
├── app/
│   ├── __init__.py
│   ├── models.py                    # Pydantic request/response models
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py                # FastAPI endpoints
│   ├── services/
│   │   ├── __init__.py
│   │   ├── measurement.py           # Core measurement service
│   │   ├── count_rate.py            # Count-rate handler
│   │   └── your_handler.py          # Add new handlers here
│   └── utils/
│       ├── __init__.py
│       ├── logger.py                # Logging setup
│       └── ssl_utils.py             # Certificate generation
└── examples/
    └── client_example.py            # Example client usage
```

### Running Tests

Create a `test_client_example.py` to validate endpoints:

```python
import requests
import json
from pathlib import Path

# Disable SSL warnings for self-signed certs
requests.packages.urllib3.disable_warnings()

BASE_URL = "https://localhost:8443"

# Health check
print("Health check:", requests.get(f"{BASE_URL}/health", verify=False).json())

# Start measurement
resp = requests.post(
    f"{BASE_URL}/api/v1/measurements/count-rate",
    json={"measurement_type": "count_rate", "duration_seconds": 5},
    verify=False
)
measurement_id = resp.json()["measurement_id"]
print(f"Started measurement: {measurement_id}")

# Check status
import time
time.sleep(2)
status = requests.get(
    f"{BASE_URL}/api/v1/measurements/{measurement_id}/status",
    verify=False
).json()
print(f"Status: {status['status']}, Duration: {status['duration_so_far']:.2f}s")

# Stop
time.sleep(5)
result = requests.delete(
    f"{BASE_URL}/api/v1/measurements/{measurement_id}",
    verify=False
).json()
print(f"Results: {result}")
```

---

## Performance Considerations

1. **Async Architecture**: FastAPI + Uvicorn handles thousands of concurrent connections
2. **Measurement Isolation**: Each measurement runs independently in its own task
3. **Memory Efficient**: Measurements are cleaned up after stopping
4. **Scalability**: Add new handlers without changing service core

---

## Security Notes

- ⚠️ This service uses **self-signed certificates** for local network usage
- The service binds to `0.0.0.0` - adjust `SERVICE_HOST` if needed for tighter security
- No authentication is implemented - use network-level security if needed
- Certificates are stored in `certs/` - keep this directory secure

---

## Troubleshooting

### "Address already in use"
Change port: `SERVICE_PORT=9443 python main.py`

### SSL certificate errors in client
Use `-k` flag in curl or `verify=False` in Python requests

### Measurements not stopping
Check logs for errors: Look for `[measurement_id]` in output to trace specific measurement

### High CPU usage
Check `_count_rate_loop()` implementation - ensure adequate sleep intervals

---

## License

MIT - Use freely for local services.
