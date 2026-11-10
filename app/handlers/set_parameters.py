"""Set parameters measurement handler implementation."""

import logging
from typing import Optional, Dict, Any
from datetime import datetime
from app.models import SetParametersMetadata
from app.handlers.base import MeasurementHandler
from app.services.channel_parameters import record_channel_parameters
from Swabian import TimeTagger

logger = logging.getLogger(__name__)


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

        # Handler logic
        if input_delay is not None:
            for channel in channels:
                logger.debug(f"Setting input delay for channel {channel} (type: {type(channel)}) to {input_delay} (type: {type(input_delay)})")
                self.tagger.setInputDelay(int(channel), int(input_delay))
        if trigger_voltage is not None:
            for channel in channels:
                self.tagger.setTriggerLevel(int(channel), float(trigger_voltage))

        # Record what the hardware now reports so clients can read it back
        redis_client = getattr(self, "redis_client", None)
        if redis_client is not None:
            record_channel_parameters(redis_client, self.tagger, channels)

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
