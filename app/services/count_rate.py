"""Count-rate measurement handler implementation."""

import asyncio
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import CountRateMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging
from Swabian import TimeTagger

logger = configure_logging(__name__)


class CountRateMeasurementHandler(MeasurementHandler):
    """Handler for count-rate measurements."""

    def __init__(self, tagger=None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._count = 0
        self._start_time: Optional[datetime] = None
        logger.debug("CountRateMeasurementHandler initialized")

    async def start(self, duration_seconds: float, metadata: CountRateMetadata) -> None:
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

        # Extract parameters from metadata
        channels = metadata.channels
        binwidth = metadata.binwidth
        n_values = metadata.n_values
        target_location = metadata.target_location
        logger.debug(
            f"Count-rate params - channels: {channels}, binwidth: {binwidth}, n_values: {n_values}, target: {target_location}"
        )
        
        self.tagger.setTestSignal(1, True)
        self.tagger.setTestSignal(2, True)

        # Start the counting task
        counter = TimeTagger.Counter(
            tagger=self.tagger, channels=channels, binwidth=binwidth, n_values=n_values
        )
        counter.startFor(duration_seconds * 1e12)
        counter.waitUntilFinished()
        counter_data = counter.getData()
        logger.info(f"Count-rate measurement completed with raw data: {counter_data}")
        data = np.array(counter_data)
        logger.info(
            f"Count-rate measurement finished for duration: {duration_seconds} seconds"
        )
        logger.info(f"Data acquired: {data}")
        np.savetxt(target_location, data, delimiter=",")
        logger.info(f"Count-rate data saved to {target_location}")

    async def stop(self) -> Dict[str, Any]:
        """
        Stop count-rate measurement and return results.

        Returns:
            Dictionary with measurement results
        """
        logger.info("Stopping count-rate measurement")

        if self._measurement_task and not self._measurement_task.done():
            self._measurement_task.cancel()
            try:
                await self._measurement_task
            except asyncio.CancelledError:
                pass

        if self._start_time is None:
            logger.warning("Measurement was never started")
            return {"error": "Measurement was never started"}

        duration = (datetime.utcnow() - self._start_time).total_seconds()
        count_rate = self._count / duration if duration > 0 else 0

        results = {
            "total_count": self._count,
            "duration_seconds": duration,
            "count_rate_cps": count_rate,  # counts per second
            "stopped_at": datetime.utcnow().isoformat(),
        }

        logger.info(
            f"Count-rate measurement stopped - "
            f"total_count={self._count}, count_rate={count_rate:.2f} cps"
        )

        return results
