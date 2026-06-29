"""
# System Architecture & HTTP Request Flow

## Overview

This document describes the MaaS distributed architecture and how HTTP requests flow through 
the system from initial reception to completion and status update.

---

## Part 1: Distributed Architecture Overview

### Architecture Components

The application uses a distributed architecture with clear separation of concerns:

1. **Web Layer (FastAPI)** - Receives requests and returns immediately with status IDs
2. **Redis Message Broker** - Stores status and job queue
3. **Backend Worker** - Processes jobs in separate threads using registered handlers
4. **Measurement Handlers** - Execute actual measurement logic (count-rate, save-raw-tags, etc.)

### Architecture Diagram

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

### Key Components

**StatusManager** (`app/services/status_manager.py`)
- Manages measurement status in Redis
- Creates, updates, and retrieves measurement status
- Stores metadata and results
- Status states: QUEUED → ACTIVE → COMPLETED/STOPPED/FAILED

**JobProcessor** (`app/services/job_processor.py`)
- Spawns a new thread for each measurement job
- Registers handlers for different measurement types
- Updates status as jobs progress
- Handles errors and cleanup

**Web Layer** (`app/api/routes.py`)
- FastAPI routes for starting measurements
- Returns unique status IDs (UUIDs)
- Enqueues jobs to Redis (does NOT register or execute handlers)
- Status queries return information from Redis
- Lightweight and scalable independently

**Backend Worker** (`worker.py`)
- Standalone process that processes measurement jobs
- Registers measurement handlers (only location where handlers are registered)
- Monitors Redis connection health
- Polls job queue and spawns threads for measurements
- Can be scaled to multiple instances for parallel processing

---

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

---

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

---

## Part 2: HTTP Request Routing & System Flow

---

## System Architecture (Request Flow)

```
┌──────────────────────────────────────────────────────────────────┐
│                        CLIENT                                    │
│              (Browser / CLI / External Service)                  │
└────────────────────────────────┬─────────────────────────────────┘
                                 │ HTTP Request
                                 ▼
┌──────────────────────────────────────────────────────────────────┐
│                    FASTAPI WEB LAYER                             │
│                  (main.py)                           │
│  • Receives HTTP request                                         │
│  • Validates with Pydantic models                               │
│  • Returns immediately with status ID                           │
└───────────────┬──────────────────────────────────┬───────────────┘
                │                                  │
                │ Enqueue Job                      │ Health Check
                │                                  │
                ▼                                  ▼
    ┌───────────────────────┐        ┌─────────────────────┐
    │   REDIS BROKER        │        │   Redis Status      │
    │  (In-Memory Storage)  │        │    (Health Check)   │
    │                       │        │                     │
    │ • Status objects      │        │ PONG response       │
    │ • Metadata            │        └─────────────────────┘
    │ • Job results         │
    │ • TTL: 1 hour         │
    └───────────┬───────────┘
                │ Dequeue Job
                ▼
┌──────────────────────────────────────────────────────────────────┐
│                   BACKEND WORKER                                 │
│                (worker.py)                               │
│                                                                  │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │          JOB PROCESSOR (Thread Pool)                       │ │
│  │          (app/services/job_processor.py)                  │ │
│  │                                                            │ │
│  │  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐   │ │
│  │  │   Thread 1   │  │   Thread 2   │  │   Thread N   │   │ │
│  │  │              │  │              │  │              │   │ │
│  │  │  Job A       │  │  Job B       │  │  Job ...     │   │ │
│  │  │  Measurement │  │  Measurement │  │  Measurement │   │ │
│  │  │  Handler     │  │  Handler     │  │  Handler     │   │ │
│  │  └──────────────┘  └──────────────┘  └──────────────┘   │ │
│  │                                                            │ │
│  │  Handlers:                                                 │ │
│  │  • CountRateMeasurementHandler                            │ │
│  │  • SaveRawTagsMeasurementHandler                          │ │
│  └────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────┘
```

---

## Detailed Request Flow

### Phase 1: HTTP Request Reception (< 5ms)

```
1. CLIENT sends HTTP request
   POST /api/v1/measurements/count-rate
   {
     "measurement_type": "count_rate",
     "duration_seconds": 30,
     "metadata": {
       "channels": [1, 2, 3],
       "binwidth": 1000000000,
       "n_values": 1,
       "target_location": "desktop/MaasData/{datetime}/{measurement-type}"
     }
   }

2. FASTAPI Router (routes.py)
   ├─ Route handler receives request
   └─ Dependency injection provides: status_manager, job_processor

3. PYDANTIC VALIDATION
   ├─ Validate request model (CountRateMeasurementRequest)
   ├─ Check required fields (measurement_type, duration_seconds, metadata)
   ├─ Validate metadata structure (CountRateMetadata)
   ├─ Check field types
   └─ If invalid → Return HTTP 422 (Unprocessable Entity)

4. GENERATE STATUS ID
   ├─ Create UUID: status_id = uuid.uuid4()
   └─ Example: "550e8400-e29b-41d4-a716-446655440000"
```

**Code Location**: `app/api/routes.py` lines 30-60 (start_count_rate_measurement)

---

### Phase 2: Status Creation in Redis (< 10ms)

```
5. CREATE INITIAL STATUS IN REDIS
   ├─ Status Manager creates record
   ├─ Redis key: measurement:status:{status_id}
   ├─ Initial state: QUEUED
   ├─ Store metadata separately
   │  └─ Redis key: measurement:metadata:{status_id}
   └─ Set TTL: 3600 seconds (1 hour)

   Redis stored object:
   {
     "status_id": "550e8400-e29b-41d4-a716-446655440000",
     "measurement_type": "count_rate",
     "status": "QUEUED",
     "duration_seconds": 30,
     "started_at": "2026-04-30T10:00:00Z",
     "updated_at": "2026-04-30T10:00:00Z",
     "message": "Job queued, waiting to be processed"
   }
```

**Code Location**: `app/services/status_manager.py` - `create_status()` method

---

### Phase 3: Immediate Response to Client (< 10ms total)

```
6. RETURN HTTP RESPONSE
   ├─ HTTP 201 Created
   └─ Response body:
      {
        "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
        "measurement_type": "count_rate",
        "status": "queued",
        "started_at": "2026-04-30T10:00:00Z",
        "message": "Count-rate measurement queued. Use ID '...' to query status"
      }

7. REQUEST HANDLING COMPLETE
   ├─ Web layer is now FREE for next request
   └─ Total time: < 10ms
```

**Code Location**: `app/api/routes.py` lines 50-60

---

### Phase 4: Job Enqueue to Processor (< 1ms)

```
8. ENQUEUE JOB TO PROCESSOR
   ├─ Call: job_processor.process_job(status_id, "count_rate", 30)
   └─ This returns immediately

9. JOB PROCESSOR RECEIVES JOB
   ├─ Check if handler registered for "count_rate"
   ├─ Get handler class: CountRateMeasurementHandler
   ├─ Create handler instance
   └─ Spawn new thread for job execution
```

**Code Location**: `app/services/job_processor.py` - `process_job()` method

---

### Phase 5: Measurement Execution in Thread (background)

```
10. NEW THREAD STARTS (_run_job_in_thread)
    ├─ Thread spawned with job details
    └─ Main thread returns immediately

11. THREAD EXECUTION - Update Status to ACTIVE
    ├─ Status Manager updates Redis
    ├─ Redis key: measurement:status:{status_id}
    ├─ New state: ACTIVE
    └─ Message: "Measurement started"

    Redis update:
    {
      "status": "ACTIVE",
      "updated_at": "2026-04-30T10:00:00.100Z",
      "message": "Measurement is running"
    }

12. THREAD EXECUTION - Run Handler
    ├─ Call handler.start() to execute measurement
    ├─ Handler runs measurement logic
    │  ├─ For count_rate: Count detector events for 30 seconds
    │  └─ For save_raw_tags: Save raw tag events to file
    ├─ Collect results
    └─ Handle any errors
```

**Code Location**: `app/services/job_processor.py` - `_run_job_in_thread()` method

---

### Phase 6: Measurement Completion & Result Storage

```
13. HANDLER COMPLETES SUCCESSFULLY
    ├─ Results collected:
    │  └─ Example: {"total_count": 12345, "duration": 30.0}
    └─ Handler returns to thread

14. UPDATE STATUS TO COMPLETED
    ├─ Status Manager updates Redis
    ├─ Status: COMPLETED
    ├─ Store results
    │  └─ Redis key: measurement:results:{status_id}
    └─ Message: "Measurement completed successfully"

    Redis final state:
    {
      "status": "COMPLETED",
      "updated_at": "2026-04-30T10:00:30.500Z",
      "message": "Measurement completed successfully",
      "results": {
        "total_count": 12345,
        "duration": 30.0,
        "live_time": 29.99,
        "real_time": 30.00
      }
    }

15. THREAD CLEANUP
    ├─ Remove from active_jobs dictionary
    ├─ Thread exits
    └─ Resources released
```

**Code Location**: `app/services/job_processor.py` - `_run_job_in_thread()` method (lines handling COMPLETED state)

---

### Phase 7: Error Handling (if something fails)

```
16. IF HANDLER ENCOUNTERS ERROR
    ├─ Exception caught in thread
    ├─ Status Manager updates Redis
    ├─ Status: FAILED
    ├─ Store error message
    │  └─ Redis key: measurement:status:{status_id}
    └─ Message: "Error: Connection timeout to detector"

    Redis error state:
    {
      "status": "FAILED",
      "error": "Connection timeout",
      "updated_at": "2026-04-30T10:00:15.000Z",
      "message": "Error: Connection timeout to detector"
    }

17. SERVICE CONTINUES
    ├─ Other jobs in other threads unaffected
    ├─ Web layer still accepting requests
    └─ Error isolated to this specific job
```

**Code Location**: `app/services/job_processor.py` - Exception handling in `_run_job_in_thread()`

---

## Status Query Flow

### When Client Queries Status

```
CLIENT:
  GET /api/v1/measurements/550e8400-e29b-41d4-a716-446655440000/status

FASTAPI Router (routes.py):
  ├─ Extract status_id from URL
  └─ Call: status_manager.get_status(status_id)

STATUS MANAGER:
  ├─ Query Redis key: measurement:status:{status_id}
  ├─ Retrieve current state from Redis
  └─ Return status object

RESPONSE:
  {
    "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
    "measurement_type": "count_rate",
    "status": "active",
    "duration_so_far": 15.5,
    "metadata": {"detector": "det_001"},
    "results": null        ← Only populated when COMPLETED
  }

Note: Can be queried anytime, even while measurement is running
```

**Code Location**: `app/api/routes.py` - `get_measurement_status()` method

---

## Stop Measurement Flow

```
CLIENT:
  DELETE /api/v1/measurements/550e8400-e29b-41d4-a716-446655440000

FASTAPI Router:
  ├─ Extract status_id from URL
  └─ Call: job_processor.stop_job(status_id)

JOB PROCESSOR:
  ├─ Look up job in active_jobs
  ├─ Set stop flag or send interrupt signal
  └─ Update status in Redis: STOPPED

MEASUREMENT HANDLER:
  ├─ Check stop signal/flag
  ├─ Gracefully shutdown
  └─ Return partial results if available

STATUS MANAGER:
  ├─ Update Redis: status = STOPPED
  └─ Keep any partial results collected so far

RESPONSE:
  {
    "status": "stopped",
    "message": "Measurement stopped by user",
    "results": {...partial results if any...}
  }
```

**Code Location**: `app/api/routes.py` - `stop_measurement()` method

---

## Component Interactions

### FastAPI Router ↔ Status Manager

```
Routes (routes.py)
   │
   ├─→ create_status(status_id, type, duration, metadata)
   ├─→ get_status(status_id)
   ├─→ get_metadata(status_id)
   ├─→ get_results(status_id)
   ├─→ update_status(status_id, state, message, results)
   └─→ delete_status(status_id)
        │
        └─→ Redis Operations
            ├─ GET measurement:status:{id}
            ├─ SET measurement:status:{id} [JSON]
            ├─ GET measurement:metadata:{id}
            ├─ SET measurement:results:{id} [JSON]
            └─ DEL measurement:*:{id}
```

### FastAPI Router ↔ Job Processor

```
Routes (routes.py - Web Layer)
   │
   ├─→ enqueue_job(status_id, measurement_type, duration)  ← ONLY enqueueing
   └─→ stop_job(status_id)  ← Mark job for stopping
        │
        └─→ Redis Job Queue (Message Broker)
            ├─ Push job to measurement_job_queue
            └─ Job awaits backend worker processing

Worker (worker.py - Backend)
   │
   ├─→ get_next_job()  ← Pull from queue
   ├─→ process_job()   ← Execute with registered handlers
   └─→ Thread Operations
       ├─ threading.Thread(target=_run_job_in_thread)
       ├─ Store in active_jobs[status_id]
       ├─ Set stop flag when stop requested
       └─ Remove from active_jobs when done
```

### Job Processor ↔ Measurement Handlers (Backend Worker Only)

```
Worker (worker.py) - Initialization Phase
   │
   ├─→ register_handler("count_rate", CountRateMeasurementHandler)
   ├─→ register_handler("save_raw_tags", SaveRawTagsMeasurementHandler)
   │
   └─→ When Job Runs:
        ├─→ Get handler class from registry
        ├─→ Instantiate: handler = HandlerClass()
        └─→ Call: handler.start()
             │
             └─→ Handler executes measurement
                 ├─ CountRateMeasurementHandler.start() → counts events
                 └─ SaveRawTagsMeasurementHandler.start() → saves tags

Note: Handlers are ONLY registered in worker.py, not in main.py
      This keeps the web layer stateless and scalable
```

---

## Data Flow Diagram

```
HTTP Request
    │
    ▼
┌─────────────────────────────────────┐
│   Pydantic Validation               │
│   (Model validation layer)          │
└─────────────────────────────────────┘
    │
    ├─ INVALID → HTTP 422 Response
    │
    └─ VALID ▼
┌─────────────────────────────────────┐
│   Generate Status ID (UUID)         │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│   Create Status in Redis            │
│   (StatusManager.create_status)     │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│   Enqueue Job                       │
│   (JobProcessor.process_job)        │
└─────────────────────────────────────┘
    │
    ├─ Return HTTP 201 Response ────→ CLIENT
    │
    └─ Spawn Thread ▼
┌─────────────────────────────────────┐
│   Update Status: QUEUED → ACTIVE    │
└─────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────┐
│   Execute Measurement Handler       │
│   (CountRate or SaveRawTags)        │
└─────────────────────────────────────┘
    │
    ├─ SUCCESS ▼                 ├─ ERROR ▼
    │                            │
    ▼                            ▼
┌──────────────────┐  ┌─────────────────────┐
│ Collect Results  │  │ Capture Error Info  │
└──────────────────┘  └─────────────────────┘
    │                            │
    ▼                            ▼
┌──────────────────────────────────────────┐
│ Update Status → COMPLETED or FAILED      │
│ Store Results in Redis                   │
└──────────────────────────────────────────┘
    │
    └─ CLIENT Queries Status via GET /status
        ▼
    ┌──────────────────────────────┐
    │ StatusManager.get_status()   │
    │ Returns current state + data │
    └──────────────────────────────┘
        │
        └─→ HTTP 200 Response
```

---

## Timing Analysis

| Phase | Component | Time | Notes |
|-------|-----------|------|-------|
| 1 | Pydantic Validation | < 1ms | Model type checking |
| 2 | UUID Generation | < 0.1ms | Quick UUID creation |
| 3 | Redis Status Create | < 5ms | Network + disk write |
| 4 | HTTP Response | < 10ms | **Total to response** |
| 5 | Thread Spawn | < 1ms | After response sent |
| 6 | Handler Execution | 10-60s | Measurement duration |
| 7 | Redis Update | < 5ms | Status + results update |
| 8 | Status Query | < 10ms | Redis GET operation |

---

## Key Points

### Request-Response Separation
- ✅ Response sent BEFORE job starts (< 10ms)
- ✅ Job runs asynchronously in background thread
- ✅ Client not blocked waiting for measurement

### Status Persistence
- ✅ All status stored in Redis
- ✅ Survives web layer restarts
- ✅ Queryable at any time
- ✅ TTL auto-cleanup after 1 hour

### Concurrent Execution
- ✅ Multiple jobs run in separate threads
- ✅ No blocking between jobs
- ✅ Each job independent
- ✅ Error in one doesn't affect others

### Error Handling
- ✅ Validation errors return immediately (HTTP 422)
- ✅ Runtime errors caught and stored
- ✅ Web layer continues functioning
- ✅ Results still available for partial jobs

---

## Debugging: Tracing a Request

### To trace a specific measurement through the system:

1. **Get the status_id** from the HTTP response
   ```bash
   # Example: "550e8400-e29b-41d4-a716-446655440000"
   ```

2. **Query Redis directly**
   ```bash
   redis-cli GET "measurement:status:550e8400-e29b-41d4-a716-446655440000"
   ```

3. **Check logs**
   - Look for status_id in logs from routes.py
   - Look for status_id in logs from job_processor.py
   - Look for handler execution logs

4. **Query status endpoint**
   ```bash
   curl http://localhost:8000/api/v1/measurements/550e8400-e29b-41d4-a716-446655440000/status
   ```

5. **Monitor active jobs**
   - In job_processor.py: check `active_jobs` dictionary
   - Thread should appear while running
   - Should disappear when done

---

## References

- **Pydantic Models**: `app/models.py`
- **Routes**: `app/api/routes.py`
- **Status Manager**: `app/services/status_manager.py`
- **Job Processor**: `app/services/job_processor.py`
- **Main App (Web Layer)**: `main.py`
- **Worker (Backend)**: `worker.py`
