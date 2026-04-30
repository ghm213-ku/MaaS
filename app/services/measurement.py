"""Core measurement service - manages measurement lifecycle and tracking."""
import uuid
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, Callable
from abc import ABC, abstractmethod
from app.utils.logger import configure_logging
from Swabian import TimeTagger
logger = configure_logging(__name__)


class MeasurementHandler(ABC):
    """Abstract base class for measurement type handlers."""
    @abstractmethod
    def __init__(self, tagger: Optional[TimeTagger.TimeTagger] = None):
        """Initialize the handler with optional TimeTagger instance."""
        self._tagger = tagger
    
    @abstractmethod
    async def start(self, duration_seconds: Optional[int], metadata: Optional[Dict[str, Any]]) -> None:
        """Start the measurement."""
        pass
    
    @abstractmethod
    async def stop(self) -> None:
        """Stop the measurement and return results."""
        pass


class Measurement:
    """Represents an active measurement."""
    
    def __init__(
        self,
        measurement_id: str,
        measurement_type: str,
        handler: MeasurementHandler,
        duration_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.measurement_id = measurement_id
        self.measurement_type = measurement_type
        self.handler = handler
        self.started_at = datetime.utcnow()
        self.status = "active"
        self.metadata = metadata or {}
        self.results: Optional[Dict[str, Any]] = None
        self.duration_task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()
        
        logger.debug(
            f"[{measurement_id}] Measurement created - "
            f"type={measurement_type}, duration={duration_seconds}s, metadata={metadata}"
        )
        
        # Start auto-stop timer if duration specified
        if duration_seconds:
            self.duration_task = asyncio.create_task(self._auto_stop_after(duration_seconds))
            logger.info(f"[{measurement_id}] Auto-stop scheduled in {duration_seconds} seconds")
    
    async def _auto_stop_after(self, seconds: int) -> None:
        """Automatically stop measurement after specified duration."""
        try:
            await asyncio.sleep(seconds)
            logger.info(f"[{self.measurement_id}] Auto-stop timer triggered")
            await self.stop()
        except asyncio.CancelledError:
            logger.debug(f"[{self.measurement_id}] Auto-stop timer cancelled")
    
    async def start_handler(self) -> None:
        """Start the measurement handler."""
        async with self._lock:
            try:
                logger.info(f"[{self.measurement_id}] Starting handler")
                duration = None
                if self.duration_task:
                    # If there's a duration task, we don't pass duration to handler
                    # as the task manages the timing
                    pass
                await self.handler.start(None, self.metadata)
                logger.info(f"[{self.measurement_id}] Handler started successfully")
            except Exception as e:
                logger.error(f"[{self.measurement_id}] Failed to start handler: {e}", exc_info=True)
                self.status = "error"
                if self.duration_task:
                    self.duration_task.cancel()
                raise
    
    async def stop(self) -> Dict[str, Any]:
        """Stop the measurement and return results."""
        async with self._lock:
            if self.status != "active":
                logger.warning(f"[{self.measurement_id}] Stop called but status is {self.status}")
                return self.results or {}
            
            try:
                logger.info(f"[{self.measurement_id}] Stopping measurement")
                self.status = "stopping"
                
                # Cancel auto-stop timer if running
                if self.duration_task and not self.duration_task.done():
                    logger.debug(f"[{self.measurement_id}] Cancelling auto-stop timer")
                    self.duration_task.cancel()
                    try:
                        await self.duration_task
                    except asyncio.CancelledError:
                        pass
                
                # Stop the handler and collect results
                self.results = await self.handler.stop()
                self.status = "stopped"
                
                duration = (datetime.utcnow() - self.started_at).total_seconds()
                logger.info(
                    f"[{self.measurement_id}] Measurement stopped - "
                    f"duration={duration:.2f}s, results={self.results}"
                )
                
                return self.results
                
            except Exception as e:
                logger.error(f"[{self.measurement_id}] Failed to stop measurement: {e}", exc_info=True)
                self.status = "error"
                raise
    
    def get_duration(self) -> float:
        """Get duration in seconds since start."""
        return (datetime.utcnow() - self.started_at).total_seconds()


class MeasurementService:
    """Service for managing active measurements."""
    
    def __init__(self):
        self._measurements: Dict[str, Measurement] = {}
        self._handlers: Dict[str, type[MeasurementHandler]] = {}
        self._lock = asyncio.Lock()
        # self._tagger = TimeTagger.createTimeTagger()
        logger.info("MeasurementService initialized")
    
    def register_handler(self, measurement_type: str, handler_class: type[MeasurementHandler]) -> None:
        """
        Register a handler for a measurement type.
        
        Args:
            measurement_type: Type identifier (e.g., "count_rate")
            handler_class: Handler class implementing MeasurementHandler
        """
        self._handlers[measurement_type] = handler_class
        logger.info(f"Registered handler for measurement type: {measurement_type}")
    
    async def start_measurement(
        self,
        measurement_type: str,
        duration_seconds: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Start a new measurement.
        
        Args:
            measurement_type: Type of measurement
            duration_seconds: Optional auto-stop duration in seconds
            metadata: Optional custom metadata
            
        Returns:
            Measurement ID
            
        Raises:
            ValueError: If measurement type is not registered
        """
        if measurement_type not in self._handlers:
            logger.error(f"Unknown measurement type: {measurement_type}")
            raise ValueError(f"Unknown measurement type: {measurement_type}")
        
        # Generate unique measurement ID
        measurement_id = str(uuid.uuid4())
        logger.info(f"[{measurement_id}] Starting new measurement - type={measurement_type}")
        
        try:
            # Create handler instance
            handler_class = self._handlers[measurement_type]
            handler = handler_class()
            
            # Create measurement object
            async with self._lock:
                measurement = Measurement(
                    measurement_id=measurement_id,
                    measurement_type=measurement_type,
                    handler=handler,
                    duration_seconds=duration_seconds,
                    metadata=metadata,
                )
                self._measurements[measurement_id] = measurement
                logger.debug(f"[{measurement_id}] Measurement registered in service")
            
            # Start the handler
            await measurement.start_handler()
            logger.info(f"[{measurement_id}] Measurement started successfully")
            
            return measurement_id
            
        except Exception as e:
            logger.error(f"[{measurement_id}] Failed to start measurement: {e}", exc_info=True)
            # Clean up if something went wrong
            async with self._lock:
                self._measurements.pop(measurement_id, None)
            raise
    
    async def stop_measurement(self, measurement_id: str) -> Dict[str, Any]:
        """
        Stop an active measurement.
        
        Args:
            measurement_id: ID of measurement to stop
            
        Returns:
            Measurement results
            
        Raises:
            ValueError: If measurement ID not found or not active
        """
        async with self._lock:
            if measurement_id not in self._measurements:
                logger.error(f"[{measurement_id}] Measurement not found")
                raise ValueError(f"Measurement '{measurement_id}' not found")
            
            measurement = self._measurements[measurement_id]
        
        if measurement.status != "active":
            logger.warning(
                f"[{measurement_id}] Cannot stop inactive measurement (status={measurement.status})"
            )
            raise ValueError(f"Measurement is not active (status={measurement.status})")
        
        logger.info(f"[{measurement_id}] Stopping measurement")
        results = await measurement.stop()
        return results
    
    def get_measurement_status(self, measurement_id: str) -> Measurement:
        """
        Get status of a measurement.
        
        Args:
            measurement_id: ID of measurement
            
        Returns:
            Measurement object
            
        Raises:
            ValueError: If measurement not found
        """
        if measurement_id not in self._measurements:
            logger.error(f"[{measurement_id}] Measurement not found for status query")
            raise ValueError(f"Measurement '{measurement_id}' not found")
        
        measurement = self._measurements[measurement_id]
        logger.debug(
            f"[{measurement_id}] Status query - status={measurement.status}, "
            f"duration={measurement.get_duration():.2f}s"
        )
        return measurement
    
    async def cleanup(self) -> None:
        """Clean up all measurements (useful for shutdown)."""
        logger.info(f"Cleaning up {len(self._measurements)} measurements")
        async with self._lock:
            for measurement_id, measurement in list(self._measurements.items()):
                if measurement.status == "active":
                    try:
                        logger.debug(f"[{measurement_id}] Force-stopping during cleanup")
                        await measurement.stop()
                    except Exception as e:
                        logger.error(f"[{measurement_id}] Error during cleanup: {e}")
