"""Correlation measurement handler implementation."""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from Swabian import TimeTagger
from app.models import CorrelationMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging
import numpy as np

logger = configure_logging(__name__)


class CorrelationMeasurementHandler(MeasurementHandler):
    """Handler for correlation measurements."""

    def __init__(self, tagger=None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self._counter: Optional[Any] = None
        self._target_location: Optional[str] = None
        logger.debug("CorrelationMeasurementHandler initialized")

    async def start(
        self, duration_seconds: float, metadata: CorrelationMetadata
    ) -> None:
        """
        Start correlation measurement.

        Args:
            duration_seconds: Auto-stop duration in seconds
            metadata: Measurement metadata containing:
                - channel1: First channel number (required)
                - channel2: Second channel number (required)
                - binwidth: Bin width in picoseconds (default: 1e3)
                - n_values: Number of bins (default: 1000)
                - target_location: Target file path (default: ~/Desktop/MaasData/{datetime}/{measurement-type})
        """
        logger.info("Starting correlation measurement")
        self._start_time = datetime.utcnow()
        self._stopped = False

        # Extract parameters from metadata
        channel1 = metadata.channel1
        channel2 = metadata.channel2
        binwidth = metadata.binwidth
        n_values = metadata.n_values
        target_location = metadata.target_location
        self._target_location = target_location
        logger.debug(
            f"Correlation params - channel1: {channel1}, channel2: {channel2}, "
            f"binwidth: {binwidth}, n_values: {n_values}, target: {target_location}"
        )

        self._measurement_task = asyncio.current_task()

        # Start the counting task
        counter = TimeTagger.Correlation(
            tagger=self.tagger,
            channel_1=channel1,
            channel_2=channel2,
            binwidth=binwidth,
            n_bins=n_values,
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
                logger.info("Correlation measurement was stopped; skipping data save")
                if self._counter is not None:
                    try:
                        self._counter.stop()
                    except Exception as e:
                        logger.error(f"Failed to stop correlation measurement: {e}")
                return

            if self._counter:
                counts = np.asarray(self._counter.getData()).ravel()
                # Correlation.getIndex() is the bin time in ps, centred on
                # zero delay (e.g. [-20, -10, 0, 10]); without it the counts
                # can't be placed on the time axis.
                index = np.asarray(self._counter.getIndex()).ravel()
                data = np.column_stack([index, counts])
                logger.info(
                    f"Correlation measurement finished for duration: {duration_seconds} seconds"
                )
                if self._target_location:
                    os.makedirs(os.path.dirname(os.path.abspath(self._target_location)), exist_ok=True)
                    np.savetxt(
                        self._target_location,
                        data,
                        delimiter=",",
                        header="time_ps,counts",
                        fmt="%d",
                    )
                    logger.info(f"Correlation data saved to {self._target_location}")
                return {
                    "status": "completed",
                    "duration": (datetime.utcnow() - self._start_time).total_seconds(),
                    "total_counts": int(counts.sum()),
                    "n_bins": int(counts.size),
                }
        except asyncio.CancelledError:
            logger.info("Correlation measurement cancelled")
            raise

    async def stop(self) -> Dict[str, Any]:
        """
        Stop the correlation measurement and return results.

        Returns:
            Dictionary with measurement results
        """
        logger.info("Stopping correlation measurement")
        self._stopped = True

        # Stop the underlying hardware correlation so the running measurement ends
        if self._counter is not None:
            try:
                self._counter.stop()
            except Exception as e:
                logger.error(f"Failed to stop correlation measurement: {e}")

        if self._stop_event:
            self._stop_event.set()

        # Delete any data file that was already written for this measurement
        self._delete_output_file(self._target_location)

        return {
            "status": "stopped",
            "duration": (
                (datetime.utcnow() - self._start_time).total_seconds()
                if self._start_time
                else 0
            ),
            "message": "Correlation measurement stopped and data file deleted",
        }
