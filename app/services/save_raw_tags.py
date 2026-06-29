"""Count-rate measurement handler implementation."""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import SaveRawTagsMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging
from Swabian import TimeTagger

logger = configure_logging(__name__)


class SaveRawTagsMeasurementHandler(MeasurementHandler):
    """Handler for saving raw time tags."""

    def __init__(self, tagger = None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self._fileWriter: Optional[TimeTagger.FileWriter] = None
        self._channel_list: Optional[list] = None
        self._target_file_path: Optional[str] = None
        logger.debug("SaveRawTagsMeasurementHandler initialized")

    async def start(
        self, duration_seconds: float, metadata: SaveRawTagsMetadata
    ) -> None:
        """
        Start saving raw time tags from time tagger

        Args:
            duration_seconds: Auto-stop duration (managed by Measurement)
            metadata: Measurement metadata containing 'channel_list' and 'target_file_path'
        """
        channel_list = metadata.channel_list
        target_file_path = metadata.target_file_path
        self._channel_list = channel_list
        self._target_file_path = target_file_path

        logger.info(
            f"Starting save raw tags measurement for {duration_seconds} seconds on channels {channel_list}"
        )
        self._start_time = datetime.now()
        self._stopped = False
        try:
            self._fileWriter = TimeTagger.FileWriter(
                tagger=self.tagger, filename=target_file_path, channels=channel_list
            )

            logger.info("Save raw tags started")
            self._fileWriter.startFor(int(duration_seconds * 1e12))
            
            self._stop_event = asyncio.Event()
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=duration_seconds+1)
            except asyncio.TimeoutError:
                pass

            # If the measurement was stopped, stop the writer
            if self._stopped:
                logger.info("Save raw tags was stopped; stopping file writer")
                if self._fileWriter is not None:
                    try:
                        self._fileWriter.stop()
                    except Exception as e:
                        logger.error(f"Failed to stop file writer: {e}")
                return
        finally:
            # Only free real TimeTagger instances (not mocks from tests)
            try:
                TimeTagger.freeTimeTagger(self.tagger)
            except TypeError:
                # Mock objects will raise TypeError when passed to freeTimeTagger
                pass
        logger.info(
            f"Save raw tags completed for {duration_seconds} seconds on channels {channel_list} at {target_file_path}"
        )

    async def stop(self) -> Dict[str, Any]:
        logger.info(
            f"Stopping save raw tags measurement on channels {self._channel_list}"
        )
        self._stopped = True

        if self._stop_event:
            self._stop_event.set()

        if self._fileWriter:
            try:
                self._fileWriter.stop()
            except Exception as e:
                logger.error(f"Failed to stop file writer: {e}")

        # Only free real TimeTagger instances (not mocks from tests)
        try:
            TimeTagger.freeTimeTagger(self.tagger)
        except TypeError:
            pass

        # Delete any raw tags file that was already written for this measurement
        self._delete_output_file(self._target_file_path)

        logger.info("Save raw tags stopped and data file deleted")

        return {
            "status": "stopped",
            "duration": (
                (datetime.now() - self._start_time).total_seconds()
                if self._start_time
                else 0
            ),
            "message": "Save raw tags measurement stopped and data file deleted",
        }
