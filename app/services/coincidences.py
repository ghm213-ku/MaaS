"""Coincidences measurement handler implementation."""

import asyncio
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import CoincidencesMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging
from Swabian import TimeTagger

logger = configure_logging(__name__)


def _resolve_timestamp(timestamp_str: str):
    """Map the API timestamp name ('Last', 'First', ...) to the TimeTagger enum."""
    if hasattr(TimeTagger, "CoincidenceTimestamp"):
        timestamp_map = {
            "last": TimeTagger.CoincidenceTimestamp.Last,
            "first": TimeTagger.CoincidenceTimestamp.First,
            "listedfirst": TimeTagger.CoincidenceTimestamp.ListedFirst,
            "average": TimeTagger.CoincidenceTimestamp.Average,
        }
    else:
        timestamp_map = {
            "last": getattr(TimeTagger, "CoincidenceTimestamp_Last", 0),
            "first": getattr(TimeTagger, "CoincidenceTimestamp_First", 1),
            "listedfirst": getattr(TimeTagger, "CoincidenceTimestamp_ListedFirst", 2),
            "average": getattr(TimeTagger, "CoincidenceTimestamp_Average", 3),
        }
    return timestamp_map.get(str(timestamp_str).lower(), timestamp_map["last"])


def create_coincidence_counter(tagger, metadata: CoincidencesMetadata):
    """Build the Coincidences virtual channels and a Counter over them.

    Shared by the one-shot and live coincidence handlers so both measure the
    same way: TimeTagger.Coincidences(groups, coincidence_window, timestamp)
    feeding TimeTagger.Counter(binwidth, n_values).

    Returns:
        (coincidence, counter, virtual_channels)
    """
    coincidence = TimeTagger.Coincidences(
        tagger,
        metadata.coincidences or [],
        metadata.coincidence_window,
        _resolve_timestamp(metadata.timestamp),
    )
    virtual_channels = [int(ch) for ch in coincidence.getChannels()]
    counter = TimeTagger.Counter(
        tagger=tagger,
        channels=virtual_channels,
        binwidth=metadata.binwidth,
        n_values=metadata.n_values,
    )
    return coincidence, counter, virtual_channels


class CoincidencesMeasurementHandler(MeasurementHandler):
    """Handler for coincidences measurements."""

    def __init__(self, tagger=None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self._counter: Optional[Any] = None
        self._coincidence: Optional[Any] = None
        self._target_location: Optional[str] = None
        self._count = 0
        self._stopped = False
        self._stop_event: Optional[asyncio.Event] = None
        logger.debug("CoincidencesMeasurementHandler initialized")

    async def start(
        self, duration_seconds: float, metadata: CoincidencesMetadata
    ) -> Dict[str, Any]:
        """
        Start coincidences measurement.

        Args:
            duration_seconds: Auto-stop duration in seconds
            metadata: Measurement metadata containing:
                - coincidences: List of lists of channel numbers to measure (required)
                - coincidence_window: Coincidence window in picoseconds (default: 1000)
                - timestamp: Timestamp mode (default: Last)
                - binwidth: Bin width in picoseconds (default: 1e9)
                - n_values: Number of bins (default: 1)
                - target_location: Target file path
        """
        logger.info("Starting coincidences measurement")
        self._start_time = datetime.utcnow()
        self._target_location = metadata.target_location
        self._stopped = False
        self._count = 0

        self._measurement_task = asyncio.current_task()

        # Hardware setup errors propagate so the job is marked failed instead
        # of "completing" with no data.
        self._coincidence, self._counter, _ = create_coincidence_counter(self.tagger, metadata)
        self._counter.startFor(int(duration_seconds * 1e12))

        try:
            import os
            self._stop_event = asyncio.Event()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=duration_seconds + 1)
            except asyncio.TimeoutError:
                pass

            if self._stopped:
                logger.info("Coincidences measurement was stopped; skipping data save")
                if self._counter is not None:
                    try:
                        self._counter.stop()
                    except Exception as e:
                        logger.error(f"Failed to stop coincidences counter: {e}")
                return {
                    "status": "stopped",
                    "duration": (
                        (datetime.utcnow() - self._start_time).total_seconds()
                        if self._start_time
                        else 0
                    ),
                }

            counter_data = self._counter.getData()
            self._count = int(np.sum(counter_data))
            data = np.array(counter_data)
            logger.info(
                f"Coincidences measurement finished for duration: {duration_seconds} seconds"
            )
            if self._target_location:
                os.makedirs(os.path.dirname(os.path.abspath(self._target_location)), exist_ok=True)
                np.savetxt(self._target_location, data, delimiter=",")
                logger.info(f"Coincidences data saved to {self._target_location}")

        except asyncio.CancelledError:
            logger.info("Coincidences measurement cancelled")
            self._stopped = True
            if self._counter is not None:
                try:
                    self._counter.stop()
                except Exception:
                    pass
            raise

        return {
            "status": "completed",
            "duration": (
                (datetime.utcnow() - self._start_time).total_seconds()
                if self._start_time
                else duration_seconds
            ),
            "count": self._count,
        }

    async def stop(self) -> Dict[str, Any]:
        """
        Stop the coincidences measurement and return results.

        Returns:
            Dictionary with measurement results
        """
        logger.info("Stopping coincidences measurement")
        self._stopped = True

        if getattr(self, "_stop_event", None):
            self._stop_event.set()

        # Stop the underlying hardware measurement so the running job ends
        if self._counter is not None:
            try:
                self._counter.stop()
            except Exception as e:
                logger.error(f"Failed to stop coincidences measurement: {e}")

        # Delete any data file that was already written for this measurement
        if self._target_location:
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
