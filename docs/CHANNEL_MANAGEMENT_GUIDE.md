# Channel Management System Documentation

## Overview

A complete **channel booking and availability tracking system** has been implemented for the MaaS (Measurements as a Service) distributed architecture. This system enables exclusive access to 48 total channels across three ranges (1-16, 101-116, 201-216) with real-time persistence using Redis.

---

## Architecture

### Core Components

#### 1. **StatusManager Service** (`app/services/status_manager.py`)
Redis-backed service for managing both measurement status and channel availability.

**Key Features:**
- Manage measurement status and results
- Initialize all 48 channels as available on startup
- Book channels exclusively (only one measurement per channel)
- Release channels after measurement completion
- Track booking timestamps and measurement ownership
- Provide channel statistics and health checks

**Data Structures in Redis:**
```
measurement:status:{id}      - Status of measurements
measurement:metadata:{id}    - Measurement metadata
measurement:results:{id}     - Measurement results
channels:available           - Set of available channel numbers
channels:booked              - Hash mapping channel → measurement_id
channels:booking_time        - Hash mapping channel → booking_timestamp
```

#### 2. **Integration Points**

**Measurement Start (routes.py):**
- When starting a measurement, channels are booked automatically
- For `save_raw_tags`: channels from `channel_list` are booked
- For `count_rate`: channels from metadata `channel_list` (optional) are booked
- Returns HTTP 409 if any channel is already booked

**Measurement Completion (job_processor.py):**
- Channels are automatically released in the job thread's finally block
- Ensures channels are freed even if the job fails
- Works for normal completion, failures, and manual stops

**Measurement Stop (routes.py):**
- DELETE endpoint releases channels immediately
- Prevents orphaned channel bookings

---

## API Endpoints

### ✨ NEW: Dedicated Channel Routers at `/api/v1/channels/`

All channel management is now separated into dedicated routers:
- **Measurement endpoints**: `/api/v1/measurements/*`
- **Channel endpoints**: `/api/v1/channels/*`

### Channel Information Endpoints

#### 1. **GET /api/v1/channels/**
List all channels with their current status.

**Endpoint**: `GET /api/v1/channels/`

**Response (200):**
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
      "booked_by": "measurement-abc-123"
    }
  ],
  "total_channels": 48,
  "available_channels": 46,
  "booked_channels": 2
}
```

#### 2. **GET /api/v1/channels/available**
Get available channels and channel statistics.

**Endpoint**: `GET /api/v1/channels/available`

**Response (200):**
```json
{
  "total_channels": 48,
  "available_channels": 46,
  "booked_channels": 2,
  "utilization_percent": 4.17,
  "available_channel_numbers": [1, 3, 5, 6, 7, ...],
  "booked_by_identifier": {
    "measurement-id-1": [2, 101, 102],
    "measurement-id-2": [4]
  }
}
```

---

### Channel Booking/Release Endpoints

#### 3. **POST /api/v1/channels/book**
Book (reserve) channels for a measurement or user.

**Endpoint**: `POST /api/v1/channels/book`

**Request:**
```json
{
  "booked_by": "measurement-abc-123",
  "channel_numbers": [1, 2, 3]
}
```

**Response (201):**
```json
{
  "booked_by": "measurement-abc-123",
  "booked_channels": [1, 2, 3],
  "booking_time": "2026-05-14T10:30:45.123456",
  "total_booked": 3
}
```

**Error (400) - Invalid Channel:**
```json
{
  "detail": "Invalid channel number: 999"
}
```

**Error (409) - Channels Already Booked:**
```json
{
  "detail": "Channels already booked: [2, 3]"
}
```

#### 4. **POST /api/v1/channels/release/{booked_by}**
Release all channels booked by a measurement or user identifier.

**Endpoint**: `POST /api/v1/channels/release/{booked_by}`

**Response (200):**
```json
{
  "booked_by": "measurement-abc-123",
  "released_channels": [1, 2, 3],
  "total_released": 3
}
```

**Note**: If the identifier has no booked channels, returns with empty release:
```json
{
  "booked_by": "unknown-id",
  "released_channels": [],
  "total_released": 0
}
```

---

## Measurement Lifecycle with Channels

### Scenario 1: Save-Raw-Tags Measurement (Automatic Booking)

```
1. Client sends POST /api/v1/measurements/save-raw-tags
   {
     "measurement_type": "save_raw_tags",
     "duration_seconds": 60,
     "metadata": {
       "channel_list": [1, 2, 3],
       "target_file_path": "..."
     }
   }

2. System validates channels [1, 2, 3]
   - Must exist (1-16, 101-116, 201-216)
   - Must be available

3. System books channels for this measurement_id
   - channels:available: remove 1, 2, 3
   - channels:booked: 1→measurement_id, 2→measurement_id, 3→measurement_id
   - channels:booking_time: set timestamps

4. Response includes "Booked channels: [1, 2, 3]"
   ```json
   {
     "measurement_id": "abc-123",
     "status": "queued",
     "message": "Save-raw-tags measurement queued with channels [1, 2, 3]..."
   }
   ```

5. Job processes...

6. On completion/failure/stop:
   - Finally block automatically releases channels
   - Channels returned to available pool
   - Status updated to completed/failed/stopped
   - Any client can now book those channels
```

### Scenario 2: Count-Rate with Optional Channels

```
1. Client sends POST /api/v1/measurements/count-rate
   {
     "measurement_type": "count_rate",
     "duration_seconds": 60,
     "metadata": {
       "detector_id": "det_001",
       "channel_list": [101, 102]
     }
   }

2. Same flow as save-raw-tags (channels are optional here)

OR without channels:
   {
     "measurement_type": "count_rate",
     "duration_seconds": 60,
     "metadata": {
       "detector_id": "det_001"
     }
   }

   (No channel booking occurs)
```

### Scenario 3: Manual Stop

```
1. Client sends DELETE /api/v1/measurements/{measurement_id}

2. Measurement is marked as STOPPED

3. Channels are immediately released

4. Response confirms channels freed
```

---

## Data Persistence

### Redis Storage
All channel state is stored in Redis with the following characteristics:

- **No TTL on channel booking data** - Channels remain booked until explicitly released
- **Atomic operations** - Using Redis pipelines for transactional consistency
- **Persistence** - Redis persists data to disk (if configured)

### Data Recovery
Since channels are released immediately after job completion, there's minimal risk of orphaned bookings. However, if the application crashes during measurement:

1. Channels remain booked under the measurement_id
2. Channels can be manually released via: `POST /api/v1/channels/release/{measurement_id}`
3. Consider implementing a cleanup job for stale bookings (measurements in FAILED/STOPPED state for >1 hour)

---

## Exclusive Access Guarantee

**Why Channels are Exclusive:**
1. **Atomic Booking** - Redis ensures only one measurement can book a channel
2. **Validation Before Booking** - Check availability before attempting to book
3. **Error on Conflict** - HTTP 409 returned if any channel unavailable

**Concurrency Safety:**
- Redis pipelines ensure atomic multi-command operations
- No race conditions between check and book
- Multiple concurrent measurements can safely book different channels

---

## Error Handling

### Common HTTP Status Codes

| Status | Scenario | Handling |
|--------|----------|----------|
| 201 | Channels booked successfully | Measurement proceeds |
| 400 | Invalid channel numbers | User provides invalid channel range |
| 409 | Channel already booked | Retry with different channels or wait for release |
| 500 | Redis unavailable | System down, check Redis connectivity |

### Recovery Strategies

**If Channels Can't Be Booked:**
1. Check which channels are available: `GET /api/v1/channels/available`
2. Choose from `available_channel_numbers`
3. Retry with available channels

**If Channels Won't Release:**
1. Verify measurement is completed: `GET /api/v1/measurements/{measurement_id}/status`
2. Manually release if stuck: `POST /api/v1/channels/release/{measurement_id}`
3. Check Redis connectivity: `GET /api/v1/channels/available` (returns health status)

---

## Usage Examples

### Frontend Example: Get Available Channels

```javascript
// Show user available channels
const response = await fetch('/api/v1/channels/available');
const data = await response.json();

console.log(`Available channels: ${data.available_channel_numbers}`);
console.log(`Utilization: ${data.utilization_percent}%`);

// Display in dropdown
const selector = document.getElementById('channel-selector');
data.available_channel_numbers.forEach(ch => {
  const option = document.createElement('option');
  option.value = ch;
  option.text = `Channel ${ch}`;
  selector.add(option);
});
```

### Backend Example: Start Measurement with Channels

```python
# Python client
import httpx

async def start_measurement():
    async with httpx.AsyncClient() as client:
        response = await client.post(
            "http://localhost:8000/api/v1/measurements/save-raw-tags",
            json={
                "measurement_type": "save_raw_tags",
                "duration_seconds": 60,
                "metadata": {
                    "channel_list": [1, 2, 3],
                    "target_file_path": "/data/output"
                }
            }
        )
        
        if response.status_code == 201:
            data = response.json()
            print(f"Measurement started: {data['measurement_id']}")
            print(f"Booked channels: {data.get('booked_channels', [])}")
        elif response.status_code == 409:
            print(f"Error: {response.json()['detail']}")
```

---

## Configuration

### Channel Ranges
Located in `ChannelManager.ALL_CHANNELS`:
```python
ALL_CHANNELS = list(range(1, 17)) + list(range(101, 117)) + list(range(201, 217))
# Total: 48 channels
```

To modify ranges, edit `app/services/channel_manager.py` line 18.

### Redis Connection
Default configuration in `main.py`:
```python
channel_manager = ChannelManager(
    redis_host="localhost",
    redis_port=6379,
    redis_db=0,
)
```

Configure for production (environment variables, cluster, etc.)

---

## Testing

### Test Workflow

```bash
# 1. Check available channels
curl http://localhost:8000/api/v1/channels/available

# 2. Start measurement with channels (auto-books)
curl -X POST http://localhost:8000/api/v1/measurements/save-raw-tags \
  -H "Content-Type: application/json" \
  -d '{
    "measurement_type": "save_raw_tags",
    "duration_seconds": 60,
    "metadata": {
      "channel_list": [1, 2, 3],
      "target_file_path": "/tmp/data"
    }
  }'

# 3. Verify channels are booked
curl http://localhost:8000/api/v1/channels/available

# 4. Stop measurement (releases channels)
curl -X DELETE http://localhost:8000/api/v1/measurements/{measurement_id}

# 5. Verify channels are released
curl http://localhost:8000/api/v1/channels/available
```

---

## Files Modified

| File | Changes |
|------|---------|
| `app/services/status_manager.py` | Added channel management methods and Redis keys |
| `app/models.py` | Added channel-related Pydantic models |
| `app/api/routes.py` | Added 5 channel endpoints, integrated channels into measurement endpoints |
| `app/services/job_processor.py` | Use StatusManager methods for channel release on completion |
| `main.py` | Initialize StatusManager (no separate ChannelManager needed) |

---

## Future Enhancements

1. **Stale Booking Cleanup** - Auto-release channels from failed measurements after timeout
2. **Channel Reservations** - Advance booking of channels for future measurements
3. **Channel Groups** - Book related channels as bundles
4. **Audit Trail** - Track all booking/release history
5. **Channel Priorities** - Allow some measurements higher priority for channel access
6. **Graceful Degradation** - Retry with fewer channels if some unavailable
7. **Webhooks** - Notify when channels become available

