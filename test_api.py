#!/usr/bin/env python
"""Test the API to create a measurement and check its status."""

import urllib.request
import json
import time

# Create a measurement
request_data = {
    "measurement_type": "count_rate",
    "duration_seconds": 30,
    "metadata": {
        "channels": [1, 2, 3],
        "binwidth": 1e9,
        "n_values": 1,
        "target_location": "C:\\test",
    },
}

body = json.dumps(request_data).encode("utf-8")
req = urllib.request.Request(
    "http://localhost:8000/api/v1/measurements/count-rate",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(req) as response:
    result = json.loads(response.read())
    print("✓ POST /measurements/count-rate: 201 Created")
    print(json.dumps(result, indent=2))

measurement_id = result["measurement_id"]
print(f"\nCreated measurement: {measurement_id}")

# Check status
time.sleep(1)

req = urllib.request.Request(
    f"http://localhost:8000/api/v1/measurements/{measurement_id}/status", method="GET"
)
with urllib.request.urlopen(req) as response:
    status_result = json.loads(response.read())
    print(f"\n✓ GET /measurements/{measurement_id}/status: 200 OK")
    print(json.dumps(status_result, indent=2))
