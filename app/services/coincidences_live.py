"""Coincidences live measurement handler implementation."""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
import numpy as np
from app.models import CoincidencesMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging

logger = configure_logging(__name__)


class CoincidencesLiveMeasurementHandler(MeasurementHandler):
    """Handler for live coincidences measurements streaming to Redis."""

    def __init__(self, tagger=None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self._counter: Optional[Any] = None
        self._target_location: Optional[str] = None
        self._stopped = False
        logger.debug("CoincidencesLiveMeasurementHandler initialized")

    async def start(
        self, duration_seconds: Optional[float], metadata: CoincidencesMetadata
    ) -> None:
        """
        Start coincidences live measurement.

        Args:
            duration_seconds: Auto-stop duration in seconds (ignored for live unless set)
            metadata: Measurement metadata containing:
                - channels: List of channel numbers to measure (required)
                - binwidth: Bin width in picoseconds (default: 1e9)
                - n_values: Number of bins (default: 1)
                - target_location: Target file path
        """
        logger.info("Starting live coincidences measurement")
        self._start_time = datetime.utcnow()
        self._stopped = False

        # Extract parameters from metadata
        channels = metadata.channels
        coincidences = metadata.coincidences or []
        coincidence_window = getattr(metadata, "coincidence_window", 1000)
        timestamp_str = getattr(metadata, "timestamp", "Last")
        binwidth = metadata.binwidth
        n_values = metadata.n_values
        target_location = metadata.target_location
        refresh_rate = getattr(metadata, 'refresh_rate', 25)
        self._target_location = target_location
        logger.debug(
            f"Coincidences live params - coincidences: {coincidences}, channels: {channels}, binwidth: {binwidth}, n_values: {n_values}, target: {target_location}, refresh_rate: {refresh_rate}"
        )
        
        self._measurement_task = asyncio.current_task()

        if self.tagger is not None:
            try:
                from Swabian import TimeTagger
                timestamp_map = {
                    "last": getattr(TimeTagger, "CoincidenceTimestamp_Last", 0),
                    "first": getattr(TimeTagger, "CoincidenceTimestamp_First", 1),
                    "listedfirst": getattr(TimeTagger, "CoincidenceTimestamp_ListedFirst", 2),
                    "average": getattr(TimeTagger, "CoincidenceTimestamp_Average", 3),
                }
                if hasattr(TimeTagger, "CoincidenceTimestamp"):
                    timestamp_map = {
                        "last": TimeTagger.CoincidenceTimestamp.Last,
                        "first": TimeTagger.CoincidenceTimestamp.First,
                        "listedfirst": TimeTagger.CoincidenceTimestamp.ListedFirst,
                        "average": TimeTagger.CoincidenceTimestamp.Average,
                    }
                tt_timestamp = timestamp_map.get(str(timestamp_str).lower(), timestamp_map.get("last", 0))

                if len(coincidences) == 1:
                    self._coincidence = TimeTagger.Coincidence(
                        self.tagger,
                        channels=coincidences[0],
                        coincidenceWindow=coincidence_window,
                        timestamp=tt_timestamp,
                    )
                    v_channels = [self._coincidence.getChannel()]
                else:
                    self._coincidence = TimeTagger.Coincidences(
                        self.tagger,
                        coincidenceGroups=coincidences,
                        coincidenceWindow=coincidence_window,
                        timestamp=tt_timestamp,
                    )
                    v_channels = list(self._coincidence.getChannels())

                self._counter = TimeTagger.Countrate(
                    tagger=self.tagger,
                    channels=v_channels,
                )
                if duration_seconds is not None:
                    self._counter.startFor(int(duration_seconds * 1e12))
            except Exception as e:
                logger.warning(f"Coincidences live hardware initialization skipped or failed: {e}")

        try:
            import json
            self._stop_event = asyncio.Event()
            
            end_time = asyncio.get_event_loop().time() + duration_seconds if duration_seconds is not None else float('inf')
            timeout = 1.0 / refresh_rate if refresh_rate > 0 else 0.04
            
            # Loop at the specified refresh rate
            while not self._stopped and asyncio.get_event_loop().time() < end_time:
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=timeout)
                    break  # if stop_event is set, break
                except asyncio.TimeoutError:
                    pass
                
                # Fetch data and push to redis
                try:
                    if hasattr(self, 'redis_client') and self.redis_client and hasattr(self, 'status_id'):
                        pub_channel = f"measurement:data:{self.status_id}"
                        if self._counter is not None and hasattr(self._counter, 'getData'):
                            data = list(self._counter.getData())
                        else:
                            # Mock data for testing/fallback
                            num_items = len(coincidences) if coincidences else len(channels)
                            data = [0] * num_items
                        payload = json.dumps({
                            "type": "coincidences_live",
                            "status_id": self.status_id,
                            "data": data,
                            "timestamp": datetime.utcnow().isoformat()
                        })
                        self.redis_client.publish(pub_channel, payload)
                except Exception as e:
                    logger.warning(f"Failed to fetch or publish coincidences data: {e}")

            if self._stopped:
                logger.info("Live coincidences measurement was stopped")
                if self._counter is not None:
                    try:
                        self._counter.stop()
                    except Exception as e:
                        logger.error(f"Failed to stop coincidences measurement: {e}")
                return

        except asyncio.CancelledError:
            logger.info("Live coincidences measurement cancelled")
            self._stopped = True
            if self._counter is not None:
                self._counter.stop()
            raise
        except Exception as e:
            logger.error(f"Error during live coincidences measurement: {e}")
            self._stopped = True
            if self._counter is not None:
                self._counter.stop()
            raise

    async def stop(self) -> Dict[str, Any]:
        """
        Stop the coincidences measurement and return results.

        Returns:
            Dictionary with measurement results
        """
        logger.info("Stopping live coincidences measurement")
        self._stopped = True
        
        if getattr(self, '_stop_event', None):
            self._stop_event.set()

        # Stop the underlying hardware measurement
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
            "message": "Live coincidences measurement stopped",
        }
