"""Count-rate live measurement handler implementation."""

import asyncio
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import CountRateMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging
from Swabian import TimeTagger

logger = configure_logging(__name__)


class CountRateLiveMeasurementHandler(MeasurementHandler):
    """Handler for live count-rate measurements streaming to Redis."""

    def __init__(self, tagger=None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._count = 0
        self._start_time: Optional[datetime] = None
        self._counter: Optional[Any] = None
        self._target_location: Optional[str] = None
        logger.debug("CountRateLiveMeasurementHandler initialized")

    async def start(
        self, duration_seconds: float, metadata: CountRateMetadata
    ) -> None:
        """
        Start count-rate measurement.

        Args:
            duration_seconds: Auto-stop duration in seconds
            metadata: Measurement metadata containing:
                - channels: List of channel numbers to measure (required)
                - binwidth: Bin width in picoseconds (default: 1e9)
                - n_values: Number of bins (default: 1)
                - target_location: Target file path (default: desktop/MaasData/{datetime}/{measurement-type})
        """
        logger.info("Starting count-rate measurement")
        self._start_time = datetime.utcnow()
        self._count = 0
        self._stopped = False

        # Extract parameters from metadata
        channels = metadata.channels
        binwidth = metadata.binwidth
        n_values = metadata.n_values
        target_location = metadata.target_location
        self._target_location = target_location
        logger.debug(
            f"Count-rate params - channels: {channels}, binwidth: {binwidth}, n_values: {n_values}, target: {target_location}"
        )
        
        self._measurement_task = asyncio.current_task()

        # Start the counting task
        counter = TimeTagger.Counter(
            tagger=self.tagger, channels=channels, binwidth=binwidth, n_values=n_values
        )
        self._counter = counter
        counter.startFor(duration_seconds * 1e12)

        try:
            import json
            self._stop_event = asyncio.Event()
            
            end_time = asyncio.get_event_loop().time() + duration_seconds
            
            # Loop every 0.04s for 25Hz update rate
            while not self._stopped and asyncio.get_event_loop().time() < end_time:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=0.04)
                    break  # if stop_event is set, break
                except asyncio.TimeoutError:
                    pass
                
                # Fetch data and push to redis
                if self._counter:
                    try:
                        data = self._counter.getData()
                        if hasattr(self, 'redis_client') and self.redis_client and hasattr(self, 'status_id'):
                            pub_channel = f"measurement:data:{self.status_id}"
                            payload = json.dumps({
                                "type": "count_rate",
                                "status_id": self.status_id,
                                "data": np.array(data).tolist(),
                                "timestamp": datetime.utcnow().isoformat()
                            })
                            self.redis_client.publish(pub_channel, payload)
                    except Exception as e:
                        logger.warning(f"Failed to fetch or publish count-rate data: {e}")

            # If the measurement was stopped, discard any data
            if self._stopped:
                logger.info("Count-rate measurement was stopped")
                if self._counter is not None:
                    try:
                        self._counter.stop()
                    except Exception as e:
                        logger.error(f"Failed to stop count-rate measurement: {e}")
                return

            if self._counter:
                counter_data = self._counter.getData()
                self._count = int(np.sum(counter_data))
                logger.info(
                    f"Count-rate measurement finished for duration: {duration_seconds} seconds"
                )
        except asyncio.CancelledError:
            logger.info("Count-rate measurement cancelled")
            raise

    async def stop(self) -> Dict[str, Any]:
        """
        Stop count-rate measurement and return results.

        Returns:
            Dictionary with measurement results
        """
        logger.info("Stopping count-rate measurement")
        self._stopped = True

        # Fetch partial data before aborting
        if self._counter is not None:
            try:
                data = self._counter.getData()
                self._count = int(np.sum(data))
            except Exception:
                pass

        # Stop the underlying hardware counter so the running measurement ends
        if self._counter is not None:
            try:
                self._counter.stop()
            except Exception as e:
                logger.error(f"Failed to stop count-rate counter: {e}")

        if self._stop_event:
            self._stop_event.set()

        if self._start_time is None:
            logger.warning("Measurement was never started")
            return {"error": "Measurement was never started"}

        duration = (datetime.utcnow() - self._start_time).total_seconds()
        count_rate = self._count / duration if duration > 0 else 0

        results = {
            "status": "stopped",
            "total_count": self._count,
            "duration_seconds": duration,
            "count_rate_cps": count_rate,
            "stopped_at": datetime.utcnow().isoformat(),
            "message": "Count-rate measurement stopped and data file deleted",
        }

        logger.info(
            f"Count-rate measurement stopped after {duration:.2f}s; data file deleted"
        )

        return results
