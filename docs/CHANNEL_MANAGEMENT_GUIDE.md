# Channel Management Guide

MaaS shares one Time Tagger between several users. To keep users from measuring on each other's
inputs, every channel must be **booked** before it can be used in a measurement.

---

## Channels

There are **48 channels**: `1–16`, `101–116` and `201–216`.

- A channel is either `available` or `booked` by exactly one user.
- A measurement is accepted only if **every** channel it uses is booked under the `user_name` it
  sends (otherwise **403**).
- Booking and releasing are always **manual**. Channels stay booked after a measurement completes,
  stops or fails, and also across service restarts, until someone releases them.
- Releasing a channel resets its trigger level to **0.5 V** and its input delay to **0 ps**.

---

## Who may do what

All channel endpoints need a valid `Authorization: Bearer <token>`. The caller's username comes
from the token.

| Action | Normal user (operator / viewer) | Admin |
|--------|---------------------------------|-------|
| See channels | Yes | Yes |
| Book | Only under **their own** username | Only under **their own** username (no bypass) |
| Release | Only **their own** channels | Channels of **any** user (put the owner's username in the path) |

A request that breaks these rules gets **403** and changes nothing.

---

## Endpoints

### `GET /api/v1/channels/`

Every channel with its status. Booked channels also show `user_name` and `booking_time` (UTC).

```json
{
  "channels": [
    { "channel_number": 1, "status": "available" },
    { "channel_number": 2, "status": "booked", "user_name": "alice", "booking_time": "2026-11-10T10:30:45.123456" }
  ],
  "total_channels": 48,
  "available_channels": 47,
  "booked_channels": 1
}
```

### `GET /api/v1/channels/available`

Summary: free channel numbers and who holds which channels.

```json
{
  "total_channels": 48,
  "available_channels": 45,
  "booked_channels": 3,
  "utilization_percent": 6.25,
  "available_channel_numbers": [3, 4, 5, "..."],
  "user_names": { "alice": [1, 2], "bob": [101] }
}
```

### `GET /api/v1/channels/parameters`

Current trigger voltage (V) and input delay (ps) of every channel, as last reported by the worker.

### `POST /api/v1/channels/book`

```json
{ "user_name": "alice", "channel_numbers": [1, 2] }
```

`channels` is accepted instead of `channel_numbers`. Response **201**:

```json
{ "user_name": "alice", "booked_channels": [1, 2], "booking_time": "2026-11-10T10:30:45.123456", "total_booked": 2 }
```

Booking is all-or-nothing: if any listed channel is already booked (by anyone, including you),
nothing is booked.

### `POST /api/v1/channels/release/{user_name}`

```json
{ "channel_numbers": [1, 2] }
```

Every listed channel must be booked by `{user_name}`, otherwise nothing is released. Response:

```json
{
  "user_name": "alice",
  "released_channels": [1, 2],
  "total_released": 2,
  "parameter_reset_id": "7d0c..."
}
```

`parameter_reset_id` is the ID of the job that resets the released channels to 0.5 V / 0 ps.
Poll `GET /api/v1/measurements/{parameter_reset_id}/status` to see when it has run (it needs the
worker to be running).

---

## Errors

| HTTP | `detail` | What to do |
|------|----------|------------|
| 400 | `Invalid channel numbers: [999]. Valid channels: [...]` | Use channels 1–16, 101–116, 201–216 |
| 403 | `You can only book channels under your own username` | Set `user_name` to your own username |
| 403 | `You can only release your own channels` | Ask the owner or an admin to release it |
| 403 | `Channel 3 is not booked by user 'alice'` (when starting a measurement) | Book the channel first |
| 409 | `Cannot book channels [2] - already booked` | See who holds it with `GET /api/v1/channels/available`; pick another channel or ask them to release it |
| 409 | `Cannot release channels [5] - not booked by alice` | Check the channel list; only release channels the user actually holds |
| 422 | `Field required` | Release body missing or `channel_numbers` empty |

---

## Typical session

```bash
# 1. See what's free
curl http://localhost:8000/api/v1/channels/available -H "Authorization: Bearer $TOKEN"

# 2. Book
curl -X POST http://localhost:8000/api/v1/channels/book \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"user_name": "alice", "channel_numbers": [1, 2]}'

# 3. Run measurements on channels 1 and 2 (any number, one after another or in parallel)

# 4. Release
curl -X POST http://localhost:8000/api/v1/channels/release/alice \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"channel_numbers": [1, 2]}'
```

---

## Stale bookings

If someone forgets to release channels (or a client crashes), the channels stay booked. To free
them:

1. Find the owner in `GET /api/v1/channels/available` (`user_names`) or in
   `request_logs/channel_requests.txt`, which records every book and release.
2. The owner releases them, or an admin calls `POST /api/v1/channels/release/<owner>` with the
   channel numbers.

---

## How it is stored

Bookings live in Redis (no expiry):

| Key | Type | Content |
|-----|------|---------|
| `channels:available` | set | Free channel numbers |
| `channels:booked` | hash | channel → username |
| `channels:booking_time` | hash | channel → booking time (UTC, ISO) |

The channel list is defined in `StatusManager.ALL_CHANNELS` in
`app/services/status_manager.py`. Booking and release logic is in the same class; the HTTP
endpoints and permission checks are in `app/api/channels.py`.
