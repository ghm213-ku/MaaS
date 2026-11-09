"""Count-rate measurement handler implementation."""

import asyncio
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import CountRateMetadata
from app.services.measurement import MeasurementHandler
from app.services.counter_utils import counter_summary
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
        self._counter: Optional[Any] = None
        self._target_location: Optional[str] = None
        self._binwidth: int = 0
        self._summary: Dict[str, Any] = {}
        logger.debug("CountRateMeasurementHandler initialized")

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
                - target_location: Target file path (default: ~/Desktop/MaasData/{datetime}/{measurement-type})
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
        self._binwidth = binwidth
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
            import os
            self._stop_event = asyncio.Event()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=duration_seconds+1)
            except asyncio.TimeoutError:
                pass

            # If the measurement was stopped, discard any data instead of saving it
            if self._stopped:
                logger.info("Count-rate measurement was stopped; skipping data save")
                if self._counter is not None:
                    try:
                        self._counter.stop()
                    except Exception as e:
                        logger.error(f"Failed to stop count-rate measurement: {e}")
                return

            if self._counter:
                # The saved file holds the Counter's last n_values bins
                # (channels x n_values), as Counter.getData() returns them.
                # Totals come from getDataTotalCounts(), which covers the
                # whole measurement rather than only the buffered bins.
                data = np.array(self._counter.getData())
                self._summary = counter_summary(self._counter, self._binwidth)
                self._count = self._summary["count"]
                logger.info(
                    f"Count-rate measurement finished for duration: {duration_seconds} seconds"
                )
                if self._target_location:
                    os.makedirs(os.path.dirname(os.path.abspath(self._target_location)), exist_ok=True)
                    np.savetxt(self._target_location, data, delimiter=",")
                    logger.info(f"Count-rate data saved to {self._target_location}")
        except asyncio.CancelledError:
            logger.info("Count-rate measurement cancelled")
            raise

        return {
            "status": "completed",
            "duration": (
                (datetime.utcnow() - self._start_time).total_seconds()
                if self._start_time
                else duration_seconds
            ),
            **self._summary,
        }

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

        # Delete any data file that was already written for this measurement
        self._delete_output_file(self._target_location)

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
            "message": "Count-rate measurement stopped and data file deleted",
        }

        logger.info(
            f"Count-rate measurement stopped after {duration:.2f}s; data file deleted"
        )

        return results
