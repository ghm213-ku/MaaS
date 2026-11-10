import os
import json
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
from typing import Optional

# Ensure logs directory exists (overridable via MAAS_LOGS_DIR, e.g. for tests)
LOGS_DIR = os.environ.get("MAAS_LOGS_DIR") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "logs"
)
os.makedirs(LOGS_DIR, exist_ok=True)
AUDIT_LOG_FILE = os.path.join(LOGS_DIR, "audit.log")

class JSONFormatter(logging.Formatter):
    def format(self, record):
        # The record.msg will be the JSON dict we want to log
        if isinstance(record.msg, dict):
            return json.dumps(record.msg)
        return json.dumps({
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "level": record.levelname,
            "message": str(record.msg)
        })

# Configure logger
audit_logger = logging.getLogger("hardware_audit")
audit_logger.setLevel(logging.INFO)
# Avoid propagation to root logger if needed, but standard python logging is fine
audit_logger.propagate = False 

# Add rotating handler if not already added
if not audit_logger.handlers:
    # 50 MB = 50 * 1024 * 1024 = 52428800 bytes
    handler = RotatingFileHandler(
        AUDIT_LOG_FILE, 
        maxBytes=52428800, 
        backupCount=10
    )
    handler.setFormatter(JSONFormatter())
    audit_logger.addHandler(handler)

def audit_target(http_method: str, http_path: str) -> str:
    """Return the audit target id for a request.

    A stop (DELETE /api/v1/measurements/{id}) targets that measurement id;
    every other request targets "system".
    """
    if http_method == "DELETE" and "/measurements/" in http_path:
        return http_path.rstrip("/").split("/")[-1]
    return "system"


def log_audit_event(
    user_id: Optional[int], 
    role: Optional[str], 
    action: str, 
    target_hardware_id: str, 
    http_method: str, 
    http_path: str, 
    status: int, 
    message: str
):
    """
    Log a structured JSON audit event.
    """
    level = "INFO"
    if status >= 500:
        level = "ERROR"
    elif status >= 400:
        level = "WARN"
        
    event = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "level": level,
        "event_type": "hardware_audit",
        "user_id": user_id,
        "role": role,
        "action": action,
        "target_hardware_id": target_hardware_id,
        "http_method": http_method,
        "http_path": http_path,
        "status": status,
        "message": message
    }
    
    # Log it
    if level == "INFO":
        audit_logger.info(event)
    elif level == "WARN":
        audit_logger.warning(event)
    else:
        audit_logger.error(event)
