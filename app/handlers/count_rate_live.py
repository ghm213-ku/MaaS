"""Count-rate live measurement handler implementation."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
from Swabian import TimeTagger

from app.handlers.base import MeasurementHandler
from app.handlers.counter_utils import counter_summary, wait_until_finished
from app.models import CountRateMetadata

logger = logging.getLogger(__name__)


class CountRateLiveMeasurementHandler(MeasurementHandler):
    """Handler for live count-rate measurements streaming to Redis."""

    def __init__(self, tagger=None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._count = 0
        self._start_time: Optional[datetime] = None
        self._counter: Optional[Any] = None
        self._target_location: Optional[str] = None
        self._binwidth: int = 0
        self._summary: Dict[str, Any] = {}
        logger.debug("CountRateLiveMeasurementHandler initialized")

    def _publish(self, final: bool = False) -> None:
        """Read the counter and publish one update to Redis.

        ``final`` marks the last update of a timed (startFor) acquisition: the
        counter has finished and the data covers exactly n_values bins.
        """
        if self._counter is None or not (getattr(self, "redis_client", None) and hasattr(self, "status_id")):
            return
        data = self._counter.getData()
        self.redis_client.publish(
            f"measurement:data:{self.status_id}",
            json.dumps({
                "type": "count_rate",
                "status_id": self.status_id,
                "data": np.array(data).tolist(),
                "final": final,
                "timestamp": datetime.utcnow().isoformat(),
            }),
        )

    async def start(
        self, duration_seconds: Optional[float], metadata: CountRateMetadata
    ) -> None:
        """
        Start count-rate measurement.

        Args:
            duration_seconds: Auto-stop duration in seconds
            metadata: Measurement metadata containing:
                - channels: List of channel numbers to measure (required)
                - binwidth: Bin width in picoseconds (default: 1e9)
                - n_values: Number of bins (default: 1)
                - target_location: Target file path (default: ~/Desktop/MaasData/{datetime}/{measurement-type})
        """
        logger.info("Starting count-rate measurement")
        self._start_time = datetime.utcnow()
        self._count = 0

        # Extract parameters from metadata
        channels = metadata.channels
        binwidth = metadata.binwidth
        n_values = metadata.n_values
        target_location = metadata.target_location
        refresh_rate = metadata.refresh_rate
        self._target_location = target_location
        self._binwidth = binwidth
        logger.debug(
            f"Count-rate params - channels: {channels}, binwidth: {binwidth}, n_values: {n_values}, target: {target_location}, refresh_rate: {refresh_rate}"
        )

        self._measurement_task = asyncio.current_task()

        # Start the counting task
        counter = TimeTagger.Counter(
            tagger=self.tagger, channels=channels, binwidth=binwidth, n_values=n_values
        )
        self._counter = counter
        if duration_seconds is not None:
            counter.startFor(int(duration_seconds * 1e12))

        try:
            await self._stream_live_data(duration_seconds, refresh_rate, self._publish)

            # If the measurement was stopped, discard any data
            if self._stopped:
                logger.info("Count-rate measurement was stopped")
                if self._counter is not None:
                    try:
                        self._counter.stop()
                    except Exception as e:
                        logger.error(f"Failed to stop count-rate measurement: {e}")
                return

            if self._counter and duration_seconds is not None:
                # Timed acquisition: let startFor finish, then publish the
                # complete buffer once so clients get every bin.
                await wait_until_finished(self._counter)
                try:
                    self._publish(final=True)
                except Exception as e:
                    logger.warning(f"Failed to publish final count-rate data: {e}")

            if self._counter:
                self._summary = counter_summary(self._counter, self._binwidth)
                self._count = self._summary["count"]
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

        # Read the totals before stopping
        if self._counter is not None:
            try:
                self._summary = counter_summary(self._counter, self._binwidth)
                self._count = self._summary["count"]
            except Exception as e:
                logger.warning(f"Failed to read count-rate totals: {e}")

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

        results = {
            "status": "stopped",
            "total_count": self._count,
            "duration_seconds": duration,
            "counts_per_channel": self._summary.get("counts_per_channel", []),
            "integration_time_seconds": self._summary.get("integration_time_seconds", 0.0),
            "count_rate_cps_per_channel": self._summary.get("count_rate_cps_per_channel", []),
            "count_rate_cps": float(self._summary.get("count_rate_cps", 0.0)),
            "stopped_at": datetime.utcnow().isoformat(),
            "message": "Live count-rate measurement stopped",
        }

        logger.info(
            f"Live count-rate measurement stopped after {duration:.2f}s"
        )

        return results

