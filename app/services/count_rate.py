"""Count-rate measurement handler implementation."""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
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

    async def start(
        self, duration_seconds: Optional[int], metadata: Optional[Dict[str, Any]]
    ) -> None:
        """
        Start count-rate measurement.

        Args:
            duration_seconds: Auto-stop duration (managed by Measurement, not used here)
            metadata: Measurement metadata containing:
                - channels: List of channel numbers to measure
                - binwidth: Bin width in picoseconds (default: 1e9)
                - n_values: Number of bins (default: 1)
                - target_location: Target file path (default: desktop/MaasData/{datetime}/{measurement-type})
        """
        logger.info("Starting count-rate measurement")
        self._start_time = datetime.utcnow()
        self._count = 0

        # Extract parameters from metadata
        if metadata:
            channels = metadata.get("channels", [])
            binwidth = metadata.get("binwidth", int(1e9))
            n_values = metadata.get("n_values", 1)
            target_location = metadata.get(
                "target_location", "desktop/MaasData/{datetime}/{measurement-type}"
            )
            logger.debug(
                f"Count-rate params - channels: {channels}, binwidth: {binwidth}, n_values: {n_values}, target: {target_location}"
            )

        # Start the counting task
        self._measurement_task = asyncio.create_task(self._count_rate_loop())
        logger.info("Count-rate measurement loop started")

    async def _count_rate_loop(self) -> None:
        """
        Simulate count-rate measurement loop.
        This is a placeholder - replace with actual count-rate measurement logic.
        """
        try:
            while True:
                # Simulate counting events
                # Replace this with actual count-rate measurement implementation
                self._count += 1
                logger.debug(f"Count-rate update: {self._count} counts")

                # Simulate a measurement interval (e.g., every 100ms)
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.debug("Count-rate measurement loop cancelled")
            raise

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
