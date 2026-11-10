"""Save-raw-tags measurement handler implementation."""

import logging
import asyncio
import glob
import os
import re
from typing import Optional, Dict, Any, List
from datetime import datetime
from app.models import SaveRawTagsMetadata
from app.handlers.base import MeasurementHandler
from Swabian import TimeTagger

logger = logging.getLogger(__name__)


def ttbin_files(filename: Optional[str]) -> List[str]:
    """Return the files a TimeTagger FileWriter wrote for ``filename``.

    FileWriter appends ".ttbin" unless the name already ends with it, and
    splits the stream into numbered parts, so "run" produces "run.ttbin",
    "run.1.ttbin", "run.2.ttbin", ...
    """
    if not filename:
        return []
    base = filename[: -len(".ttbin")] if filename.endswith(".ttbin") else filename
    pattern = re.compile(re.escape(os.path.basename(base)) + r"(\.\d+)?\.ttbin$")
    candidates = glob.glob(glob.escape(base) + "*.ttbin")
    return sorted(f for f in candidates if pattern.fullmatch(os.path.basename(f)))


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
            # The tagger is shared by every job on this worker and is owned by
            # the worker, so it must not be freed here. Release the writer only.
            if self._fileWriter is not None and not self._stopped:
                try:
                    self._fileWriter.stop()
                except Exception as e:
                    logger.error(f"Failed to stop file writer: {e}")
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

        # Delete every raw tags file FileWriter already wrote for this
        # measurement (the .ttbin file and its numbered parts)
        for path in ttbin_files(self._target_file_path):
            self._delete_output_file(path)

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
