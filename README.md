# MaaS - Measurements as a Service

A modern, distributed system for running long-running measurements (count-rate, spectrum analysis, 
tag recording, etc.) without blocking your application.

**Key Feature**: Start a measurement and get an instant response. Query status anytime. No waiting.

---

## 🚀 Quick Start

### Requirements
- Python 3.10+
- Redis Server
- pip / Python package manager

### Get Started in 30 seconds

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Start Redis (in one terminal)
redis-server

# 3. Start MaaS (in another terminal)
python -m uvicorn main:app --reload

# 4. Try it! (in a third terminal)
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{"duration_seconds": 10, "metadata": {"detector": "test"}}'

# 5. Save the measurement_id from response, then query:
curl http://localhost:8000/api/v1/measurements/{measurement_id}/status
```

**API Documentation**: Visit `http://localhost:8000/docs`

---

## 📚 Documentation

Comprehensive documentation tailored to different audiences. All developer documentation is now consolidated into focused, single-purpose guides:

| Document | Audience | Purpose |
|----------|----------|---------|
| [docs/README_USER_GUIDE.md](docs/README_USER_GUIDE.md) | **End Users** | How to use MaaS APIs, measurement types, integration examples |
| [docs/README_SYSTEM_FLOW.md](docs/README_SYSTEM_FLOW.md) | **Architects/DevOps** | System architecture, request flow, component interactions, timing analysis |
| [docs/README_DEVELOPER_GUIDE.md](docs/README_DEVELOPER_GUIDE.md) | **Developers** | Setup, running locally, debugging, extending with new measurement types |
| [docs/DEPLOYMENT_CHECKLIST.md](docs/DEPLOYMENT_CHECKLIST.md) | **DevOps** | Pre-deployment verification, deployment steps, troubleshooting |
| [docs/CHANNEL_MANAGEMENT_GUIDE.md](docs/CHANNEL_MANAGEMENT_GUIDE.md) | **All** | Channel booking system (48 exclusive channels), lifecycle, API endpoints |

---

## 🏗️ System Architecture

```
Client Request
    ↓
FastAPI Web Layer (instant response, < 10ms)
    ↓
Redis Message Broker (persistent status storage)
    ↓
Backend Worker (thread-per-job execution)
    ↓
Measurement Handler (count-rate, save-raw-tags, custom)
```

**Key Benefits:**
- ✅ Instant response (< 10ms)
- ✅ Persistent status in Redis
- ✅ Concurrent job execution (threads)
- ✅ Independent scaling (web vs workers)
- ✅ Graceful error handling

---

## 📦 Project Structure

```
MaaS/
├── app/                          ← Application code
│   ├── api/
│   │   └── routes.py             ← FastAPI endpoints
│   ├── services/
│   │   ├── status_manager.py     ← Redis status storage
│   │   ├── job_processor.py      ← Thread-based job execution
│   │   ├── count_rate.py         ← Count-rate handler
│   │   ├── save_raw_tags.py      ← Save-raw-tags handler
│   │   ├── coincidences.py       ← Coincidences handler
│   │   ├── correlation.py        ← Correlation handler
│   │   ├── file_logger.py        ← File logging service
│   │   └── measurement.py        ← Original monolithic service (legacy)
│   ├── models.py                 ← Pydantic request/response models
│   ├── payloads.py               ← Measurement payload mapping and schemas
│   └── utils/
│       ├── logger.py             ← Logging configuration
│       ├── path_utils.py         ← Path formatting utilities
│       └── ssl_utils.py          ← SSL/TLS utilities
│
├── tests/
│   ├── test_distributed_integration.py ← Integration tests
│   ├── test_file_logger.py              ← File logging tests
│   └── test_*.py                        ← Unit tests
│
├── request_logs/                 ← Log files (created at runtime)
│   ├── channel_requests.txt      ← Channel booking/release log
│   └── measurement_requests.txt  ← Measurement requests log
│
├── main.py                       ← Web layer entry point
├── worker.py                     ← Backend worker process
│
├── README.md                     ← This file
├── README_USER_GUIDE.md          ← For users
├── README_SYSTEM_FLOW.md         ← How requests flow through system
├── README_EXTENDING.md           ← How to add measurement types
├── README_DEVELOPER_GUIDE.md     ← For developers
├── DISTRIBUTED_ARCHITECTURE.md   ← Technical architecture reference
├── DEPLOYMENT_CHECKLIST.md       ← Deployment verification
├── CHANNEL_MANAGEMENT_GUIDE.md   ← Channel booking system
│
├── requirements.txt              ← Python dependencies
└── pytest.ini                    ← Pytest configuration
```

---

## 🎯 Measurement Types

### Count-Rate

Counts detector events over time.

```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 60,
    "metadata": {"detector": "main", "source": "lab_a"}
  }'
```

### Save-Raw-Tags

Records all detector events to a file.

```bash
curl -X POST http://localhost:8000/api/v1/measurements/save-raw-tags \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 30,
    "metadata": {
      "channel_list": [1, 2, 3],
      "target_file_path": "C:\\data\\output.dat"
    }
  }'
```

### Custom Measurements

Add your own! See [README_EXTENDING.md](README_EXTENDING.md)

---

## 🔧 Development

### Run Tests

```bash
# All tests
pytest tests/ -v

# Integration tests only
pytest tests/test_distributed_integration.py -v

# Specific test
pytest tests/test_distributed_integration.py::TestStatusManagerWithRedis -v
```

### Debug a Measurement

1. **Check system health**: `curl http://localhost:8000/health`
2. **Query Redis**: `redis-cli GET measurement:status:{id}`
3. **Check logs**: Look for status_id in terminal output
4. **Query status**: `curl http://localhost:8000/api/v1/measurements/{id}/status`

See [README_DEVELOPER_GUIDE.md](README_DEVELOPER_GUIDE.md) for detailed debugging.

### Add New Measurement Type

1. Create Pydantic model in `app/models.py`
2. Create handler in `app/services/my_handler.py`
3. Register in `main.py` and `worker.py`
4. Write tests in `tests/test_my_handler.py`

See [README_EXTENDING.md](README_EXTENDING.md) for step-by-step guide.

---

## 🚀 Deployment

### Development (Single Process)

```bash
python -m uvicorn main:app --reload --port 8000
```

### Production (Separate Processes)

```bash
# Terminal 1: Web Layer
python -m uvicorn main:app --host 0.0.0.0 --port 8000

# Terminal 2: Backend Worker (can run on different machine)
python worker.py
```

### With Docker

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .

# Web layer
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

# Backend worker (different Dockerfile or CMD)
# CMD ["python", "worker.py"]
```

See [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md) for detailed steps.

---

## 🔑 Key Components

### StatusManager
Stores measurement status in Redis. Provides interface for creating, updating, and querying status.

**Location**: `app/services/status_manager.py`

```python
status_manager.create_status(status_id, "count_rate", 30, metadata)
status = status_manager.get_status(status_id)
status_manager.update_status(status_id, "active", "Running...", None)
```

### JobProcessor
Manages job execution in separate threads (runs in backend worker). 
Registers and routes to measurement handlers.

**Location**: `app/services/job_processor.py` (core class)
**Handler Registration**: `worker.py` (backend worker process)

```python
# Backend Worker (worker.py)
processor.register_handler("count_rate", CountRateMeasurementHandler)
processor.process_job(status_id, "count_rate", duration)
processor.stop_job(status_id)
```

### API Routes
FastAPI endpoints for starting measurements, querying status, stopping jobs.

**Location**: `app/api/routes.py`

```
POST   /api/v1/measurements/count-rate
POST   /api/v1/measurements/save-raw-tags
GET    /api/v1/measurements/{id}/status
DELETE /api/v1/measurements/{id}
```

---

## 📊 API Examples

### Python

```python
import requests

# Start measurement
resp = requests.post(
    "http://localhost:8000/api/v1/measurements/count-rate",
    json={"duration_seconds": 60, "metadata": {"detector": "main"}}
)
measurement_id = resp.json()["measurement_id"]

# Poll for completion
import time
while True:
    status = requests.get(
        f"http://localhost:8000/api/v1/measurements/{measurement_id}/status"
    ).json()
    
    if status["status"] == "completed":
        print(f"Results: {status['results']}")
        break
    
    print(f"Running... {status['duration_so_far']:.1f}s")
    time.sleep(1)
```

### JavaScript

```javascript
// Start measurement
const resp = await fetch("http://localhost:8000/api/v1/measurements/count-rate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ duration_seconds: 60, metadata: { detector: "main" } })
});
const { measurement_id } = await resp.json();

// Poll for completion
while (true) {
  const status = await fetch(
    `http://localhost:8000/api/v1/measurements/${measurement_id}/status`
  ).then(r => r.json());
  
  if (status.status === "completed") {
    console.log("Results:", status.results);
    break;
  }
  
  console.log(`Running... ${status.duration_so_far.toFixed(1)}s`);
  await new Promise(r => setTimeout(r, 1000));
}
```

See [README_USER_GUIDE.md](README_USER_GUIDE.md) for more examples.

---

## 🐛 Troubleshooting

### "Connection refused" to Redis
```bash
# Start Redis
redis-server

# Verify connection
redis-cli ping  # Should return PONG
```

### Measurement doesn't complete
```bash
# 1. Check backend worker is running
ps aux | grep backend_worker.py

# 2. Check Redis health
redis-cli INFO memory

# 3. Check logs for errors
# Look in terminal where backend_worker.py is running
```

### Results are null
```bash
# Check if status is really completed
curl http://localhost:8000/api/v1/measurements/{id}/status

# Status should be "completed", not "active"
```

See [README_DEVELOPER_GUIDE.md](README_DEVELOPER_GUIDE.md#troubleshooting) for more troubleshooting.

---

## 📖 Documentation Map

- **Just starting?** → [README_USER_GUIDE.md](README_USER_GUIDE.md)
- **Need to debug?** → [README_DEVELOPER_GUIDE.md](README_DEVELOPER_GUIDE.md)
- **Want to understand the flow?** → [README_SYSTEM_FLOW.md](README_SYSTEM_FLOW.md)
- **Ready to extend?** → [README_EXTENDING.md](README_EXTENDING.md)
- **Deploying?** → [DEPLOYMENT_CHECKLIST.md](DEPLOYMENT_CHECKLIST.md)
- **Quick reference?** → See Quick Start above

---

## 🛠️ Technology Stack

- **Framework**: FastAPI 0.115.0
- **Validation**: Pydantic v2.9.2
- **Message Broker**: Redis
- **Job Execution**: Python threading
- **Testing**: pytest with asyncio
- **Runtime**: Python 3.13+

---

## 📝 License

[Your License Here]

---

## 🤝 Contributing

1. Read the documentation
2. Write tests for new features
3. Follow code style guidelines
4. Update documentation as needed
5. Submit PR

---

## ❓ FAQ

**Q: How do I add a new measurement type?**
A: See [README_EXTENDING.md](README_EXTENDING.md)

**Q: Can I run multiple measurements concurrently?**
A: Yes! That's a key feature of the distributed architecture.

**Q: How does status persist across restarts?**
A: Status is stored in Redis, which persists independently.

**Q: Can I deploy web and worker on separate machines?**
A: Yes! Just point both to the same Redis instance.

**Q: What's the maximum duration for a measurement?**
A: Default is 3600 seconds (1 hour). See configuration for adjustments.

---

## 📞 Support

- **Bug Reports**: Check issues or create new one
- **Questions**: See documentation above
- **Deployment Help**: See DEPLOYMENT_CHECKLIST.md
- **Debugging**: See README_DEVELOPER_GUIDE.md

---

## ✨ Features

- ✅ Instant response (< 10ms) regardless of measurement duration
- ✅ Persistent status storage (Redis)
- ✅ Concurrent job execution (threads)
- ✅ Independent web and worker scaling
- ✅ Graceful error handling and isolation
- ✅ Built-in health checks
- ✅ Comprehensive logging
- ✅ Easy to extend (add measurement types)
- ✅ Production-ready
- ✅ Thoroughly tested

---

**Version**: 2.0 (Distributed Architecture)  
**Status**: ✅ Production Ready
