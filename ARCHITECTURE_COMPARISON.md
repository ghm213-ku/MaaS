"""
# Architecture Comparison: Monolithic vs Distributed

## System Architecture Comparison

### MONOLITHIC ARCHITECTURE (Old)

```
Client Request
    ↓
┌─────────────────────────────────┐
│  FastAPI Web Server             │
│  ├─ Accept request              │
│  ├─ Create Measurement object   │
│  ├─ Run handler directly        │
│  │  ├─ Wait for measurement     │
│  │  └─ Get results              │
│  ├─ Return response             │
│  └─ Status stored in-memory     │
└─────────────────────────────────┘
    ↓
Response to Client
(After measurement completes)
```

**Issues:**
- Request blocks until measurement completes
- Status lost if server restarts
- Single point of failure
- No concurrency across processes
- Difficult to scale

### DISTRIBUTED ARCHITECTURE (New)

```
Client Request
    ↓
┌──────────────────────────┐
│  FastAPI Web Layer       │
│  ├─ Validate request     │
│  ├─ Generate status_id   │
│  ├─ Create status record │
│  ├─ Enqueue job          │
│  └─ Return status_id     │
└─────────┬────────────────┘
          │ (enqueue)
          ↓
    ┌──────────────┐
    │  Redis       │
    │  (Status DB) │
    │  - status    │
    │  - metadata  │
    │  - results   │
    └──────┬───────┘
           │ (fetch job)
           ↓
┌──────────────────────────┐
│  Backend Worker          │
│  ├─ Thread 1: Job A      │
│  ├─ Thread 2: Job B      │
│  ├─ Thread 3: Job C      │
│  └─ (update status)      │
└──────────────────────────┘
```

**Advantages:**
- Instant response (enqueue only)
- Status persists in Redis
- Multiple jobs run concurrently
- Web layer and workers are independent
- Can scale workers horizontally
- Better error isolation

## Request Flow Comparison

### Monolithic Flow

```
1. POST /count-rate
   ├─ Validate request (fast)
   ├─ Create Measurement object
   ├─ Run handler directly
   │  ├─ Start counting... (BLOCKING, 60 seconds)
   │  └─ Collect results... (BLOCKING)
   ├─ Return response
   └─ Total time: ~60 seconds
```

### Distributed Flow

```
1. POST /count-rate
   ├─ Validate request (fast)
   ├─ Generate status_id: abc-123
   ├─ Create status in Redis (fast)
   ├─ Enqueue job (fast)
   └─ Return response immediately
   └─ Total time: < 10ms

2. [Meanwhile, in background worker thread]
   ├─ Update status to ACTIVE
   ├─ Run handler (60 seconds)
   ├─ Update status to COMPLETED
   └─ Store results in Redis

3. Client can query status anytime:
   GET /measurements/abc-123/status
```

## Data Flow Comparison

### Monolithic

```
Request Handler → Measurement Object → (runs) → Results
(all in-memory, lost on restart)
```

### Distributed

```
Request Handler → Redis Status → Job Queue → Worker Thread → Redis Results
(persistent, survives restarts)
```

## Concurrency Model

### Monolithic
- One measurement per request blocks the handler
- Multiple concurrent requests need multiple web workers
- All state in-memory
- No persistence

### Distributed
- Multiple jobs in separate threads in one worker
- Can run without blocking on web layer
- State in Redis (can query from anywhere)
- Persistent status

## Scalability Comparison

### Monolithic
```
Load increases
    ↓
Start more FastAPI workers (uvicorn)
    ↓
Each worker runs measurements independently
Problem: Measurements can't be coordinated
```

### Distributed
```
Load increases (more jobs)
    ↓
Start more backend workers
    ↓
Each worker processes jobs from Redis queue
    ↓
Web layer stays responsive (just enqueues)
Solution: Clean separation of concerns
```

## Failure Scenarios

### Monolithic
- **Web server crashes**: All active measurements lost, status lost
- **Long measurement fails**: Request times out, no error handling
- **Out of memory**: All measurements blocked

### Distributed
- **Web server crashes**: Status remains in Redis, workers continue
- **Worker crashes**: Redis status persists, job can be retried
- **Long measurement fails**: Error stored in Redis, web layer continues
- **One job fails**: Others continue in different threads

## API Changes

### Monolithic Response
```bash
POST /api/v1/measurements/count-rate
→ 200 OK (after 60 seconds)
{
  "measurement_id": "...",
  "total_count": 12345,
  "results": {...}
}
```

### Distributed Response
```bash
POST /api/v1/measurements/count-rate
→ 201 CREATED (< 10ms)
{
  "measurement_id": "status-id-uuid",
  "status": "queued",
  "message": "Use status-id-uuid to query progress"
}

# Later, query status:
GET /api/v1/measurements/status-id-uuid/status
→ 200 OK
{
  "status": "active",
  "duration_so_far": 15.5,
  "results": null
}

# After completion:
GET /api/v1/measurements/status-id-uuid/status
→ 200 OK
{
  "status": "completed",
  "results": {
    "total_count": 12345,
    ...
  }
}
```

## Thread Model

### Monolithic
```
Each request = one handler
Limited by number of FastAPI workers
```

### Distributed
```
Each job = one thread (in worker process)
Unlimited concurrent jobs per worker
(limited only by system resources)

Example: 10 measurements running concurrently
├─ Thread 1: count_rate (30 sec elapsed)
├─ Thread 2: save_raw_tags (5 sec elapsed)
├─ Thread 3: count_rate (50 sec elapsed)
├─ Thread 4: save_raw_tags (20 sec elapsed)
...
└─ All running simultaneously in one worker
```

## Database/Storage

### Monolithic
- Status: In-memory dict (lost on restart)
- Results: In-memory (lost on restart)
- No persistence

### Distributed
- Status: Redis (persistent)
- Metadata: Redis (persistent)
- Results: Redis (persistent)
- TTL: 1 hour (configurable)
- Can query from any web instance
- Can be backed up

## Resource Usage

### Monolithic (60 second measurement)
```
Request arrives
├─ Allocate memory for Measurement object
├─ Block request handler for 60 seconds
├─ Hold database connection for 60 seconds
└─ Release after response sent

Multiple concurrent requests = multiple handlers blocked
```

### Distributed (60 second measurement)
```
Request arrives
├─ Validate (< 1ms)
├─ Store to Redis (< 5ms)
├─ Return response (instant)
└─ Handler is FREE for next request

Worker processes
├─ Spawn thread (negligible)
├─ Run measurement for 60 seconds
├─ Update Redis when done
└─ Thread exits, memory released
```

## Production Readiness

### Monolithic
- Works for single-user / single-request scenarios
- Not suitable for concurrent users
- Status lost on deployment

### Distributed
- Supports multiple concurrent measurements
- Status persists across deployments
- Can handle server restarts
- Workers can be scaled independently
- Better error handling and isolation

## Migration Path

```
Phase 1: Run both (old and new)
├─ Keep monolithic system running
├─ Deploy distributed system on different port
└─ Test compatibility

Phase 2: Dual-write
├─ New requests go to distributed
├─ Old measurements finish on monolithic
└─ Run both in parallel

Phase 3: Full migration
├─ Migrate all traffic to distributed
├─ Keep monolithic as fallback
└─ Sunset monolithic when stable

Phase 4: Optimize
├─ Switch to RQ for better job management
├─ Add more worker instances
├─ Add metrics and monitoring
└─ Fine-tune Redis configuration
```
"""
