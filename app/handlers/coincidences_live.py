"""Coincidences live measurement handler implementation."""

import logging
import asyncio
import json
from typing import Optional, Dict, Any
from datetime import datetime
import numpy as np
from app.models import CoincidencesMetadata
from app.handlers.coincidences import create_coincidence_counter
from app.handlers.base import MeasurementHandler
from app.handlers.counter_utils import wait_until_finished

logger = logging.getLogger(__name__)


class CoincidencesLiveMeasurementHandler(MeasurementHandler):
    """Handler for live coincidences measurements streaming to Redis.

    Uses the same TimeTagger setup as the one-shot coincidences measurement
    (Coincidences + Counter with binwidth/n_values) and publishes the counter
    data at ``refresh_rate`` instead of saving it to a file.
    """

    def __init__(self, tagger=None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self._coincidence: Optional[Any] = None
        self._counter: Optional[Any] = None
        self._virtual_channels: list[int] = []
        self._binwidth: int = 0
        self._stopped = False
        logger.debug("CoincidencesLiveMeasurementHandler initialized")

    def _publish(self, coincidences: list[list[int]], final: bool = False) -> None:
        """Read the counter and publish one update to Redis.

        ``final`` marks the last update of a timed (startFor) acquisition.
        Each group is also published on its own ``:stream_{i}`` channel, also
        when there is only one group.
        """
        if not (getattr(self, "redis_client", None) and hasattr(self, "status_id")):
            return

        raw = np.nan_to_num(
            np.array(self._counter.getData(), dtype=float), nan=0.0, posinf=0.0, neginf=0.0
        )
        # Counter.getData() is (n_channels, n_values): counts per bin, oldest first.
        rows = raw.reshape(len(coincidences), -1).tolist() if raw.size else [[] for _ in coincidences]
        binwidth_s = self._binwidth * 1e-12
        now_iso = datetime.utcnow().isoformat()

        streams = []
        for i, group in enumerate(coincidences):
            row = rows[i]
            # Counts per second in the most recent bin
            rate = row[-1] / binwidth_s if row and binwidth_s > 0 else 0.0
            streams.append({
                "stream_index": i,
                "coincidence": group,
                "virtual_channel": self._virtual_channels[i],
                "rate": rate,
                "data": row,
            })

        for stream in streams:
            self.redis_client.publish(
                f"measurement:data:{self.status_id}:stream_{stream['stream_index']}",
                json.dumps({
                    "type": "coincidences_live_stream",
                    "status_id": self.status_id,
                    **stream,
                    "final": final,
                    "timestamp": now_iso,
                }),
            )

        self.redis_client.publish(
            f"measurement:data:{self.status_id}",
            json.dumps({
                "type": "coincidences_live",
                "status_id": self.status_id,
                "coincidences": coincidences,
                "virtual_channels": self._virtual_channels,
                "streams": streams,
                "data": rows,
                "final": final,
                "timestamp": now_iso,
            }),
        )

    def _stop_counter(self) -> None:
        if self._counter is not None:
            try:
                self._counter.stop()
            except Exception as e:
                logger.error(f"Failed to stop coincidences measurement: {e}")

    async def start(
        self, duration_seconds: Optional[float], metadata: CoincidencesMetadata
    ) -> None:
        """
        Start coincidences live measurement.

        Args:
            duration_seconds: Auto-stop duration in seconds; None runs until stopped
            metadata: Same fields as the one-shot coincidences measurement
                (coincidences, coincidence_window, timestamp, binwidth, n_values)
                plus refresh_rate. target_location is not used: live data is
                only streamed.
        """
        logger.info("Starting live coincidences measurement")
        self._start_time = datetime.utcnow()
        self._measurement_task = asyncio.current_task()

        coincidences = metadata.coincidences or []
        refresh_rate = metadata.refresh_rate
        self._binwidth = metadata.binwidth

        # Hardware setup errors propagate so the job is marked failed instead
        # of streaming zeros.
        self._coincidence, self._counter, self._virtual_channels = create_coincidence_counter(
            self.tagger, metadata
        )
        if duration_seconds is not None:
            self._counter.startFor(int(duration_seconds * 1e12))

        try:
            await self._stream_live_data(duration_seconds, refresh_rate, lambda: self._publish(coincidences))

            if self._stopped:
                logger.info("Live coincidences measurement was stopped")
                self._stop_counter()
            elif duration_seconds is not None:
                # Timed acquisition: let startFor finish, then publish the
                # complete buffer once so clients get every bin.
                await wait_until_finished(self._counter)
                try:
                    self._publish(coincidences, final=True)
                except Exception as e:
                    logger.warning(f"Failed to publish final coincidences data: {e}")
        except asyncio.CancelledError:
            logger.info("Live coincidences measurement cancelled")
            self._stopped = True
            self._stop_counter()
            raise

    async def stop(self) -> Dict[str, Any]:
        """Stop the live coincidences measurement."""
        logger.info("Stopping live coincidences measurement")
        self._stopped = True

        if self._stop_event:
            self._stop_event.set()

        self._stop_counter()

        return {
            "status": "stopped",
            "duration": (
                (datetime.utcnow() - self._start_time).total_seconds()
                if self._start_time
                else 0
            ),
            "message": "Live coincidences measurement stopped",
        }
