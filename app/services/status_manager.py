"""Status management service for distributed measurement system."""
import json
from datetime import datetime
from typing import Optional, Dict, Any
from enum import Enum
import redis
from app.utils.logger import configure_logging

logger = configure_logging(__name__)


class MeasurementStatus(str, Enum):
    """Status states for measurements."""
    QUEUED = "queued"
    ACTIVE = "active"
    COMPLETED = "completed"
    STOPPED = "stopped"
    FAILED = "failed"


class StatusManager:
    """Manages measurement status in Redis."""
    
    def __init__(self, redis_host: str = "localhost", redis_port: int = 6379, redis_db: int = 0):
        """Initialize Redis connection."""
        self.redis_client = redis.Redis(
            host=redis_host,
            port=redis_port,
            db=redis_db,
            decode_responses=True
        )
        self.status_prefix = "measurement:status:"
        self.metadata_prefix = "measurement:metadata:"
        self.results_prefix = "measurement:results:"
        
        logger.info(f"StatusManager initialized - Redis {redis_host}:{redis_port}")
    
    def create_status(
        self,
        status_id: str,
        measurement_type: str,
        duration_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Create a new measurement status in Redis."""
        status_data = {
            "status_id": status_id,
            "measurement_type": measurement_type,
            "status": MeasurementStatus.QUEUED.value,
            "started_at": datetime.utcnow().isoformat(),
            "duration_seconds": duration_seconds or 0,
            "message": "Measurement queued for processing",
        }
        
        # Store status
        status_key = f"{self.status_prefix}{status_id}"
        self.redis_client.set(status_key, json.dumps(status_data), ex=3600)  # 1 hour TTL
        
        # Store metadata separately
        if metadata:
            metadata_key = f"{self.metadata_prefix}{status_id}"
            self.redis_client.set(metadata_key, json.dumps(metadata), ex=3600)
        
        logger.info(f"[{status_id}] Status created: {MeasurementStatus.QUEUED.value}")
        return status_data
    
    def get_status(self, status_id: str) -> Optional[Dict[str, Any]]:
        """Get measurement status from Redis."""
        status_key = f"{self.status_prefix}{status_id}"
        status_data = self.redis_client.get(status_key)
        
        if not status_data:
            logger.warning(f"[{status_id}] Status not found")
            return None
        
        return json.loads(status_data)
    
    def update_status(
        self,
        status_id: str,
        status: str,
        message: str,
        results: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Update measurement status."""
        status_key = f"{self.status_prefix}{status_id}"
        status_data = self.redis_client.get(status_key)
        
        if not status_data:
            logger.error(f"[{status_id}] Cannot update non-existent status")
            raise ValueError(f"Status {status_id} not found")
        
        status_obj = json.loads(status_data)
        status_obj["status"] = status
        status_obj["message"] = message
        
        if status == MeasurementStatus.ACTIVE.value:
            status_obj["started_at"] = datetime.utcnow().isoformat()
        
        if status in [MeasurementStatus.COMPLETED.value, MeasurementStatus.STOPPED.value, MeasurementStatus.FAILED.value]:
            status_obj["completed_at"] = datetime.utcnow().isoformat()
        
        # Store updated status
        self.redis_client.set(status_key, json.dumps(status_obj), ex=3600)
        
        # Store results if provided
        if results:
            results_key = f"{self.results_prefix}{status_id}"
            self.redis_client.set(results_key, json.dumps(results), ex=3600)
            status_obj["results"] = results
        
        logger.info(f"[{status_id}] Status updated to: {status}")
        return status_obj
    
    def get_metadata(self, status_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a measurement."""
        metadata_key = f"{self.metadata_prefix}{status_id}"
        metadata = self.redis_client.get(metadata_key)
        
        if not metadata:
            return None
        
        return json.loads(metadata)
    
    def get_results(self, status_id: str) -> Optional[Dict[str, Any]]:
        """Get results for a measurement."""
        results_key = f"{self.results_prefix}{status_id}"
        results = self.redis_client.get(results_key)
        
        if not results:
            return None
        
        return json.loads(results)
    
    def delete_status(self, status_id: str) -> bool:
        """Delete status and associated data from Redis."""
        status_key = f"{self.status_prefix}{status_id}"
        metadata_key = f"{self.metadata_prefix}{status_id}"
        results_key = f"{self.results_prefix}{status_id}"
        
        deleted = 0
        deleted += self.redis_client.delete(status_key)
        deleted += self.redis_client.delete(metadata_key)
        deleted += self.redis_client.delete(results_key)
        
        logger.info(f"[{status_id}] Status deleted ({deleted} keys)")
        return deleted > 0
    
    def health_check(self) -> bool:
        """Check Redis connection health."""
        try:
            self.redis_client.ping()
            return True
        except Exception as e:
            logger.error(f"Redis health check failed: {e}")
            return False
