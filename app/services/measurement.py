"""Base measurement handler interface."""
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import logging
import asyncio
import uuid
from datetime import datetime


class MeasurementHandler(ABC):
    """Abstract base class for measurement handlers."""
    
    def __init__(self, tagger=None):
        """Initialize the measurement handler.
        
        Args:
            tagger: Optional hardware interface (e.g., TimeTagger)
        """
        self.tagger = tagger
        self.logger = logging.getLogger(self.__class__.__name__)
        self.is_running = False
    
    @abstractmethod
    async def start(self, duration_seconds: float, metadata: Dict[str, Any]) -> None:
        """Start the measurement.
        
        Args:
            duration_seconds: Duration of measurement in seconds
            metadata: Measurement-specific metadata
        """
        pass
    
    @abstractmethod
    async def stop(self) -> Dict[str, Any]:
        """Stop the measurement and return results.
        
        Returns:
            Dictionary with measurement results
        """
        pass


class Measurement:
    """Represents a single measurement instance."""
    
    def __init__(
        self,
        measurement_id: str,
        measurement_type: str,
        handler: MeasurementHandler,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Initialize a measurement.
        
        Args:
            measurement_id: Unique identifier for this measurement
            measurement_type: Type of measurement (e.g., 'mock', 'count-rate')
            handler: Handler instance for this measurement
            duration_seconds: Optional duration for auto-stop
            metadata: Optional metadata to pass to handler
        """
        self.measurement_id = measurement_id
        self.measurement_type = measurement_type
        self.handler = handler
        self.duration_seconds = duration_seconds
        self.metadata = metadata or {}
        
        self.status = "active"
        self.started_at = datetime.now()
        self.stopped_at: Optional[datetime] = None
        self.results: Optional[Dict[str, Any]] = None
        
        self.duration_task: Optional[asyncio.Task] = None
    
    async def start_handler(self) -> None:
        """Start the handler and set up auto-stop if needed."""
        try:
            await self.handler.start(self.duration_seconds, self.metadata)
            
            # Set up auto-stop timer if duration is specified
            if self.duration_seconds:
                self.duration_task = asyncio.create_task(
                    self._auto_stop_timer()
                )
        except Exception as e:
            self.status = "error"
            raise
    
    async def _auto_stop_timer(self) -> None:
        """Automatically stop measurement after duration."""
        try:
            await asyncio.sleep(self.duration_seconds)
            if self.status == "active":
                await self.stop()
        except asyncio.CancelledError:
            pass
    
    async def stop(self) -> Dict[str, Any]:
        """Stop the measurement and collect results."""
        if self.status != "active":
            # Return cached results if already stopped
            return self.results or {}
        
        # Cancel auto-stop timer if running
        if self.duration_task and not self.duration_task.done():
            self.duration_task.cancel()
            try:
                await self.duration_task
            except asyncio.CancelledError:
                pass
        
        # Call handler stop and collect results
        self.results = await self.handler.stop()
        self.status = "stopped"
        self.stopped_at = datetime.now()
        
        return self.results
    
    def get_duration(self) -> float:
        """Get elapsed duration in seconds."""
        end_time = self.stopped_at or datetime.now()
        return (end_time - self.started_at).total_seconds()


class MeasurementService:
    """Service to manage multiple concurrent measurements."""
    
    def __init__(self):
        """Initialize the measurement service."""
        self._handlers: Dict[str, type] = {}
        self._measurements: Dict[str, Measurement] = {}
        self.logger = logging.getLogger(self.__class__.__name__)
    
    def register_handler(self, measurement_type: str, handler_class: type) -> None:
        """Register a measurement handler class.
        
        Args:
            measurement_type: Name of the measurement type
            handler_class: Handler class (not instance)
        """
        self._handlers[measurement_type] = handler_class
        self.logger.info(f"Registered handler for type: {measurement_type}")
    
    async def start_measurement(
        self,
        measurement_type: str,
        duration_seconds: Optional[float] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Start a new measurement.
        
        Args:
            measurement_type: Type of measurement
            duration_seconds: Optional duration for auto-stop
            metadata: Optional metadata for the measurement
        
        Returns:
            Measurement ID
        
        Raises:
            ValueError: If measurement type is unknown
        """
        if measurement_type not in self._handlers:
            raise ValueError(f"Unknown measurement type: {measurement_type}")
        
        # Create new measurement instance
        measurement_id = str(uuid.uuid4())
        handler_class = self._handlers[measurement_type]
        handler = handler_class()
        
        measurement = Measurement(
            measurement_id=measurement_id,
            measurement_type=measurement_type,
            handler=handler,
            duration_seconds=duration_seconds,
            metadata=metadata,
        )
        
        # Store measurement
        self._measurements[measurement_id] = measurement
        
        try:
            # Start the handler
            await measurement.start_handler()
            self.logger.info(f"Started measurement: {measurement_id}")
        except Exception as e:
            # Clean up on failure
            del self._measurements[measurement_id]
            raise
        
        return measurement_id
    
    def get_measurement_status(self, measurement_id: str) -> Measurement:
        """Get the status of a measurement.
        
        Args:
            measurement_id: ID of the measurement
        
        Returns:
            Measurement object
        
        Raises:
            ValueError: If measurement not found
        """
        if measurement_id not in self._measurements:
            raise ValueError(f"Measurement {measurement_id} not found")
        
        return self._measurements[measurement_id]
    
    async def stop_measurement(self, measurement_id: str) -> Dict[str, Any]:
        """Stop a measurement.
        
        Args:
            measurement_id: ID of the measurement to stop
        
        Returns:
            Measurement results
        
        Raises:
            ValueError: If measurement not found or not active
        """
        if measurement_id not in self._measurements:
            raise ValueError(f"Measurement {measurement_id} not found")
        
        measurement = self._measurements[measurement_id]
        
        if measurement.status != "active":
            raise ValueError(f"Measurement {measurement_id} is not active")
        
        results = await measurement.stop()
        self.logger.info(f"Stopped measurement: {measurement_id}")
        
        return results
    
    async def cleanup(self) -> None:
        """Stop all active measurements and clean up."""
        measurement_ids = list(self._measurements.keys())
        
        for measurement_id in measurement_ids:
            measurement = self._measurements[measurement_id]
            if measurement.status == "active":
                try:
                    await measurement.stop()
                except Exception as e:
                    self.logger.error(
                        f"Error cleaning up measurement {measurement_id}: {e}"
                    )
        
        self.logger.info("Measurement service cleanup complete")

