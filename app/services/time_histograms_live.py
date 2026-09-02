"""Live Time Histograms Measurement Handlers implementation."""

import asyncio
import numpy as np
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import StartStopLiveMetadata, HistogramLiveMetadata, CorrelationLiveMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging
from Swabian import TimeTagger

logger = configure_logging(__name__)


class BaseTimeHistogramLiveHandler(MeasurementHandler):
    """Base handler for live time histogram measurements streaming to Redis."""

    def __init__(self, tagger=None, measurement_name="time-histogram-live"):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self._counter: Optional[Any] = None
        self.measurement_name = measurement_name
        logger.debug(f"{self.__class__.__name__} initialized")

    async def _run_live_loop(
        self, duration_seconds: float, refresh_rate: int
    ) -> None:
        """Run the live streaming loop pushing data to Redis."""
        import json
        self._stop_event = asyncio.Event()
        
        end_time = asyncio.get_event_loop().time() + duration_seconds
        timeout = 1.0 / refresh_rate if refresh_rate > 0 else 0.04
        
        while not self._stopped and asyncio.get_event_loop().time() < end_time:
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
                break  # if stop_event is set, break
            except asyncio.TimeoutError:
                pass
            
            # Fetch data and push to redis
            if self._counter:
                try:
                    raw_data = self._counter.getData()
                    if hasattr(self._counter, 'getIndex'):
                        data = raw_data
                        index = self._counter.getIndex()
                    else:
                        # For StartStop, data is Nx2 array: [:, 0] is times, [:, 1] is counts
                        data_arr = np.array(raw_data)
                        if data_arr.size > 0 and data_arr.ndim == 2:
                            index = data_arr[:, 0]
                            data = data_arr[:, 1]
                        else:
                            index = []
                            data = []
                            
                    if hasattr(self, 'redis_client') and self.redis_client and hasattr(self, 'status_id'):
                        pub_channel = f"measurement:data:{self.status_id}"
                        payload = json.dumps({
                            "type": self.measurement_name,
                            "status_id": self.status_id,
                            "data": np.array(data).tolist(),
                            "index": np.array(index).tolist(),
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        self.redis_client.publish(pub_channel, payload)
                except Exception as e:
                    logger.warning(f"Failed to fetch or publish {self.measurement_name} data: {e}")

        # If the measurement was stopped, discard any data
        if self._stopped:
            logger.info(f"{self.measurement_name} measurement was stopped")
            if self._counter is not None:
                try:
                    self._counter.stop()
                except Exception as e:
                    logger.error(f"Failed to stop {self.measurement_name} measurement: {e}")
            return

        if self._counter:
            logger.info(
                f"{self.measurement_name} measurement finished for duration: {duration_seconds} seconds"
            )

    async def stop(self) -> Dict[str, Any]:
        """Stop measurement and return results."""
        logger.info(f"Stopping {self.measurement_name} measurement")
        self._stopped = True

        # Stop the underlying hardware counter
        if self._counter is not None:
            try:
                self._counter.stop()
            except Exception as e:
                logger.error(f"Failed to stop counter: {e}")

        if hasattr(self, '_stop_event') and self._stop_event:
            self._stop_event.set()

        if self._start_time is None:
            return {"error": "Measurement was never started"}

        duration = (datetime.utcnow() - self._start_time).total_seconds()
        return {"message": "Stopped", "duration_seconds": duration}


class StartStopLiveMeasurementHandler(BaseTimeHistogramLiveHandler):
    """Handler for live StartStop measurements streaming to Redis."""

    def __init__(self, tagger=None):
        super().__init__(tagger, measurement_name="startstop_live")

    async def start(
        self, duration_seconds: float, metadata: StartStopLiveMetadata
    ) -> None:
        logger.info("Starting StartStop-live measurement")
        self._start_time = datetime.utcnow()
        self._stopped = False
        
        click_channel = metadata.click_channel
        start_channel = metadata.start_channel
        binwidth = metadata.binwidth
        n_bins = metadata.n_bins
        refresh_rate = metadata.refresh_rate
        
        self._measurement_task = asyncio.current_task()
        self._counter = TimeTagger.StartStop(
            tagger=self.tagger, 
            click_channel=click_channel, 
            start_channel=start_channel, 
            binwidth=binwidth
        )
        self._counter.startFor(duration_seconds * 1e12)

        try:
            await self._run_live_loop(duration_seconds, refresh_rate)
        except asyncio.CancelledError:
            logger.info("StartStop-live measurement cancelled")
            raise


class HistogramLiveMeasurementHandler(BaseTimeHistogramLiveHandler):
    """Handler for live Histogram measurements streaming to Redis."""

    def __init__(self, tagger=None):
        super().__init__(tagger, measurement_name="histogram_live")

    async def start(
        self, duration_seconds: float, metadata: HistogramLiveMetadata
    ) -> None:
        logger.info("Starting Histogram-live measurement")
        self._start_time = datetime.utcnow()
        self._stopped = False
        
        click_channel = metadata.click_channel
        start_channel = metadata.start_channel
        binwidth = metadata.binwidth
        n_bins = metadata.n_bins
        refresh_rate = metadata.refresh_rate
        
        self._measurement_task = asyncio.current_task()
        self._counter = TimeTagger.Histogram(
            tagger=self.tagger, 
            click_channel=click_channel, 
            start_channel=start_channel, 
            binwidth=binwidth, 
            n_bins=n_bins
        )
        self._counter.startFor(duration_seconds * 1e12)

        try:
            await self._run_live_loop(duration_seconds, refresh_rate)
        except asyncio.CancelledError:
            logger.info("Histogram-live measurement cancelled")
            raise


class CorrelationLiveMeasurementHandler(BaseTimeHistogramLiveHandler):
    """Handler for live Correlation measurements streaming to Redis."""

    def __init__(self, tagger=None):
        super().__init__(tagger, measurement_name="correlation_live")

    async def start(
        self, duration_seconds: float, metadata: CorrelationLiveMetadata
    ) -> None:
        logger.info("Starting Correlation-live measurement")
        self._start_time = datetime.utcnow()
        self._stopped = False
        
        channel1 = metadata.channel1
        channel2 = metadata.channel2
        binwidth = metadata.binwidth
        n_bins = metadata.n_bins
        refresh_rate = metadata.refresh_rate
        
        self._measurement_task = asyncio.current_task()
        self._counter = TimeTagger.Correlation(
            tagger=self.tagger, 
            channel_1=channel1, 
            channel_2=channel2, 
            binwidth=binwidth, 
            n_bins=n_bins
        )
        self._counter.startFor(duration_seconds * 1e12)

        try:
            await self._run_live_loop(duration_seconds, refresh_rate)
        except asyncio.CancelledError:
            logger.info("Correlation-live measurement cancelled")
            raise
