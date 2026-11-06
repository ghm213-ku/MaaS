"""Status management service for distributed measurement system."""

import json
from datetime import datetime
from typing import Optional, Dict, Any, List
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
    """Manages measurement status and channels in Redis."""

    # Define all available channels
    ALL_CHANNELS = list(range(1, 17)) + list(range(101, 117)) + list(range(201, 217))

    def __init__(
        self,
        redis_host: str = "127.0.0.1",
        redis_port: int = 6379,
        redis_db: int = 0,
        file_logger: Optional[Any] = None,
    ):
        """Initialize Redis connection.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            file_logger: Optional FileLogger instance for logging measurement status removal
        """
        self.redis_client = redis.Redis(
            host=redis_host, port=redis_port, db=redis_db, decode_responses=True
        )
        self.file_logger = file_logger
        self.status_prefix = "measurement:status:"
        self.metadata_prefix = "measurement:metadata:"
        self.results_prefix = "measurement:results:"

        # Channel management keys
        self.available_channels_key = "channels:available"
        self.booked_channels_key = "channels:booked"
        self.booking_time_key = "channels:booking_time"

        # Initialize channels if not already done
        self._initialize_channels()

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
        self.redis_client.set(
            status_key, json.dumps(status_data), ex=3600
        )  # 1 hour TTL

        # Store metadata separately
        if metadata:
            metadata_key = f"{self.metadata_prefix}{status_id}"
            self.redis_client.set(metadata_key, json.dumps(metadata), ex=3600)

        logger.info(f"[{status_id}] Status created: {MeasurementStatus.QUEUED.value}")

        # Log the initial status creation to file
        if self.file_logger:
            try:
                self.file_logger.log_measurement_status_update(
                    status_id=status_id,
                    status_data=status_data,
                    timestamp=datetime.utcnow(),
                )
            except Exception as e:
                logger.error(f"[{status_id}] Failed to log status creation: {e}")

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
        """Update measurement status and log the change.

        Status updates are logged to file on every change. The measurement
        remains in Redis until the TTL expires. Reaching a terminal status does
        not release booked channels or reset their parameters; that happens
        only via release_channels().
        """
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

        if status in [
            MeasurementStatus.COMPLETED.value,
            MeasurementStatus.STOPPED.value,
            MeasurementStatus.FAILED.value,
        ]:
            status_obj["completed_at"] = datetime.utcnow().isoformat()

        # Store updated status in Redis (keeps TTL)
        self.redis_client.set(status_key, json.dumps(status_obj), ex=3600)

        # Store results if provided
        if results:
            results_key = f"{self.results_prefix}{status_id}"
            self.redis_client.set(results_key, json.dumps(results), ex=3600)
            status_obj["results"] = results

        logger.info(f"[{status_id}] Status updated to: {status}")

        # Log the status update to file
        if self.file_logger:
            try:
                self.file_logger.log_measurement_status_update(
                    status_id=status_id,
                    status_data=status_obj,
                    timestamp=datetime.utcnow(),
                )
            except Exception as e:
                logger.error(f"[{status_id}] Failed to log status update: {e}")



        return status_obj

    def get_metadata(self, status_id: str) -> Optional[Dict[str, Any]]:
        """Get metadata for a measurement."""
        metadata_key = f"{self.metadata_prefix}{status_id}"
        metadata = self.redis_client.get(metadata_key)

        if not metadata:
            return None

        return json.loads(metadata)

    def get_results(self, status_id: str) -> Optional[Dict[str, Any]]:
        """Get results for a measurement.

        Returns None if results are not a valid dictionary (handles legacy string data).
        """
        results_key = f"{self.results_prefix}{status_id}"
        results = self.redis_client.get(results_key)

        if not results:
            return None

        try:
            parsed = json.loads(results)
            # Ensure it's a dictionary, not a string
            if isinstance(parsed, dict):
                return parsed
            else:
                logger.warning(
                    f"[{status_id}] Results stored as non-dict type, returning None"
                )
                return None
        except (json.JSONDecodeError, TypeError):
            logger.warning(
                f"[{status_id}] Could not parse results JSON, returning None"
            )
            return None

    def delete_status(self, status_id: str) -> bool:
        """Delete status and associated data from Redis.

        Logs the status to file before deletion if file_logger is available.
        """
        # Get the status data before deleting (for logging)
        status_key = f"{self.status_prefix}{status_id}"
        status_data = self.redis_client.get(status_key)

        # Log the status removal if file_logger is available
        if status_data and self.file_logger:
            try:
                status_obj = json.loads(status_data)
                self.file_logger.log_measurement_status_removal(
                    status_id=status_id,
                    status_data=status_obj,
                    timestamp=datetime.utcnow(),
                )
            except Exception as e:
                logger.error(f"[{status_id}] Failed to log status removal: {e}")

        # Now delete from Redis
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

    # ========== CHANNEL MANAGEMENT METHODS ==========

    def _initialize_channels(self) -> None:
        """Initialize all channels as available on first run."""
        if self.redis_client.exists(self.available_channels_key):
            logger.debug("Channels already initialized")
            return

        for channel in self.ALL_CHANNELS:
            self.redis_client.sadd(self.available_channels_key, str(channel))

        logger.info(
            f"Initialized {len(self.ALL_CHANNELS)} channels: {self.ALL_CHANNELS}"
        )

    def get_all_channels(self) -> List[Dict[str, Any]]:
        """Get all channels with their current status."""
        channels = []

        for channel in self.ALL_CHANNELS:
            channel_str = str(channel)
            is_available = self.redis_client.sismember(
                self.available_channels_key, channel_str
            )

            channel_info = {
                "channel_number": channel,
                "status": "available" if is_available else "booked",
            }

            if not is_available:
                booked_by = self.redis_client.hget(
                    self.booked_channels_key, channel_str
                )
                booking_time = self.redis_client.hget(
                    self.booking_time_key, channel_str
                )

                if booked_by:
                    channel_info["user_name"] = booked_by
                if booking_time:
                    channel_info["booking_time"] = booking_time

            channels.append(channel_info)

        return channels

    def get_available_channels(self) -> List[int]:
        """Get list of all available channel numbers."""
        available = self.redis_client.smembers(self.available_channels_key)
        return sorted([int(ch) for ch in available])

    def get_booked_channels(self) -> Dict[int, str]:
        """Get mapping of booked channels to their bookers (measurement_id or user)."""
        booked = self.redis_client.hgetall(self.booked_channels_key)
        return {int(ch): booker for ch, booker in booked.items()}

    def book_channels(
        self,
        channel_numbers: List[int],
        user_name: str,
    ) -> Dict[str, Any]:
        """Book channels for a measurement or user.

        Args:
            channel_numbers: List[int] to book
            user_name: Who is booking (user identifier)

        Returns:
            Dict with booking results

        Raises:
            ValueError: If any channels are already booked
        """
        unavailable = []
        for channel in channel_numbers:
            channel_str = str(channel)
            if not self.redis_client.sismember(
                self.available_channels_key, channel_str
            ):
                unavailable.append(channel)

        if unavailable:
            raise ValueError(
                f"Cannot book channels {unavailable} - already booked"
            )

        pipe = self.redis_client.pipeline()
        booking_time = datetime.utcnow().isoformat()

        for channel in channel_numbers:
            channel_str = str(channel)
            pipe.srem(self.available_channels_key, channel_str)
            pipe.hset(self.booked_channels_key, channel_str, user_name)
            pipe.hset(self.booking_time_key, channel_str, booking_time)

        pipe.execute()

        logger.info(f"[{user_name}] Booked channels: {channel_numbers}")

        return {
            "user_name": user_name,
            "booked_channels": channel_numbers,
            "booking_time": booking_time,
            "total_booked": len(channel_numbers),
        }

    def release_channels(self, user_name: str) -> Dict[str, Any]:
        """Release all channels booked by a user.

        Args:
            user_name: The identifier (user) whose channels to release

        Returns:
            Dict with released channels info
        """
        booked = self.redis_client.hgetall(self.booked_channels_key)
        channels_to_release = [
            int(ch) for ch, booker in booked.items() if booker == user_name
        ]

        if not channels_to_release:
            logger.info(f"[{user_name}] No channels to release")
            return {
                "user_name": user_name,
                "released_channels": [],
                "total_released": 0,
            }

        pipe = self.redis_client.pipeline()

        for channel in channels_to_release:
            channel_str = str(channel)
            pipe.sadd(self.available_channels_key, channel_str)
            pipe.hdel(self.booked_channels_key, channel_str)
            pipe.hdel(self.booking_time_key, channel_str)

        pipe.execute()

        logger.info(f"[{user_name}] Released channels: {channels_to_release}")

        return {
            "user_name": user_name,
            "released_channels": sorted(channels_to_release),
            "total_released": len(channels_to_release),
        }

    def get_booked_channels_by(self, user_name: str) -> List[int]:
        """Get all channels booked by a specific user."""
        booked = self.redis_client.hgetall(self.booked_channels_key)
        channels = [int(ch) for ch, booker in booked.items() if booker == user_name]
        return sorted(channels)

    def validate_channels(self, channel_numbers: List[int]) -> bool:
        """Validate that all channel numbers are valid.

        Raises:
            ValueError: If any channel number is invalid
        """
        invalid = [ch for ch in channel_numbers if ch not in self.ALL_CHANNELS]
        if invalid:
            raise ValueError(
                f"Invalid channel numbers: {invalid}. Valid channels: {self.ALL_CHANNELS}"
            )
        return True

    def get_channel_stats(self) -> Dict[str, Any]:
        """Get statistics about channel usage."""
        available = self.redis_client.scard(self.available_channels_key)
        booked = len(self.redis_client.hgetall(self.booked_channels_key))
        total = len(self.ALL_CHANNELS)

        return {
            "total_channels": total,
            "available_channels": available,
            "booked_channels": booked,
            "utilization_percent": round((booked / total) * 100, 2) if total > 0 else 0,
        }

    def close(self):
        """Close Redis connection gracefully."""
        try:
            if self.redis_client:
                self.redis_client.close()
                logger.info("Redis connection closed")
        except Exception as e:
            logger.error(f"Error closing Redis connection: {e}", exc_info=True)
