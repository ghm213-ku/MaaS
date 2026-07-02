"""Set parameters measurement handler implementation."""

import asyncio
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import SetParametersMetadata
from app.services.measurement import MeasurementHandler
from app.utils.logger import configure_logging
from Swabian import TimeTagger

logger = configure_logging(__name__)


class SetParametersHandler(MeasurementHandler):
    """Handler for setting channel parameters."""

    def __init__(self, tagger: TimeTagger = None):
        super().__init__(tagger)
        self._start_time: Optional[datetime] = None
        self._stopped = False
        logger.debug("SetParametersHandler initialized")

    async def start(
        self, duration_seconds: float, metadata: SetParametersMetadata
    ) -> None:
        """
        Set channel parameters.

        Args:
            duration_seconds: Unused for this handler (typically 0)
            metadata: Measurement metadata containing channels, input_delay, trigger_voltage
        """
        logger.info("Starting set-parameters")
        self._start_time = datetime.utcnow()
        self._stopped = False

        # Extract parameters from metadata
        channels = metadata.channels
        input_delay = metadata.input_delay
        trigger_voltage = metadata.trigger_voltage

        logger.debug(
            f"Set parameters params - channels: {channels}, "
            f"input_delay: {input_delay}, trigger_voltage: {trigger_voltage}"
        )

        # Handler logic is intentionally left empty for now
        self.tagger.setInputDelay(channels, input_delay)
        self.tagger.setTriggerLevel(channels, trigger_voltage)
            
        logger.info("Set parameters finished")

    async def stop(self) -> Dict[str, Any]:
        """
        Stop the operation and return results.

        Returns:
            Dictionary with operation results
        """
        logger.info("Stopping set-parameters operation")
        self._stopped = True

        duration = 0
        if self._start_time:
            duration = (datetime.utcnow() - self._start_time).total_seconds()

        results = {
            "status": "stopped",
            "duration_seconds": duration,
            "stopped_at": datetime.utcnow().isoformat(),
            "message": "Set parameters operation completed",
        }

        return results
