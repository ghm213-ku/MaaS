"""
# User Guide - How to Use MaaS

## Overview

MaaS (Measurements as a Service) is a distributed system for running long-running measurements 
(count-rate, spectrum analysis, tag recording, etc.) without blocking your application.

**Key Benefit**: Start a measurement and get an instant response with a status ID. Query the 
status anytime, stop when needed.

---

## Quick Start (3 minutes)

### 1. Access the API

The MaaS API is available at: `http://localhost:8000` (or your server)

**API Documentation**: Visit `http://localhost:8000/docs` for interactive documentation

### 2. Check System Health

```bash
curl http://localhost:8000/health
```

Response shows system status:
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

### 3. Start Your First Measurement

```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 10,
    "metadata": {
      "detector": "Main Detector",
      "source": "Lab A"
    }
  }'
```

**Response** (instant, < 10ms):
```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "queued",
  "started_at": "2026-04-30T10:00:00Z",
  "message": "Count-rate measurement queued. Use ID '550e8400-e29b-41d4-a716-446655440000' to query status."
}
```

### 4. Query the Status

Save the `measurement_id` from the response above, then:

```bash
curl http://localhost:8000/api/v1/measurements/550e8400-e29b-41d4-a716-446655440000/status
```

**Response while running**:
```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "active",
  "started_at": "2026-04-30T10:00:00Z",
  "duration_so_far": 3.5,
  "metadata": {
    "detector": "Main Detector",
    "source": "Lab A"
  },
  "results": null
}
```

**Response after completion**:
```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "completed",
  "started_at": "2026-04-30T10:00:00Z",
  "duration_so_far": 10.0,
  "metadata": {
    "detector": "Main Detector",
    "source": "Lab A"
  },
  "results": {
    "total_count": 12345,
    "live_time": 9.99,
    "real_time": 10.00
  }
}
```

---

## Available Measurement Types

### 1. Count-Rate Measurement

Counts detector events over a period of time.

**Endpoint**: `POST /api/v1/measurements/count-rate`

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 60,
    "metadata": {
      "detector_id": "det_001",
      "high_voltage": 1200,
      "source": "lab_b"
    }
  }'
```

**Metadata Fields** (optional - customize as needed):
- `detector_id`: Identifier for the detector
- `high_voltage`: HV setting
- `source`: Source location or identifier
- Any other custom fields

**Results**: 
- `total_count`: Total number of events detected
- `live_time`: Live time (dead-time corrected)
- `real_time`: Real/wall clock time

---

### 2. Save Raw Tags Measurement

Records all detector events (tags) to a file for offline analysis.

**Endpoint**: `POST /api/v1/measurements/save-raw-tags`

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/measurements/save-raw-tags \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 30,
    "metadata": {
      "channel_list": [1, 2, 3, 4],
      "target_file_path": "C:\\data\\measurement_001.dat"
    }
  }'
```

**Required Metadata Fields**:
- `channel_list`: List of channel numbers to record (e.g., `[1,2,3]`)
- `target_file_path`: Where to save the data file (must be absolute path)

**Results**:
- `file_path`: Actual path where file was saved
- `total_events`: Number of events recorded
- `file_size`: Size of saved file in bytes

---

## Advanced Usage

### Polling for Completion (Python Example)

```python
import requests
import time

# Start measurement
response = requests.post(
    "http://localhost:8000/api/v1/measurements/count-rate",
    json={
        "duration_seconds": 60,
        "metadata": {"detector": "main"}
    }
)
measurement_id = response.json()["measurement_id"]

# Poll for completion
base_url = "http://localhost:8000/api/v1/measurements"
while True:
    status_resp = requests.get(f"{base_url}/{measurement_id}/status")
    status_data = status_resp.json()
    
    if status_data["status"] == "completed":
        print(f"Results: {status_data['results']}")
        break
    elif status_data["status"] == "failed":
        print(f"Error: {status_data}")
        break
    
    print(f"Still running... {status_data['duration_so_far']:.1f}s elapsed")
    time.sleep(2)
```

### Stop a Measurement Early

```bash
curl -X DELETE http://localhost:8000/api/v1/measurements/550e8400-e29b-41d4-a716-446655440000
```

Response:
```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "stopped",
  "message": "Measurement stopped by user",
  "results": {
    "total_count": 6789,
    "duration": 5.12
  }
}
```

### Batch Measurements (JavaScript Example)

```javascript
async function startMultipleMeasurements() {
  const baseUrl = "http://localhost:8000/api/v1/measurements";
  
  // Start 3 measurements
  const measurements = [];
  
  for (let i = 0; i < 3; i++) {
    const response = await fetch(`${baseUrl}/count-rate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        duration_seconds: 30,
        metadata: { detector: `detector_${i+1}` }
      })
    });
    
    const data = await response.json();
    measurements.push(data.measurement_id);
    console.log(`Started measurement ${i+1}: ${data.measurement_id}`);
  }
  
  // Poll all measurements
  let completed = 0;
  while (completed < measurements.length) {
    completed = 0;
    
    for (const id of measurements) {
      const response = await fetch(`${baseUrl}/${id}/status`);
      const data = await response.json();
      
      if (data.status === "completed") {
        console.log(`✓ Measurement ${id.slice(0,8)}... completed`);
        completed++;
      }
    }
    
    if (completed < measurements.length) {
      await new Promise(r => setTimeout(r, 1000));  // Wait 1 second
    }
  }
}

startMultipleMeasurements();
```

---

## Understanding Status Values

| Status | Meaning | Next Action |
|--------|---------|------------|
| `queued` | Waiting to start | Poll for `active` or `completed` |
| `active` | Currently running | Keep polling or stop if needed |
| `completed` | Finished successfully | Results are available |
| `stopped` | Stopped by user (DELETE) | Partial results may be available |
| `failed` | Error occurred | Check error message in response |

---

## Understanding Responses

### Successful Measurement Response

```json
{
  "measurement_id": "550e8400-e29b-41d4-a716-446655440000",
  "measurement_type": "count_rate",
  "status": "completed",
  "started_at": "2026-04-30T10:00:00.000Z",
  "duration_so_far": 60.123,
  "metadata": {
    "detector": "main",
    "source": "lab_a"
  },
  "results": {
    "total_count": 123456,
    "live_time": 59.99,
    "real_time": 60.00
  }
}
```

**Fields**:
- `measurement_id`: UUID for this measurement (use to query status)
- `measurement_type`: Type of measurement performed
- `status`: Current state (queued, active, completed, stopped, failed)
- `started_at`: ISO timestamp when measurement started
- `duration_so_far`: How long the measurement has been running
- `metadata`: The metadata you provided
- `results`: Results (only populated when completed)

### Error Response (HTTP 422 - Validation Error)

```json
{
  "detail": [
    {
      "type": "missing",
      "loc": ["body", "metadata", "channel_list"],
      "msg": "Field required",
      "input": {
        "duration_seconds": 30,
        "metadata": {
          "target_file_path": "C:\\data.dat"
        }
      }
    }
  ]
}
```

**Common Errors**:
- Missing required fields → HTTP 422
- Invalid field types → HTTP 422
- Measurement not found → HTTP 404
- Server error → HTTP 500

---

## Tips & Best Practices

### ✅ DO

- Use reasonable `duration_seconds` values (1-3600 seconds)
- Poll status every 1-5 seconds (don't hammer the API)
- Use unique detector/source identifiers in metadata
- Handle errors gracefully in your code
- Stop measurements you no longer need

### ❌ DON'T

- Don't use very large duration values (> 1 hour)
- Don't poll more frequently than every 100ms
- Don't assume measurements complete immediately
- Don't forget to check `results` is not null before accessing
- Don't hardcode IP addresses; use configuration

---

## Integration Examples

### Python Integration

```python
import requests
from datetime import datetime

class MaaSClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.base_endpoint = f"{base_url}/api/v1/measurements"
    
    def start_count_rate(self, duration_seconds, detector_id):
        """Start a count-rate measurement."""
        response = requests.post(
            f"{self.base_endpoint}/count-rate",
            json={
                "duration_seconds": duration_seconds,
                "metadata": {"detector": detector_id}
            }
        )
        return response.json()
    
    def get_status(self, measurement_id):
        """Get measurement status."""
        response = requests.get(
            f"{self.base_endpoint}/{measurement_id}/status"
        )
        return response.json()
    
    def wait_for_completion(self, measurement_id, poll_interval=2):
        """Wait for measurement to complete."""
        while True:
            status = self.get_status(measurement_id)
            
            if status["status"] in ["completed", "stopped", "failed"]:
                return status
            
            print(f"Running... {status['duration_so_far']:.1f}s elapsed")
            time.sleep(poll_interval)

# Usage
client = MaaSClient()
resp = client.start_count_rate(60, "detector_1")
measurement_id = resp["measurement_id"]

result = client.wait_for_completion(measurement_id)
print(f"Final results: {result['results']}")
```

### Node.js Integration

```javascript
class MaaSClient {
  constructor(baseUrl = "http://localhost:8000") {
    this.baseUrl = baseUrl;
    this.endpoint = `${baseUrl}/api/v1/measurements`;
  }
  
  async startCountRate(durationSeconds, detectorId) {
    const response = await fetch(`${this.endpoint}/count-rate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        duration_seconds: durationSeconds,
        metadata: { detector: detectorId }
      })
    });
    return response.json();
  }
  
  async getStatus(measurementId) {
    const response = await fetch(
      `${this.endpoint}/${measurementId}/status`
    );
    return response.json();
  }
  
  async waitForCompletion(measurementId, pollInterval = 2000) {
    while (true) {
      const status = await this.getStatus(measurementId);
      
      if (["completed", "stopped", "failed"].includes(status.status)) {
        return status;
      }
      
      console.log(`Running... ${status.duration_so_far.toFixed(1)}s elapsed`);
      await new Promise(r => setTimeout(r, pollInterval));
    }
  }
}

// Usage
const client = new MaaSClient();
const resp = await client.startCountRate(60, "detector_1");
const result = await client.waitForCompletion(resp.measurement_id);
console.log("Final results:", result.results);
```

---

## Troubleshooting

### "Connection refused" Error

```
Problem: Can't connect to MaaS
Solution: 
  1. Ensure server is running: python -m uvicorn main:app
  2. Check correct URL: http://localhost:8000
  3. Check firewall: Port 8000 should be open
```

### "Health check shows Redis unhealthy"

```
Problem: Redis component showing unhealthy
Solution:
  1. Start Redis: redis-server
  2. Check Redis is running: redis-cli ping (should return PONG)
  3. Check Redis host/port in code
```

### "Measurement returns HTTP 422"

```
Problem: Missing or invalid fields
Solution:
  1. Read error message carefully
  2. Check required fields are present
  3. Verify field types (list vs string, etc.)
  4. Check visit http://localhost:8000/docs for examples
```

### "Measurement times out or doesn't complete"

```
Problem: Measurement seems stuck
Solution:
  1. Check system has enough resources
  2. Try stopping (DELETE) and restarting
  3. Check backend worker is running
  4. Check logs for errors
```

### "Can't find saved file"

```
Problem: Save-raw-tags didn't save file where expected
Solution:
  1. Use absolute path in target_file_path
  2. Ensure path exists and is writable
  3. Check file permissions
  4. Try with simpler path first (e.g., C:\\output.dat)
```

---

## FAQ

**Q: How long can a measurement run?**
A: Up to 3600 seconds (1 hour). Longer times are not recommended. Contact support for special cases.

**Q: Can I run multiple measurements at once?**
A: Yes! That's a key feature. Start as many as you need, they run concurrently.

**Q: What happens if I stop the web server?**
A: Active measurements will be interrupted. Status will remain in Redis for 1 hour. Restart the web server and query the status to see what happened.

**Q: Can I customize the metadata fields?**
A: Yes! You can add any fields to the metadata dict. The system doesn't restrict custom fields.

**Q: How often should I poll for status?**
A: Every 1-5 seconds is reasonable. More frequent polling won't make results available faster.

**Q: Can I see historical measurements?**
A: Status is stored in Redis for 1 hour, then auto-deleted. For longer retention, save results to your own database.

**Q: What's the maximum number of concurrent measurements?**
A: System-dependent, but typically 100+ concurrent measurements are supported.

**Q: Can I run measurements without querying status?**
A: Yes, but you won't know when they complete. Always query status to know the results.

---

## Getting Help

1. **Documentation**: Check README files in the project
2. **API Docs**: Visit `http://localhost:8000/docs` 
3. **Error Messages**: Read HTTP error responses carefully
4. **Logs**: Check server logs for detailed error messages
5. **Health Check**: Run `curl http://localhost:8000/health` to verify system

---

## Next Steps

- Try the quick start measurements
- Integrate MaaS into your application
- Read README_DEVELOPER_GUIDE.md for debugging
- Contact your administrator for production setup
