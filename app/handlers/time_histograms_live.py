"""Live time-histogram handlers (StartStop, Histogram, Correlation) streaming to Redis."""

import asyncio
import json
import logging
from abc import abstractmethod
from datetime import datetime
from typing import Any, Dict, Optional

import numpy as np
from Swabian import TimeTagger

from app.handlers.base import MeasurementHandler
from app.models import CorrelationLiveMetadata, HistogramLiveMetadata, StartStopLiveMetadata

logger = logging.getLogger(__name__)


class BaseTimeHistogramLiveHandler(MeasurementHandler):
    """Runs a TimeTagger histogram measurement and publishes its data at refresh_rate.

    Each update is published on ``measurement:data:<status_id>`` as
    ``{"type", "status_id", "data", "index", "timestamp"}``, where ``index`` holds
    the bin times (ps) and ``data`` the counts.
    """

    measurement_name = "time-histogram-live"

    def __init__(self, tagger=None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self._counter: Optional[Any] = None

    @abstractmethod
    def _create_measurement(self, metadata) -> Any:
        """Create the TimeTagger measurement object for ``metadata``."""

    async def start(self, duration_seconds: Optional[float], metadata) -> None:
        logger.info(f"Starting {self.measurement_name} measurement")
        self._start_time = datetime.utcnow()
        self._measurement_task = asyncio.current_task()

        self._counter = self._create_measurement(metadata)
        if duration_seconds is not None:
            self._counter.startFor(int(duration_seconds * 1e12))

        try:
            await self._stream_live_data(duration_seconds, metadata.refresh_rate, self._publish)
        except asyncio.CancelledError:
            logger.info(f"{self.measurement_name} measurement cancelled")
            raise

        if self._stopped:
            logger.info(f"{self.measurement_name} measurement was stopped")
            self._stop_counter()
        else:
            logger.info(f"{self.measurement_name} measurement finished after {duration_seconds} seconds")

    def _read_data(self) -> tuple[Any, Any]:
        """Return (index, data) of the current histogram."""
        raw_data = self._counter.getData()
        if hasattr(self._counter, "getIndex"):
            return self._counter.getIndex(), raw_data
        # StartStop returns an Nx2 array: [:, 0] bin times, [:, 1] counts
        data_arr = np.array(raw_data)
        if data_arr.size > 0 and data_arr.ndim == 2:
            return data_arr[:, 0], data_arr[:, 1]
        return [], []

    def _publish(self) -> None:
        if self._counter is None or not (getattr(self, "redis_client", None) and hasattr(self, "status_id")):
            return
        index, data = self._read_data()
        self.redis_client.publish(
            f"measurement:data:{self.status_id}",
            json.dumps({
                "type": self.measurement_name,
                "status_id": self.status_id,
                "data": np.array(data).tolist(),
                "index": np.array(index).tolist(),
                "timestamp": datetime.utcnow().isoformat(),
            }),
        )

    def _stop_counter(self) -> None:
        if self._counter is not None:
            try:
                self._counter.stop()
            except Exception as e:
                logger.error(f"Failed to stop {self.measurement_name} measurement: {e}")

    async def stop(self) -> Dict[str, Any]:
        """Stop the measurement and return how long it ran."""
        logger.info(f"Stopping {self.measurement_name} measurement")
        self._stopped = True
        self._stop_counter()
        if self._stop_event:
            self._stop_event.set()

        if self._start_time is None:
            return {"error": "Measurement was never started"}
        duration = (datetime.utcnow() - self._start_time).total_seconds()
        return {"message": "Stopped", "duration_seconds": duration}


class StartStopLiveMeasurementHandler(BaseTimeHistogramLiveHandler):
    """Live TimeTagger StartStop: time from each start click to the next click."""

    measurement_name = "startstop_live"

    def _create_measurement(self, metadata: StartStopLiveMetadata) -> Any:
        return TimeTagger.StartStop(
            tagger=self.tagger,
            click_channel=metadata.click_channel,
            start_channel=metadata.start_channel,
            binwidth=metadata.binwidth,
        )


class HistogramLiveMeasurementHandler(BaseTimeHistogramLiveHandler):
    """Live TimeTagger Histogram of click times after each start."""

    measurement_name = "histogram_live"

    def _create_measurement(self, metadata: HistogramLiveMetadata) -> Any:
        return TimeTagger.Histogram(
            tagger=self.tagger,
            click_channel=metadata.click_channel,
            start_channel=metadata.start_channel,
            binwidth=metadata.binwidth,
            n_bins=metadata.n_bins,
        )


class CorrelationLiveMeasurementHandler(BaseTimeHistogramLiveHandler):
    """Live TimeTagger Correlation between channel1 and channel2."""

    measurement_name = "correlation_live"

    def _create_measurement(self, metadata: CorrelationLiveMetadata) -> Any:
        return TimeTagger.Correlation(
            tagger=self.tagger,
            channel_1=metadata.channel1,
            channel_2=metadata.channel2,
            binwidth=metadata.binwidth,
            n_bins=metadata.n_bins,
        )
