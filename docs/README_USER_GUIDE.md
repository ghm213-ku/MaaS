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
    "measurement_type": "count_rate",
    "duration_seconds": 10,
    "metadata": {
      "channels": [1, 2, 3],
      "binwidth": 1000000000,
      "n_values": 1,
      "target_location": "desktop/MaasData/{datetime}/{measurement-type}"
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
  "message": "Count-rate measurement queued with channels [1, 2, 3]. Use ID '550e8400-e29b-41d4-a716-446655440000' to query status or stop."
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

Counts detector events over a period of time using specified channels.

**Endpoint**: `POST /api/v1/measurements/count-rate`

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 60,
    "metadata": {
      "channels": [1, 2, 3],
      "binwidth": 1000000000,
      "n_values": 1,
      "target_location": "desktop/MaasData/{datetime}/{measurement-type}"
    }
  }'
```

**Request Fields**:
- `channels` (required): List of channel numbers to measure (e.g., `[1, 2, 3]`)
- `binwidth` (optional): Bin width in picoseconds. Default: `1000000000` (1 second)
- `n_values` (optional): Number of bins in histogram. Default: `1`
- `target_location` (optional): Target file path for results. Supports `{datetime}` and `{measurement-type}` placeholders. Default: `"desktop/MaasData/{datetime}/{measurement-type}"`
- `duration_seconds` (optional): Auto-stop after N seconds. If omitted, runs until manually stopped.

**Results**: 
- `total_count`: Total number of events detected
- `count_rate_cps`: Count rate in counts per second
- `duration_seconds`: Measurement duration
- `stopped_at`: ISO timestamp of when measurement stopped

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

### 3. Coincidences Measurement

Measures coincidence events across multiple channel groups within a specified coincidence window using Swabian Instruments TimeTagger virtual coincidence channels.

The coincidence API model supports taking **multiple coincidences as a list of lists of channel numbers** (e.g., `[[1, 2], [2, 3, 5]]`). Under the hood, this integrates directly with Swabian's `Coincidences` virtual channel class to generate dedicated virtual channels for each coincidence group with maximum performance.

**Endpoints**:
- Standard: `POST /api/v1/measurements/coincidences` (alias: `POST /api/v1/measurements/coincidence`)
- Live Streaming: `POST /api/v1/measurements/coincidences-live` (alias: `POST /api/v1/measurements/coincidence-live`)

**Request**:
```bash
curl -X POST http://localhost:8000/api/v1/measurements/coincidences \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 60,
    "metadata": {
      "user_name": "user-123",
      "coincidences": [[1, 2], [2, 3, 5]],
      "coincidence_window": 1000,
      "timestamp": "Last",
      "binwidth": 1000000000,
      "n_values": 1,
      "target_location": "desktop/MaasData/{datetime}/{measurement-type}"
    }
  }'
```

**Metadata Fields**:
- `coincidences` (required if `channels` not provided): List of lists of channel numbers representing each coincidence group. E.g., `[[1, 2]]` for a single coincidence or `[[1, 2], [2, 3, 5]]` for multiple coincidences. Simple 1D lists are deprecated and rejected.
- `channels` (optional): List of lists of channel numbers (e.g. `[[1, 2]]` or `[[1, 2], [2, 3]]`). *Note: The old method of simple 1D channel lists (e.g. `[1, 2]`) is deprecated and no longer supported.*
- `coincidence_groups` (optional): Alias for `coincidences` matching Swabian parameter naming (`list[list[int]]`).
- `user_name` (required): The user ID who booked all required channels.
- `coincidence_window` / `coincidenceWindow` (optional): Maximum time window between events for a coincidence in picoseconds. Default: `1000` (1 ns).
- `timestamp` (optional): Timestamp mode for coincidence virtual channel (`"Last"`, `"First"`, `"ListedFirst"`, `"Average"`). Default: `"Last"`.
- `binwidth` (optional): Histogram bin width in picoseconds. Default: `1000000000` (1 second).
- `n_values` (optional): Number of histogram bins. Default: `1`.
- `target_location` (optional): Target file path. Supports `{datetime}` and `{measurement-type}` placeholders.
- `refresh_rate` (optional): Streaming update frequency in Hz for live coincidence measurements. Default: `25`.

**Results**:
- `status`: `"completed"` or `"stopped"`
- `duration`: Measurement duration in seconds
- `count`: Total coincidence counts detected across channels

---

### 4. Live Time Histograms

Streams StartStop, Histogram, or Correlation measurements in real-time to a Redis channel `measurement:data:{measurement_id}`.

**Endpoints**:
- `POST /api/v1/measurements/startstop-live`
- `POST /api/v1/measurements/histogram-live`
- `POST /api/v1/measurements/correlation-live`

**Request** (Example for Histogram-Live):
```bash
curl -X POST http://localhost:8000/api/v1/measurements/histogram-live \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 60,
    "metadata": {
      "click_channel": 1,
      "start_channel": 2,
      "user_name": "user-123",
      "binwidth": 1000,
      "n_bins": 1000,
      "refresh_rate": 25
    }
  }'
```
*(Note: Use `channel1` and `channel2` for `correlation-live` instead of `click_channel` and `start_channel`)*

**Live Streaming**: Connect to a local WebSocket (if applicable) or subscribe directly to Redis pub/sub to receive updates at the specified `refresh_rate` (default 25 Hz).
Each payload contains `{"data": [...], "index": [...]}`.

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
        "metadata": {
            "channels": [1, 2, 3],
            "binwidth": 1000000000,
            "n_values": 1,
            "target_location": "desktop/MaasData/{datetime}/{measurement-type}"
        }
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
        metadata: {
          channels: [1 + i, 2 + i, 3 + i],
          binwidth: 1000000000,
          n_values: 1,
          target_location: "desktop/MaasData/{datetime}/{measurement-type}"
        }
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

## Channel Management

MaaS includes an integrated **channel booking system** for managing exclusive channel resources.

### What are Channels?

- **48 Total Channels**: Numbered 1-16, 101-116, and 201-216
- **Exclusive Access**: Only one measurement can use a channel at a time
- **Automatic Management**: Channels are booked/released automatically with measurements
- **Manual Control**: Optional manual booking for advanced scenarios

### Channel API Endpoints

All channel operations are at `/api/v1/channels/` (separate from measurements):

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/channels/` | GET | List all channels with status |
| `/api/v1/channels/available` | GET | List available channels and statistics |
| `/api/v1/channels/book` | POST | Manually book channels |
| `/api/v1/channels/release/{id}` | POST | Manually release channels |

### Automatic Channel Booking (Save-Raw-Tags)

Channels are **required** for save-raw-tags measurements and are automatically booked:

```bash
curl -X POST http://localhost:8000/api/v1/measurements/save-raw-tags \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 60,
    "metadata": {
      "channel_list": [1, 2, 3],
      "target_file_path": "C:\\data\\output.dat"
    }
  }'
```

**Response** (channels automatically booked):
```json
{
  "measurement_id": "abc-123",
  "status": "queued",
  "message": "Save-raw-tags measurement queued with channels [1, 2, 3]. Booked channels: [1, 2, 3]"
}
```

When the measurement **completes, stops, or fails**, channels are **automatically released**.

### Count-Rate with Custom Target Location

For count-rate measurements, you can customize where results are saved:

```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 60,
    "metadata": {
      "channels": [1, 2, 3],
      "binwidth": 1000000000,
      "n_values": 10,
      "target_location": "C:\\custom\\path\\my_measurement_{datetime}.csv"
    }
  }'
```

The `target_location` field supports these placeholders:
- `{datetime}`: Replaced with current timestamp (e.g., `2026-05-22_14-30-45`)
- `{measurement-type}`: Replaced with measurement type (e.g., `count_rate`)

### Check Available Channels

```bash
curl http://localhost:8000/api/v1/channels/available
```

**Response**:
```json
{
  "total_channels": 48,
  "available_channels": 45,
  "booked_channels": 3,
  "utilization_percent": 6.25,
  "available_channel_numbers": [1, 2, 3, 4, 5, ...],
  "booked_by_identifier": {
    "measurement-001": [10, 11, 12]
  }
}
```

### List All Channels with Status

```bash
curl http://localhost:8000/api/v1/channels/
```

**Response**:
```json
{
  "channels": [
    {
      "channel": 1,
      "status": "available",
      "booked_by": null
    },
    {
      "channel": 2,
      "status": "booked",
      "booked_by": "measurement-001"
    },
    ...
  ],
  "total_channels": 48,
  "available_channels": 46,
  "booked_channels": 2
}
```

### Manual Channel Management

For advanced scenarios, you can manually book/release channels:

**Book Channels**:
```bash
curl -X POST http://localhost:8000/api/v1/channels/book \
  -H "Content-Type: application/json" \
  -d '{
    "booked_by": "my-user-id",
    "channel_numbers": [5, 6, 7]
  }'
```

**Release Channels**:
```bash
curl -X POST http://localhost:8000/api/v1/channels/release/my-user-id
```

### Channel Booking Errors

If channels are unavailable:

```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "duration_seconds": 60,
    "metadata": {
      "detector_id": "det_001",
      "channel_list": [1, 2, 999]
    }
  }'
```

**Response** (HTTP 400):
```json
{
  "detail": "Invalid channel number: 999"
}
```

If channels are already booked:

**Response** (HTTP 409):
```json
{
  "detail": "Channels already booked: [1, 2]"
}
```

### Channel Management Best Practices

✅ **DO**:
- Check available channels before booking
- Use descriptive identifiers for booked_by (e.g., measurement ID)
- Release channels when done with measurements
- Monitor channel utilization

❌ **DON'T**:
- Book channels you don't need
- Forget about manually-booked channels
- Assume all channels are always available
- Book invalid channel numbers (must be 1-16, 101-116, or 201-216)

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
- Read [README_DEVELOPER_GUIDE.md](README_DEVELOPER_GUIDE.md) for debugging
- Contact your administrator for production setup
