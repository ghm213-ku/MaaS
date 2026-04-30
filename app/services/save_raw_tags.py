"""Count-rate measurement handler implementation."""
import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging
from Swabian import TimeTagger

logger = configure_logging(__name__)

class SaveRawTagsMeasurementHandler(MeasurementHandler):
    """Handler for saving raw time tags."""

    def __init__(self, tagger: Optional[TimeTagger.TimeTagger] = None):
        super().__init__(tagger)
        self._measurement_task: Optional[asyncio.Task] = None
        self._start_time: Optional[datetime] = None
        logger.debug("SaveRawTagsMeasurementHandler initialized")
        
    async def start(self, duration_seconds: int, channels_list: list[int], target_file_path: str) -> None:
        """
        Start saving raw time tags from time tagger

        Args:
            duration_seconds (int): Duration for which the time tags should be saved
            channels_list (list[int]): List of channels to save time tags from
            target_file_path (str): Path to the file where time tags should be saved
        """
        logger.info(f"Starting save raw tags measurement for {duration_seconds} seconds on channels {channels_list}")
        self._start_time = datetime.now()
        fileWriter = TimeTagger.FileWriter(target_file_path, tagger=self._tagger, channels=channels_list)
        
        logger.info("Save raw tags started")
        fileWriter.startFor(int(duration_seconds*1e12)) 
        fileWriter.waitUntilFinished()
        logger.info(f"Save raw tags completed for {duration_seconds} seconds on channels {channels_list} at {target_file_path}")
    
    async def stop(self) -> None:
        logger.info(f"Stopping save raw tags measurement on channels {self._channels_list}")
        if self._fileWriter:
            self._fileWriter.stop()
        
        logger.info(f"Save raw tags stopped for channels {self._channels_list}")