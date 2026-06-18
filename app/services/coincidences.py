"""Coincidences measurement handler implementation."""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import CoincidencesMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging

logger = configure_logging(__name__)


class CoincidencesMeasurementHandler(MeasurementHandler):
    """Handler for coincidences measurements."""

    def __init__(self, tagger=None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self._counter: Optional[Any] = None
        self._target_location: Optional[str] = None
        logger.debug("CoincidencesMeasurementHandler initialized")

    async def start(
        self, duration_seconds: float, metadata: CoincidencesMetadata
    ) -> None:
        """
        Start coincidences measurement.

        Args:
            duration_seconds: Auto-stop duration in seconds
            metadata: Measurement metadata containing:
                - channels: List of channel numbers to measure (required)
                - binwidth: Bin width in picoseconds (default: 1e9)
                - n_values: Number of bins (default: 1)
                - target_location: Target file path (default: desktop/MaasData/{datetime}/{measurement-type})
        """
        logger.info("Starting coincidences measurement")
        self._start_time = datetime.utcnow()
        self._target_location = metadata.target_location

        # TODO: Implement coincidences measurement business logic.
        # This will configure the tagger and collect coincidence data.
        # Placeholder for future implementation.

    async def stop(self) -> Dict[str, Any]:
        """
        Stop the coincidences measurement and return results.

        Returns:
            Dictionary with measurement results
        """
        logger.info("Stopping coincidences measurement")
        self._stopped = True

        # Stop the underlying hardware measurement so the running job ends
        if self._counter is not None:
            try:
                self._counter.stop()
            except Exception as e:
                logger.error(f"Failed to stop coincidences measurement: {e}")

        # Delete any data file that was already written for this measurement
        self._delete_output_file(self._target_location)

        return {
            "status": "stopped",
            "duration": (
                (datetime.utcnow() - self._start_time).total_seconds()
                if self._start_time
                else 0
            ),
            "message": "Coincidences measurement stopped and data file deleted",
        }
