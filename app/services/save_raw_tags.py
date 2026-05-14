"""Count-rate measurement handler implementation."""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import SaveRawTagsMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging
# from Swabian import TimeTagger

logger = configure_logging(__name__)


class SaveRawTagsMeasurementHandler(MeasurementHandler):
    """Handler for saving raw time tags."""

    def __init__(self, tagger = None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        self._fileWriter: Optional[TimeTagger.FileWriter] = None
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

        logger.info(
            f"Starting save raw tags measurement for {duration_seconds} seconds on channels {channel_list}"
        )
        self._start_time = datetime.now()
        try:
            self._fileWriter = TimeTagger.FileWriter(
                tagger=self.tagger, filename=target_file_path, channels=channel_list
            )

            logger.info("Save raw tags started")
            self._fileWriter.startFor(int(duration_seconds * 1e12))
            self._fileWriter.waitUntilFinished()
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

    async def stop(self) -> None:
        logger.info(
            f"Stopping save raw tags measurement on channels {self._channel_list}"
        )
        if self._fileWriter:
            self._fileWriter.stop()

        logger.info("Save raw tags stopped")
        TimeTagger.freeTimeTagger(self.tagger)
