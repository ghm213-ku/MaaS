"""
# Quick Start Guide - Distributed Architecture

## Prerequisites
- Redis server installed and accessible

## Quick Start (Development)

```bash
# 1. Install dependencies
pip install redis rq

# 2. Start Redis (if not already running)
redis-server

# 3. Run the application (combines web + worker in one process)
python -m uvicorn main_distributed:app --reload --port 8000
```

Open browser: http://localhost:8000/docs

## Quick Start (Production - 2 Terminals)

**Terminal 1 - Web Layer:**
```bash
python -m uvicorn main_distributed:app --host 0.0.0.0 --port 8000
```

**Terminal 2 - Backend Worker:**
```bash
python backend_worker.py
```

## Test the API

### Start Measurement
```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 10,
    "metadata": {"test": "example"}
  }'
```

Save the `measurement_id` from response.

### Query Status
```bash
curl http://localhost:8000/api/v1/measurements/{measurement_id}/status
```

### Stop Measurement
```bash
curl -X DELETE http://localhost:8000/api/v1/measurements/{measurement_id}
```

### Check Health
```bash
curl http://localhost:8000/health
```

## Architecture Summary

| Component | Purpose | Technology |
|-----------|---------|-----------|
| Web Layer | Accept requests, manage status | FastAPI |
| Message Broker | Store status, metadata, results | Redis |
| Backend Worker | Process jobs in threads | Python threading |
| Job Processor | Execute measurements | ThreadPool |
| Status Manager | Persist status in Redis | Redis client |

## Key Improvements

✅ **Decoupled**: Web layer and workers can scale independently
✅ **Fault-tolerant**: Worker failure doesn't crash web layer
✅ **Persistent**: Status survives web layer restart
✅ **Concurrent**: Multiple measurements run in parallel threads
✅ **Stateless**: Web layer is truly stateless
✅ **Easy to understand**: Simple threading model, Redis for storage

## File Structure

```
app/
  api/
    routes_distributed.py    ← New distributed routes
  services/
    status_manager.py        ← Redis status management
    job_processor.py         ← Thread-based job processor
    
main_distributed.py          ← New distributed app entry point
backend_worker.py            ← Backend worker service
DISTRIBUTED_ARCHITECTURE.md  ← Full documentation
```

## Differences from Monolithic

| Feature | Old | New |
|---------|-----|-----|
| Processing | Synchronous | Asynchronous (enqueued) |
| Status Storage | In-memory | Redis persistent |
| Concurrency | Sequential | Thread-per-job |
| Response Time | Long (waits for completion) | Instant (returns status ID) |
| Scalability | Single process | Multiple processes |
| Error Handling | Blocks on error | Graceful failure |

## Next Steps

1. Review `DISTRIBUTED_ARCHITECTURE.md` for detailed documentation
2. Run tests: `pytest tests/ -v`
3. Try the API examples above
4. Deploy backend workers as needed for capacity
"""
