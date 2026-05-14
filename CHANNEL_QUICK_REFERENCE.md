# Channel Management System - Quick Reference

## What Was Implemented

A complete **Redis-backed channel booking system** with automatic lifecycle management for your MaaS distributed architecture.

### 🎯 Core Features

✅ **48 Exclusive Channels**: 1-16, 101-116, 201-216 (only one measurement per channel)
✅ **Automatic Booking**: Channels booked when measurements start
✅ **Automatic Release**: Channels freed when measurements complete, fail, or stop
✅ **Both Booked and Manual**: Auto-booking for save-raw-tags, optional for count-rate
✅ **Real-time Status**: Check availability, utilization, and booking details
✅ **Frontend & Backend Access**: Both can query via REST APIs
✅ **Redis Persistence**: State survives restarts

---

## API Endpoints

### ✨ NEW: Dedicated Channel API at `/api/v1/channels/`

All channel management endpoints are now under `/api/v1/channels/` for cleaner separation of concerns:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/channels/` | GET | List all channels with current status |
| `/api/v1/channels/available` | GET | List available channels and statistics |
| `/api/v1/channels/book` | POST | Book channels for a measurement or user |
| `/api/v1/channels/release/{booked_by}` | POST | Release channels booked by an identifier |

---

## Quick Start - API Usage

### Check Available Channels
```bash
curl http://localhost:8000/api/v1/channels/available
```

Response shows available channels, utilization, and who booked what.

Example Response:
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

### List All Channels With Status
```bash
curl http://localhost:8000/api/v1/channels/
```

Example Response:
```json
{
  "channels": [
    {"channel": 1, "status": "available", "booked_by": null},
    {"channel": 2, "status": "booked", "booked_by": "measurement-001"},
    ...
  ],
  "total_channels": 48,
  "available_channels": 46,
  "booked_channels": 2
}
```

### Start Measurement (Auto-Books Channels)

**Save Raw Tags** (required channels):
```bash
curl -X POST http://localhost:8000/api/v1/measurements/save-raw-tags \
  -H "Content-Type: application/json" \
  -d '{
    "measurement_type": "save_raw_tags",
    "duration_seconds": 60,
    "metadata": {
      "channel_list": [1, 2, 3],
      "target_file_path": "/data/output"
    }
  }'
```

**Count Rate** (optional channels):
```bash
curl -X POST http://localhost:8000/api/v1/measurements/count-rate \
  -H "Content-Type: application/json" \
  -d '{
    "measurement_type": "count_rate",
    "duration_seconds": 60,
    "metadata": {
      "detector_id": "det_001",
      "channel_list": [101, 102, 103]
    }
  }'
```

### Manual Channel Management (if needed)

**Book Channels Manually:**
```bash
curl -X POST http://localhost:8000/api/v1/channels/book \
  -H "Content-Type: application/json" \
  -d '{
    "booked_by": "my-user-id",
    "channel_numbers": [5, 6, 7]
  }'
```

Response:
```json
{
  "booked_by": "my-user-id",
  "booked_channels": [5, 6, 7],
  "booking_time": "2026-05-14T10:30:45.123456",
  "total_booked": 3
}
```

**Release Channels Manually:**
```bash
curl -X POST http://localhost:8000/api/v1/channels/release/my-user-id
```

Response:
```json
{
  "booked_by": "my-user-id",
  "released_channels": [5, 6, 7],
  "total_released": 3
}
```

---

## Channel Lifecycle

### Automatic Channel Management

1. **Measurement Starts** → Channels are automatically booked
2. **Measurement Runs** → Channels remain booked
3. **Measurement Completes/Stops/Fails** → Channels automatically released
4. **Channels Available** → Ready for next measurement

### Manual Channel Management

Use the `/api/v1/channels/book` and `/api/v1/channels/release/{booked_by}` endpoints for:
- Manual channel reservations outside of measurements
- Testing channel management
- Administrative channel release if needed

---

## Common Use Cases

### Get Current System Status
```bash
curl http://localhost:8000/api/v1/measurements/
```

Returns health status and available measurement/channel endpoints.

### Check if Specific Channels are Available
```bash
# List available channels
curl http://localhost:8000/api/v1/channels/available | jq '.available_channel_numbers'

# Check if specific channels [5,6,7] are in the list
curl http://localhost:8000/api/v1/channels/available | jq '.available_channel_numbers | contains([5,6,7])'
```

### Get All Channels Booked by a Measurement
```bash
curl http://localhost:8000/api/v1/channels/available | \
  jq '.booked_by_identifier["measurement-001"]'
```

### Monitor Channel Utilization Over Time
```bash
# Check utilization percentage
curl http://localhost:8000/api/v1/channels/available | jq '.utilization_percent'
```

---

## Architecture Overview

```
┌─────────────┐
│   Frontend  │ ←→ GET  /api/v1/channels/available
│   or Client │    GET  /api/v1/channels/
└─────────────┘    POST /api/v1/channels/book
                   POST /api/v1/channels/release/{booked_by}

┌──────────────────────────────────────────────────────────┐
│            FastAPI Web Layer                              │
│  ┌────────────────────────────────────────────────────┐  │
│  │ Channels Router: /api/v1/channels/*                │  │
│  │ Measurements Router: /api/v1/measurements/*        │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
                        ↓
                   Redis
             (Channel bookings & Status)
```

---

## Error Handling

### Invalid Channel Numbers
```json
{
  "detail": "Invalid channel number: 999"
}
// Status: 400 Bad Request
```

### Channels Already Booked
```json
{
  "detail": "Channels already booked: [5, 6]"
}
// Status: 409 Conflict
```

### Channel Booking Failed During Measurement
```json
{
  "detail": "Channel booking failed: Channels already booked: [10]"
}
// Status: 409 Conflict
```

---

## Testing Channel API

Run the comprehensive channel API tests:

```bash
pytest tests/test_channel_api.py -v
```

Test Coverage:
- ✅ List all channels
- ✅ List available channels
- ✅ Book channels (success, validation, conflicts)
- ✅ Release channels
- ✅ Integration workflows
- ✅ Concurrent bookings
- ✅ Channel statistics accuracy
- ✅ Edge cases and error handling
         ↓
┌──────────────────────────────────────────────┐
│        StatusManager Service (Redis)          │
│  • Measurement status management              │
│  • Channel booking/release operations         │
│  • Channel state tracking & validation        │
│  • Atomic Redis operations via pipelines      │
└──────────────────────────────────────────────┘
         ↓
┌──────────────────────────────────────────────┐
│         Redis Database                        │
│  • measurement:* (status, metadata, results)  │
│  • channels:available (Set)                   │
│  • channels:booked (Hash)                     │
│  • channels:booking_time (Hash)               │
└──────────────────────────────────────────────┘

┌──────────────────────────────────────────────┐
│      JobProcessor (Backend)                   │
│  • On job completion: Release channels       │
│  • On job stop: Release channels             │
│  • Finally block ensures cleanup             │
│  • Uses StatusManager methods                 │
└──────────────────────────────────────────────┘
```

---

## Channel Lifecycle Example

```
Frontend: POST /measurements/save-raw-tags with channel_list: [1, 2, 3]
                          ↓
Routes: Validate channels (all available?)
                          ↓
ChannelManager: Book [1, 2, 3] for measurement_id
                Redis: Add mapping 1→measurement_id, 2→measurement_id, etc.
                          ↓
Measurement: QUEUED → ACTIVE → COMPLETED
                          ↓
JobProcessor: Finally block runs
                ChannelManager: Release [1, 2, 3]
                Redis: Remove mappings, restore to available
                          ↓
Frontend: Query /channels/available → [1, 2, 3] back in pool
```

---

## Key Design Decisions

### Why Redis?
- **Already used** for StatusManager (consistency)
- **Atomic operations** via pipelines (race-condition safe)
- **Fast** for real-time queries
- **Persistent** (survives restarts)
- **Simple** key-value structure

### Why Automatic Release?
- **Prevents leaks** - channels always freed eventually
- **Simplifies frontend** - no manual cleanup needed
- **Handles failures** - even if measurement crashes, finally block runs
- **Scales well** - works with many concurrent measurements

### Why Exclusive?
- **Real constraint** - channels are physical/logical resources
- **Prevents conflicts** - no two measurements on same channel
- **Simple semantics** - easier for users to understand

### Why Optional for Count-Rate?
- **Flexibility** - not all count-rate measurements need channels
- **Simple bookkeeping** - no channels = no booking overhead
- **Save-raw-tags is stricter** - always needs channels (file output)

---

## Error Handling

### Channel Already Booked (409)
```json
{
  "detail": "Cannot book channels [2, 3] - already booked for measurement xyz"
}
```
**Solution**: Get available channels and retry with different ones.

### Invalid Channel Number (400)
```json
{
  "detail": "Invalid channel numbers: [999]. Valid channels: [1-16, 101-116, 201-216]"
}
```
**Solution**: Use only valid channel numbers.

### Redis Unavailable (500)
```json
{
  "detail": "Redis connection failed"
}
```
**Solution**: Check Redis is running and accessible.

---

## Configuration

### Channel Ranges
Edit `app/services/status_manager.py` line 24:
```python
ALL_CHANNELS = list(range(1, 17)) + list(range(101, 117)) + list(range(201, 217))
```

### Redis Connection
Edit `main.py` lines ~27-32:
```python
status_manager = StatusManager(
    redis_host="localhost",      # Change for remote Redis
    redis_port=6379,
    redis_db=0,
)
```

---

## Testing Checklist

- [ ] Start measurement with channels → Verify booked
- [ ] Query channels/available → Verify decreased
- [ ] Measurement completes → Verify channels released
- [ ] Query channels/available → Verify back in pool
- [ ] Try booking already-booked channel → Get 409 error
- [ ] Stop measurement manually → Verify channels released
- [ ] Start without channels (count-rate) → No booking occurs
- [ ] Query measurement's channels → Get correct list

---

## Files Created/Modified

**MODIFIED:**
- `app/services/status_manager.py` - Added channel management methods
- `app/models.py` - Added 6 Pydantic models for channels
- `app/api/routes.py` - Added 5 channel endpoints + integrated into measurement endpoints
- `app/services/job_processor.py` - Use StatusManager for channel release

**DOCUMENTATION:**
- `CHANNEL_MANAGEMENT_GUIDE.md` - Comprehensive guide
- `CHANNEL_QUICK_REFERENCE.md` - This file

---

## Next Steps (Optional Enhancements)

1. **Cleanup Job** - Remove stale bookings after timeout
2. **Channel Reservations** - Book for future measurements
3. **Channel Groups** - Book related channels together
4. **Audit Logging** - Track all booking/release history
5. **Webhook Notifications** - Alert when channels available
6. **Channel Priority** - High-priority measurements get channels first
7. **Graceful Degradation** - Retry with fewer channels if needed

---

## Support

For detailed documentation, see: `CHANNEL_MANAGEMENT_GUIDE.md`

API docs available at: `http://localhost:8000/docs` (Swagger UI)
