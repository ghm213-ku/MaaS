"""Example client demonstrating how to use the MaaS service."""
import requests
import json
import time
from pathlib import Path

# Suppress SSL warnings for self-signed certificates
requests.packages.urllib3.disable_warnings()

BASE_URL = "https://localhost:8443"


def health_check():
    """Check if service is running."""
    try:
        response = requests.get(f"{BASE_URL}/health", verify=False, timeout=5)
        response.raise_for_status()
        print("✓ Service is healthy")
        print(f"  Response: {response.json()}\n")
        return True
    except Exception as e:
        print(f"✗ Health check failed: {e}\n")
        return False


def start_measurement(duration_seconds=None, metadata=None):
    """Start a new count-rate measurement."""
    payload = {
        "measurement_type": "count_rate",
    }
    if duration_seconds:
        payload["duration_seconds"] = duration_seconds
    if metadata:
        payload["metadata"] = metadata
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/v1/measurements/count-rate",
            json=payload,
            verify=False,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        measurement_id = data["measurement_id"]
        print(f"✓ Measurement started")
        print(f"  Measurement ID: {measurement_id}")
        print(f"  Status: {data['status']}")
        print(f"  Started at: {data['started_at']}\n")
        return measurement_id
    except Exception as e:
        print(f"✗ Failed to start measurement: {e}\n")
        return None


def get_status(measurement_id):
    """Get current status of a measurement."""
    try:
        response = requests.get(
            f"{BASE_URL}/api/v1/measurements/{measurement_id}/status",
            verify=False,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        print(f"✓ Measurement status retrieved")
        print(f"  Status: {data['status']}")
        print(f"  Duration: {data['duration_so_far']:.2f}s")
        if data['results']:
            print(f"  Results: {data['results']}\n")
        else:
            print()
        return data
    except Exception as e:
        print(f"✗ Failed to get status: {e}\n")
        return None


def stop_measurement(measurement_id):
    """Stop a running measurement."""
    try:
        response = requests.delete(
            f"{BASE_URL}/api/v1/measurements/{measurement_id}",
            verify=False,
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        print(f"✓ Measurement stopped")
        print(f"  Status: {data['status']}")
        print(f"  Message: {data['message']}\n")
        return data
    except Exception as e:
        print(f"✗ Failed to stop measurement: {e}\n")
        return None


def example_workflow():
    """Demonstrate a complete workflow."""
    print("=" * 80)
    print("MaaS Client Example - Complete Workflow")
    print("=" * 80)
    print()
    
    # 1. Health check
    print("1. Checking service health...")
    if not health_check():
        print("Please start the service with: python main.py\n")
        return
    
    # 2. Start a measurement with auto-stop after 10 seconds
    print("2. Starting a 10-second auto-stop measurement...")
    measurement_id = start_measurement(
        duration_seconds=10,
        metadata={"detector_id": "det_001", "location": "lab_B"},
    )
    if not measurement_id:
        return
    
    # 3. Check status periodically
    print("3. Monitoring measurement status...")
    for i in range(5):
        time.sleep(2)
        print(f"   [{i+1}] Checking status...")
        status_data = get_status(measurement_id)
        if status_data is None:
            return
    
    # 4. Manual stop (though auto-stop should trigger soon)
    print("4. Manually stopping measurement...")
    result = stop_measurement(measurement_id)
    if result:
        print("5. Workflow complete!\n")
    
    # 6. Try to query stopped measurement
    print("6. Trying to query a stopped measurement...")
    status_data = get_status(measurement_id)
    if status_data:
        print(f"   Final status: {status_data['status']}")
        print(f"   Results available: {status_data['results'] is not None}\n")


def example_multiple_concurrent():
    """Example of running multiple concurrent measurements."""
    print("=" * 80)
    print("MaaS Client Example - Multiple Concurrent Measurements")
    print("=" * 80)
    print()
    
    # Health check
    if not health_check():
        return
    
    # Start 3 measurements
    print("Starting 3 concurrent measurements...\n")
    measurement_ids = []
    for i in range(3):
        meas_id = start_measurement(
            duration_seconds=15,
            metadata={"measurement_num": i+1, "detector": f"det_{i:03d}"},
        )
        if meas_id:
            measurement_ids.append(meas_id)
    
    if not measurement_ids:
        return
    
    print(f"Started {len(measurement_ids)} measurements\n")
    
    # Check status of all measurements
    print("Checking status of all measurements...")
    for meas_id in measurement_ids:
        get_status(meas_id)
    
    # Wait a bit
    print("Waiting 5 seconds...")
    time.sleep(5)
    
    # Stop all measurements
    print("Stopping all measurements...\n")
    for meas_id in measurement_ids:
        stop_measurement(meas_id)
    
    print("All measurements stopped!\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "concurrent":
        example_multiple_concurrent()
    else:
        example_workflow()
    
    print("=" * 80)
    print("Examples complete. Check the logs for detailed information.")
    print("=" * 80)
