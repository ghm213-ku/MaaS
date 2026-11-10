"""Settings shared by the web API and the worker.

Each value can be overridden with the environment variable of the same name.
"""

import os

# Redis connection used for the job queue, measurement status, channel bookings
# and the live-data pub/sub channels.
REDIS_HOST = os.getenv("REDIS_HOST", "127.0.0.1")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
REDIS_DB = int(os.getenv("REDIS_DB", "0"))

# Web API listen address (used when running `python main.py`).
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))

# Stopping measurements. A stop request is stored in Redis; each running job
# checks for it every STOP_POLL_INTERVAL_SECONDS, so a stop can't be lost even
# if the pub/sub notification is missed. DELETE /measurements/{id} waits up to
# STOP_ACK_TIMEOUT_SECONDS for the worker to confirm that the job has ended.
STOP_POLL_INTERVAL_SECONDS = float(os.getenv("STOP_POLL_INTERVAL_SECONDS", "0.5"))
STOP_ACK_TIMEOUT_SECONDS = float(os.getenv("STOP_ACK_TIMEOUT_SECONDS", "3"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
