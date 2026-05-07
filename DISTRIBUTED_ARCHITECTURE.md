"""
# Distributed Architecture - Implementation Guide

## Overview

The application has been redesigned to use a distributed architecture with the following components:

```
┌─────────────────────────────────────┐
│  Web Layer (FastAPI)                │
│  - Receive measurement requests     │
│  - Enqueue jobs to Redis            │
│  - Return status IDs                │
│  - Query and stop measurements      │
└──────────────┬──────────────────────┘
               │ (enqueue via process_job)
               ▼
┌─────────────────────────────────────┐
│  Redis (Message Broker)             │
│  - Store status objects             │
│  - Persist metadata                 │
│  - Store results                    │
│  - Track active jobs                │
└──────────────┬──────────────────────┘
               │ (dequeue job)
               ▼
┌─────────────────────────────────────┐
│  Backend Worker Process             │
│  - Process jobs in separate threads │
│  - Update status in Redis           │
│  - Handle errors gracefully         │
│  - Store results when complete      │
└─────────────────────────────────────┘
```

## Architecture Components

### 1. StatusManager (`app/services/status_manager.py`)
- Manages measurement status in Redis
- Creates, updates, and retrieves measurement status
- Stores metadata and results
- Status states: QUEUED → ACTIVE → COMPLETED/STOPPED/FAILED

### 2. JobProcessor (`app/services/job_processor.py`)
- Spawns a new thread for each measurement job
- Registers handlers for different measurement types
- Updates status as jobs progress
- Handles errors and cleanup

### 3. Web Layer (`app/api/routes.py`)
- FastAPI routes for starting measurements
- Returns unique status IDs (UUIDs) instead of measurement IDs
- Enqueues jobs to Redis (does NOT register or execute handlers)
- Status queries return information from Redis
- Lightweight and scalable independently

### 4. Backend Worker (`worker.py`)
- Standalone process that processes measurement jobs
- Registers measurement handlers (only location where handlers are registered)
- Monitors Redis connection health
- Polls job queue and spawns threads for measurements
- Can be scaled to multiple instances for parallel processing

## Setup & Installation

### Prerequisites
- Python 3.10+
- Redis Server (local or remote)

### Installation

1. **Install dependencies:**
```bash
pip install -r requirements.txt
```

2. **Start Redis Server** (if not already running):
```bash
redis-server
# or on Windows:
wsl redis-server
```

3. **Verify Redis is running:**
```bash
redis-cli ping
# Should return: PONG
```

## Running the Application

### Option A: Development Mode (Single Process)

For testing and development, you can run everything in one process:

```bash
# Run the main application with FastAPI
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

This starts the web layer, and jobs are processed in background threads as they arrive.

### Option B: Production Mode (Separate Processes)

For better isolation and scalability:

```bash
# Terminal 1: Start the web layer
python main.py

# Terminal 2: Start the backend worker (processes jobs)
python worker.py
```

You can run multiple worker instances for parallel processing.

## API Usage Examples

### 1. Start a Count-Rate Measurement

```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "measurement_type": "count_rate",
    "duration_seconds": 60,
    "metadata": {
      "detector_id": "det_001",
      "source": "lab_B"
    }
  }'
```

Response:
```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "queued",
  "started_at": "2026-04-30T10:00:00",
  "message": "Count-rate measurement queued. Use ID '550e8400-e29b-41d4-a716-446655440000' to query status or stop."
}
```

### 2. Start a Save-Raw-Tags Measurement

```bash
curl -X POST http://localhost:8000/api/v1/measurements/save-raw-tags \
  -H "Content-Type: application/json" \
  -d '{
    "measurement_type": "save_raw_tags",
    "duration_seconds": 30,
    "metadata": {
      "channel_list": [1, 2, 3],
      "target_file_path": "C:\\data\\output.dat"
    }
  }'
```

### 3. Query Measurement Status

```bash
curl http://localhost:8000/api/v1/measurements/550e8400-e29b-41d4-a716-446655440000/status
```

Response:
```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "active",
  "started_at": "2026-04-30T10:00:00",
  "duration_so_far": 15.234,
  "metadata": {
    "detector_id": "det_001",
    "source": "lab_B"
  },
  "results": null
}
```

### 4. Stop a Measurement

```bash
curl -X DELETE http://localhost:8000/api/v1/measurements/550e8400-e29b-41d4-a716-446655440000
```

### 5. Health Check

```bash
curl http://localhost:8000/health
```

Response:
```json
{
  "status": "healthy",
  "service": "MaaS",
  "version": "2.0",
  "components": {
    "web_layer": "healthy",
    "redis": "healthy",
    "job_processor": "ready"
  }
}
```

## Key Features

### 1. Asynchronous Processing
- Jobs are enqueued immediately, returning status IDs
- Web layer responds quickly without waiting for job completion
- Jobs run in separate threads for concurrent processing

### 2. Status Persistence
- All status information stored in Redis
- Survives web layer restarts
- TTL set to 1 hour (configurable)

### 3. Thread-Per-Job Model
- Each measurement job spawns a new thread
- Jobs run independently without blocking each other
- Multiple measurements can run concurrently

### 4. Error Handling
- Validation errors return HTTP 422 before job creation
- Runtime errors captured and stored in status
- Service continues running even if jobs fail

### 5. Scalability
- Web layer can be scaled independently
- Backend workers can be added without restarting web layer
- Redis handles all inter-process communication

## Status States

```
QUEUED  → Job is waiting to be processed
   ↓
ACTIVE  → Job is currently running
   ↓
COMPLETED → Job finished successfully
  or
STOPPED  → Job was manually stopped
  or
FAILED   → Job encountered an error
```

## Configuration

### Redis Connection
Edit in `main.py` or `worker.py`:
```python
StatusManager(
    redis_host="localhost",      # Change to Redis server IP
    redis_port=6379,             # Redis port
    redis_db=0,                  # Database index
)
```

### Status TTL
Edit in `app/services/status_manager.py`:
```python
self.redis_client.set(status_key, ..., ex=3600)  # 3600 seconds = 1 hour
```

### Job Poll Interval
Edit in `worker.py`:
```python
worker.run(poll_timeout=1)  # Check every 1 second
```

## Distributed Architecture Overview

**Web Layer** (`main.py`):
- Receives HTTP requests
- Creates status records in Redis
- Enqueues jobs (via JobProcessor)
- Returns immediately with status ID

**Backend Worker** (`worker.py`):
- Registers measurement handlers
- Polls Redis job queue
- Processes jobs in threads
- Updates status in Redis

To switch:
- Change imports in `main_distributed.py` or rename files
- Ensure Redis is running before starting the application
- Update any client code to work with the new status ID system

## Troubleshooting

### Redis Connection Error
```
ERROR: ConnectionRefusedError
Solution: Start Redis server (redis-server)
```

### Jobs Not Processing
```
Solution: Ensure both main_distributed.py and backend_worker.py are running
Solution: Check Redis connection health with: redis-cli ping
```

### Status Not Found
```
Solution: Measurement status may have expired (TTL=1 hour)
Solution: Re-create the measurement
```

### Port Already in Use
```
Solution: Change port in uvicorn:
python -m uvicorn main_distributed:app --port 8001
```

## Performance Characteristics

- **Job Startup**: < 1ms (just enqueues to Redis)
- **Status Query**: < 10ms (reads from Redis)
- **Concurrent Jobs**: Limited by available threads (system-dependent)
- **Memory**: Minimal (status only stored while active + 1 hour)

## Testing

Run tests with:
```bash
# Unit tests for models
pytest tests/test_save_raw_tags_model.py -v

# API validation tests
pytest tests/test_save_raw_tags_api.py -v

# All tests
pytest tests/ -v
```

## Future Enhancements

1. **Job Queue**: Replace threading with RQ for better job management
2. **Job Persistence**: Use RQ to persist job queue across restarts
3. **Multiple Workers**: Deploy multiple backend worker instances
4. **Job Priority**: Add priority levels for different measurement types
5. **Job Cancellation**: Implement proper cancellation mechanism
6. **Metrics**: Add Prometheus metrics for monitoring
7. **Web Dashboard**: Add UI to monitor active measurements
"""

# This is a module docstring showing the architecture documentation
