# Testing Guide for MaaS

## Overview

The MaaS project includes comprehensive unit and integration tests covering:

- **Payload Mapping** (`test_payloads.py`) - JSON to class mapping and validation
- **Measurement Service** (`test_measurement_service.py`) - Core service lifecycle
- **Count-Rate Handler** (`test_count_rate_handler.py`) - Measurement implementation
- **API Routes** (`test_api_routes.py`) - HTTP endpoints and integration

## Quick Start

### 1. Install Test Dependencies

```bash
pip install -r requirements.txt
```

This includes:
- `pytest` - Test framework
- `pytest-asyncio` - Async test support
- `httpx` - HTTP testing client

### 2. Run All Tests

```bash
pytest
```

### 3. Run Tests with More Details

```bash
pytest -v
```

### 4. Run Specific Test File

```bash
pytest tests/test_payloads.py -v
pytest tests/test_measurement_service.py -v
pytest tests/test_count_rate_handler.py -v
pytest tests/test_api_routes.py -v
```

### 5. Run Specific Test

```bash
pytest tests/test_payloads.py::TestMeasurementPayloadMapper::test_validate_and_parse_count_rate_valid -v
```

### 6. Run with Coverage Report

```bash
pip install pytest-cov
pytest --cov=app --cov-report=html
# Opens htmlcov/index.html in browser
```

---

## Test Structure

### `tests/test_payloads.py`
Tests for JSON payload schemas and validation mapping.

**Key test classes:**
- `TestMeasurementPayloadSchemas` - Payload schema definitions
- `TestMeasurementPayloadMapper` - JSON to Pydantic model mapping
- `TestPayloadHelpers` - Utility functions
- `TestPayloadEdgeCases` - Boundary conditions

**Example:**
```bash
pytest tests/test_payloads.py::TestMeasurementPayloadMapper -v
```

### `tests/test_measurement_service.py`
Tests for the core measurement service and lifecycle.

**Key test classes:**
- `TestMeasurementService` - Service operations
- `TestMeasurement` - Individual measurement objects
- `TestMeasurementErrorHandling` - Error cases

**Example:**
```bash
pytest tests/test_measurement_service.py::TestMeasurementService::test_start_measurement_creates_unique_id -v
```

### `tests/test_count_rate_handler.py`
Tests for the count-rate measurement handler implementation.

**Key test classes:**
- `TestCountRateMeasurementHandler` - Handler functionality
- `TestCountRateMeasurementHandlerEdgeCases` - Boundary conditions

**Example:**
```bash
pytest tests/test_count_rate_handler.py::TestCountRateMeasurementHandler::test_count_rate_calculation -v
```

### `tests/test_api_routes.py`
Tests for REST API endpoints and integration.

**Key test classes:**
- `TestHealthEndpoint` - Health check endpoint
- `TestStartMeasurementEndpoint` - POST /measurements endpoint
- `TestStopMeasurementEndpoint` - DELETE /measurements endpoint
- `TestGetStatusEndpoint` - GET /measurements status endpoint
- `TestApiErrorHandling` - Error responses
- `TestApiIntegration` - Complete workflows

**Example:**
```bash
pytest tests/test_api_routes.py::TestApiIntegration::test_complete_measurement_workflow -v
```

---

## Test Commands by Category

### Payload and Data Mapping Tests
```bash
pytest tests/test_payloads.py -v
```

### Service Logic Tests
```bash
pytest tests/test_measurement_service.py tests/test_count_rate_handler.py -v
```

### API Integration Tests
```bash
pytest tests/test_api_routes.py -v
```

### All Tests
```bash
pytest tests/ -v
```

### Run with Async Output
```bash
pytest tests/ -v -s
```

### Run Specific Test Pattern
```bash
pytest tests/ -k "start_measurement" -v
```

---

## Test Markers

Tests can be filtered by markers:

```bash
# Run only async tests
pytest -m asyncio

# Skip slow tests
pytest -m "not slow"

# Run integration tests
pytest -m integration
```

---

## Coverage Analysis

### Generate Coverage Report

```bash
pytest --cov=app --cov-report=term-missing
```

### Generate HTML Coverage Report

```bash
pytest --cov=app --cov-report=html
# Open htmlcov/index.html in browser
```

### Coverage with Specific Test File

```bash
pytest tests/test_payloads.py --cov=app.payloads --cov-report=term-missing
```

---

## Debugging Tests

### Show Print Statements

```bash
pytest tests/ -v -s
```

### Drop into Debugger on Failure

```bash
pytest tests/ -v --pdb
```

### Show Local Variables on Failure

```bash
pytest tests/ -v -l
```

### Verbose Traceback

```bash
pytest tests/ -v --tb=long
```

---

## Test Examples

### Testing Payload Validation

```python
def test_validate_complex_metadata():
    """Test complex nested metadata."""
    payload = {
        "measurement_type": "count_rate",
        "metadata": {
            "detector": "det_001",
            "location": {"building": "A", "room": 101},
            "settings": [1, 2, 3],
        },
    }
    result = MeasurementPayloadMapper.validate_and_parse("count_rate", payload)
    assert result.metadata["location"]["building"] == "A"
```

### Testing Async Measurement Operations

```python
@pytest.mark.asyncio
async def test_concurrent_measurements():
    """Test multiple concurrent measurements."""
    service = MeasurementService()
    
    # Start 5 measurements
    ids = [await service.start_measurement("mock") for _ in range(5)]
    
    # Verify all are active
    for meas_id in ids:
        measurement = service.get_measurement_status(meas_id)
        assert measurement.status == "active"
```

### Testing API Endpoints

```python
def test_start_measurement_success(client, mock_service):
    """Test starting a measurement via API."""
    response = client.post(
        "/api/v1/measurements/count-rate",
        json={"measurement_type": "count_rate", "duration_seconds": 10},
    )
    
    assert response.status_code == 201
    assert "measurement_id" in response.json()
```

---

## Continuous Integration

### Run tests before committing

```bash
# Run all tests with coverage
pytest tests/ --cov=app --cov-report=term-missing
```

### In CI/CD Pipeline

```yaml
# Example: .github/workflows/tests.yml
- name: Run tests
  run: |
    pip install -r requirements.txt
    pytest tests/ -v --cov=app --cov-report=xml
```

---

## Extending Tests

### Adding New Tests

1. Create test file in `tests/` directory
2. Name it `test_*.py`
3. Create test class `Test*` or test function `test_*`
4. Use pytest fixtures and markers

### Creating Custom Fixtures

```python
@pytest.fixture
async def custom_handler():
    """Create a custom handler for testing."""
    handler = MyCustomHandler()
    yield handler
    await handler.cleanup()
```

### Testing New Measurement Types

When adding new measurement types:

1. Create handler in `app/services/`
2. Add Pydantic model in `app/models.py`
3. Register in `app/payloads.py` mapper
4. Add tests in `test_payloads.py` and `test_api_routes.py`

---

## Troubleshooting

### Tests Hang

- Check for missing `await` in async functions
- Verify fixtures are properly cleaned up
- Check for infinite loops in handlers

### Import Errors

```bash
# Re-add project root to path
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
pytest tests/
```

### Async Test Issues

- Ensure `pytest-asyncio` is installed
- Use `@pytest.mark.asyncio` decorator
- Check `asyncio_mode` in `pytest.ini`

### Port Already in Use (API Tests)

- Tests use FastAPI TestClient (no real port)
- If tests still fail, check for lingering processes:
  ```bash
  netstat -an | grep 8443
  ```

---

## Test Stats

- **Total Tests**: 100+
- **Coverage Target**: 80%+
- **Async Tests**: 30+
- **API Integration Tests**: 20+

---

## Further Reading

- [Pytest Documentation](https://docs.pytest.org/)
- [Pytest-Asyncio](https://pytest-asyncio.readthedocs.io/)
- [FastAPI Testing](https://fastapi.tiangles.com/tutorial/testing/)
- [Pydantic Testing](https://docs.pydantic.dev/)
