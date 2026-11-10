"""Base class for measurement handlers."""

import asyncio
import logging
import os
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, Optional

logger = logging.getLogger(__name__)


class MeasurementHandler(ABC):
    """Abstract base class for measurement handlers."""

    def __init__(self, tagger=None):
        """Initialize the measurement handler.

        Args:
            tagger: Optional hardware interface (e.g., TimeTagger)
        """
        self.tagger = tagger
        # Set to True when a stop is requested so that start() skips writing
        # any final output once the running measurement is interrupted.
        self._stopped = False
        self._stop_event: Optional[asyncio.Event] = None

    def _delete_output_file(self, path: Optional[str]) -> None:
        """Delete the output file written by a measurement, if it exists.

        Used when a measurement is stopped so partially written data is
        discarded.
        """
        if not path:
            return
        try:
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Deleted output file on stop: {path}")
        except OSError as e:
            logger.error(f"Failed to delete output file {path}: {e}")

    async def _stream_live_data(
        self,
        duration_seconds: Optional[float],
        refresh_rate: int,
        publish: Callable[[], None],
    ) -> None:
        """Call ``publish()`` ``refresh_rate`` times per second.

        Returns when stop() is called or, if ``duration_seconds`` is given, once
        it has elapsed. A failing publish is logged and the stream goes on.
        """
        self._stop_event = asyncio.Event()
        loop = asyncio.get_event_loop()
        end_time = loop.time() + duration_seconds if duration_seconds is not None else float("inf")
        interval = 1.0 / refresh_rate if refresh_rate > 0 else 0.04

        while not self._stopped and loop.time() < end_time:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=interval)
                break  # stop() was called
            except asyncio.TimeoutError:
                pass
            try:
                publish()
            except Exception as e:
                logger.warning(f"{type(self).__name__}: failed to publish live data: {e}")

    @abstractmethod
    async def start(self, duration_seconds: float, metadata) -> None:
        """Start the measurement.

        Args:
            duration_seconds: Duration of measurement in seconds
            metadata: Measurement-specific metadata
        """

    @abstractmethod
    async def stop(self) -> Dict[str, Any]:
        """Stop the measurement and return results.

        Returns:
            Dictionary with measurement results
        """

