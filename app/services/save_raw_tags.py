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
        
    async def start(self, duration_seconds: Optional[int], metadata: Optional[Dict[str, Any]]) -> None:
        """
        Start saving raw time tags from time tagger

        Args:
            duration_seconds: Auto-stop duration (managed by Measurement)
            metadata: Measurement metadata containing 'channel_list' and 'target_file_path'
        """
        metadata = metadata or {}
        channels_list = metadata.get('channel_list', [])
        target_file_path = metadata.get('target_file_path', '')
        
        logger.info(f"Starting save raw tags measurement for {duration_seconds} seconds on channels {channels_list}")
        self._start_time = datetime.now()
        fileWriter = TimeTagger.FileWriter(target_file_path, tagger=self.tagger, channels=channels_list)
        
        logger.info("Save raw tags started")
        fileWriter.startFor(int(duration_seconds*1e12)) 
        fileWriter.waitUntilFinished()
        logger.info(f"Save raw tags completed for {duration_seconds} seconds on channels {channels_list} at {target_file_path}")
    
    async def stop(self) -> None:
        logger.info(f"Stopping save raw tags measurement on channels {self._channels_list}")
        if self._fileWriter:
            self._fileWriter.stop()
        
        logger.info(f"Save raw tags stopped for channels {self._channels_list}")