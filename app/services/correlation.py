"""Correlation measurement handler implementation."""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
import TimeTagger
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
                - binwidth: Bin width in picoseconds (default: 1e9)
                - n_values: Number of bins (default: 100)
                - target_location: Target file path (default: desktop/MaasData/{datetime}/{measurement-type})
        """
        logger.info("Starting correlation measurement")
        self._start_time = datetime.utcnow()

        # Extract parameters from metadata
        channel1 = metadata.channel1
        channel2 = metadata.channel2
        binwidth = metadata.binwidth
        n_values = metadata.n_values
        target_location = metadata.target_location
        logger.debug(
            f"Correlation params - channel1: {channel1}, channel2: {channel2}, "
            f"binwidth: {binwidth}, n_values: {n_values}, target: {target_location}"
        )

        self.tagger.setTestSignal(1, True)
        self.tagger.setTestSignal(2, True)

        # Start the counting task
        counter = TimeTagger.Correlation(
            tagger=self.tagger,
            channel_1=channel1,
            channel_2=channel2,
            binwidth=binwidth,
            n_bins=n_values,
        )
        counter.startFor(duration_seconds * 1e12)
        counter.waitUntilFinished()
        counter_data = counter.getData()
        data = np.array(counter_data)
        logger.info(
            f"Count-rate measurement finished for duration: {duration_seconds} seconds"
        )
        np.savetxt(target_location, data, delimiter=",")
        logger.info(f"Count-rate data saved to {target_location}")

    async def stop(self) -> Dict[str, Any]:
        """
        Stop the correlation measurement and return results.

        Returns:
            Dictionary with measurement results
        """
        logger.info("Stopping correlation measurement")

        # TODO: Implement correlation measurement results collection
        # This will gather and return the correlation data
        # Placeholder for future implementation

        return {
            "status": "completed",
            "duration": (
                (datetime.utcnow() - self._start_time).total_seconds()
                if self._start_time
                else 0
            ),
            "message": "Correlation measurement stopped",
        }
