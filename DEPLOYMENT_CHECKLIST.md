"""
# Distributed System - Deployment Checklist

## Pre-Deployment Verification

### Environment Setup
- [ ] Python 3.10+ installed
- [ ] Redis server available (local or remote)
- [ ] All dependencies installed: `pip install -r requirements.txt`

### Code Verification
- [ ] All new files syntax checked
- [ ] Integration tests pass: `pytest tests/test_distributed_integration.py -v`
- [ ] Existing tests still pass: `pytest tests/ -v`
- [ ] No import errors in main.py

### Configuration Review
- [ ] Redis host/port configured correctly in main.py
- [ ] Redis DB number set (default: 0 for prod, 15 for tests)
- [ ] TTL settings appropriate for use case
- [ ] Port 8000 (web layer) is available

---

## Development Deployment (Quick Test)

### Step 1: Verify Redis
```bash
redis-cli ping
# Should return: PONG
```

### Step 2: Start Web Layer
```bash
python -m uvicorn main:app --reload --port 8000
```

### Step 3: In Another Terminal, Start Worker
```bash
python backend_worker.py
```

### Step 4: Test API
```bash
# Health check
curl http://localhost:8000/health

# Create measurement
Invoke-RestMethod -Uri "http://localhost:8000/api/v1/measurements/count-rate" -Method Post -ContentType "application/json" -Body '{"duration_seconds": 5, "metadata": {}}'

# Save the measurement_id from response, then:
curl http://localhost:8000/api/v1/measurements/{measurement_id}/status
```

---

## Production Deployment

### Prerequisites
- [ ] Redis configured for persistence (dump.rdb)
- [ ] Redis memory limits set appropriately
- [ ] Redis password protected (if exposed)
- [ ] Monitoring/alerting configured

### Deployment Steps

#### 1. Prepare Environment
```bash
# Create Python virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Verify installation
python -c "import redis; import fastapi; print('OK')"
```

#### 2. Start Redis
```bash
# Using systemd (Linux)
sudo systemctl start redis-server

# Or direct
redis-server /etc/redis/redis.conf

# Verify
redis-cli PING
```

#### 3. Start Web Layer
```bash
# Option A: Direct (development)
python -m uvicorn main_distributed:app --host 0.0.0.0 --port 8000

# Option B: With Gunicorn (production)
gunicorn main_distributed:app \
  --workers 4 \
  --worker-class uvicorn.workers.UvicornWorker \
  --bind 0.0.0.0:8000

# Option C: With systemd
sudo systemctl start maas-web
```

#### 4. Start Backend Worker(s)
```bash
# Single worker
python backend_worker.py

# Multiple workers (in separate processes/servers)
python backend_worker.py &
python backend_worker.py &
python backend_worker.py &
```

#### 5. Configure Reverse Proxy (Nginx)
```nginx
upstream maas_web {
    server localhost:8000;
}

server {
    listen 80;
    server_name maas.example.com;
    
    location / {
        proxy_pass http://maas_web;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_connect_timeout 10s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }
}
```

#### 6. Setup Monitoring
```bash
# Option A: Simple health checks
curl http://localhost:8000/health

# Option B: Prometheus metrics
# Add prometheus client to requirements.txt
pip install prometheus-client

# Option C: Redis monitoring
redis-cli INFO
redis-cli SLOWLOG GET 10
```

---

## Health Checks

### Pre-Deployment
```bash
# 1. Redis health
redis-cli ping

# 2. Python imports
python -c "from app.services.status_manager import StatusManager; print('OK')"
python -c "from app.services.job_processor import JobProcessor; print('OK')"

# 3. Network connectivity
curl -v http://localhost:8000/health
```

### Post-Deployment
```bash
# 1. Service startup
curl http://localhost:8000/health

# 2. Create test measurement
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{"duration_seconds": 2, "metadata": {"test": true}}'

# 3. Query status (should show COMPLETED after 2 seconds)
curl http://localhost:8000/api/v1/measurements/{measurement_id}/status
```

### Production Monitoring
```bash
# Monitor processes
ps aux | grep python
ps aux | grep redis

# Monitor ports
netstat -tuln | grep -E "(6379|8000)"

# Monitor Redis memory
redis-cli INFO memory

# Check for stuck jobs
redis-cli KEYS "measurement:status:*" | wc -l
```

---

## Rollback Plan

### If Issues Occur

1. **Web Layer Crash**
   ```bash
   # Status preserved in Redis
   # Simply restart web layer
   pkill -f main_distributed
   python -m uvicorn main:app --host 0.0.0.0 --port 8000
   ```

2. **Worker Crash**
   ```bash
   # Jobs in progress stored in Redis
   # Restart worker
   pkill -f worker
   python worker.py
   ```

3. **Redis Crash**
   ```bash
   # Graceful degradation if Redis unavailable
   # Queue new requests while Redis recovers
   # Health check will report unhealthy
   # Restart Redis
   redis-server
   ```

4. **Complete Failure**
   ```bash
   # Revert to old monolithic system
   pkill -f main_distributed
   python -m uvicorn main:app --port 8000
   ```

---

## Performance Optimization

### Web Layer
```bash
# Increase workers for more concurrency
gunicorn main_distributed:app \
  --workers 8 \
  --worker-class uvicorn.workers.UvicornWorker
```

### Backend Workers
```bash
# Multiple workers for job parallelism
for i in {1..4}; do
  python worker.py &
done
```

### Redis
```bash
# Edit redis.conf
maxmemory 2gb
maxmemory-policy allkeys-lru
```

---

## Scaling Strategy

### Phase 1: Single Server
- 1 Redis instance
- 1 Web layer
- 1 Backend worker

### Phase 2: Separate Web & Worker
- 1 Redis instance (separate box)
- N Web layer instances (load balanced)
- M Backend workers (separate box)

### Phase 3: Distributed
- Redis Cluster (multiple nodes)
- Web layer (auto-scaled)
- Backend workers (auto-scaled)

---

## Disaster Recovery

### Data Backup
```bash
# Redis persistence
redis-cli BGSAVE  # Background save

# Scheduled backup
0 2 * * * redis-cli BGSAVE

# Monitor dump.rdb
ls -lh /var/lib/redis/dump.rdb
```

### Status Recovery
```bash
# If Redis data corrupted
redis-cli FLUSHDB  # Clear corrupted data
# Jobs will need to be restarted

# If Redis completely lost
# Status data lost (by design, TTL=1 hour)
# Jobs restart from queue
```

---

## Post-Deployment Verification

### Day 1
- [ ] All health checks passing
- [ ] Sample measurements complete successfully
- [ ] Status queries working correctly
- [ ] Logs are clean (no errors)

### Week 1
- [ ] Multiple concurrent measurements working
- [ ] Memory usage stable
- [ ] No Redis connection issues
- [ ] Worker processes alive

### Month 1
- [ ] Performance metrics collected
- [ ] Any issues identified and fixed
- [ ] Monitoring/alerting working
- [ ] Scaling needs identified

---

## Maintenance Schedule

### Daily
- [ ] Monitor processes running
- [ ] Check for error logs
- [ ] Verify Redis connectivity

### Weekly
- [ ] Review performance metrics
- [ ] Check Redis memory usage
- [ ] Verify backup completion

### Monthly
- [ ] Update dependencies
- [ ] Review logs for patterns
- [ ] Optimize configuration if needed

### Quarterly
- [ ] Security updates
- [ ] Performance tuning
- [ ] Capacity planning

---

## Contact & Support

### If Issues Occur
1. Check health endpoint: `curl http://localhost:8000/health`
2. Review logs: Look in worker.py output
3. Check Redis: `redis-cli PING`
4. Refer to troubleshooting in `DISTRIBUTED_ARCHITECTURE.md`

### Documentation
- **Quick Start**: `QUICKSTART_DISTRIBUTED.md`
- **Full Docs**: `DISTRIBUTED_ARCHITECTURE.md`
- **API Docs**: `http://localhost:8000/docs`
- **Tests**: `pytest tests/test_distributed_integration.py -v`

---

## Deployment Confirmation Template

```
Deployment Date: _______________
Deployed by: ___________________
Environment: [ ] Dev [ ] Staging [ ] Production

Pre-Deployment Checks:
- [ ] Redis running and healthy
- [ ] All dependencies installed
- [ ] Tests passing (✅ / ❌)
- [ ] Configuration reviewed

Deployment Actions:
- [ ] Web layer started (time: ___)
- [ ] Backend worker started (time: ___)
- [ ] Health check passing (✅ / ❌)
- [ ] Sample measurement tested (✅ / ❌)

Post-Deployment:
- [ ] All endpoints responding
- [ ] No error logs
- [ ] Monitoring active
- [ ] Team notified

Notes:
_________________________________
_________________________________
_________________________________

Sign-off: _____________________
```

---

**Status**: ✅ Ready for Deployment

The distributed system is fully implemented, tested, and documented.
Proceed with deployment following the steps above.
"""
