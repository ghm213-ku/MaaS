"""JSON payload definitions and schemas for different measurement types."""
from typing import Dict, Type, Any
from enum import Enum
from pydantic import BaseModel, Field
from app.models import CountRateMeasurementRequest


# ============================================================================
# Payload Schemas (JSON definitions)
# ============================================================================

class MeasurementPayloadSchemas:
    """Centralized storage for measurement payload schemas."""
    
    COUNT_RATE_SCHEMA = {
        "type": "object",
        "title": "Count-Rate Measurement Payload",
        "description": "Payload for starting a count-rate measurement",
        "properties": {
            "measurement_type": {
                "type": "string",
                "enum": ["count_rate"],
                "description": "Type of measurement",
            },
            "duration_seconds": {
                "type": "integer",
                "minimum": 1,
                "description": "Optional: auto-stop after this many seconds",
            },
            "metadata": {
                "type": "object",
                "description": "Optional: custom metadata for this measurement",
                "additionalProperties": True,
            },
        },
        "required": ["measurement_type"],
        "example": {
            "measurement_type": "count_rate",
            "duration_seconds": 60,
            "metadata": {"detector_id": "det_001", "location": "lab_B"},
        },
    }
    
    # Map of measurement type to schema
    SCHEMAS: Dict[str, Dict[str, Any]] = {
        "count_rate": COUNT_RATE_SCHEMA,
    }


# ============================================================================
# Measurement-Type to Pydantic Model Mapping
# ============================================================================

class MeasurementPayloadMapper:
    """Maps JSON payloads to appropriate Pydantic model classes."""
    
    # Registry: measurement_type -> Pydantic model class
    _PAYLOAD_MODELS: Dict[str, Type[BaseModel]] = {
        "count_rate": CountRateMeasurementRequest,
    }
    
    @classmethod
    def get_model_for_type(cls, measurement_type: str) -> Type[BaseModel]:
        """
        Get the appropriate Pydantic model class for a measurement type.
        
        Args:
            measurement_type: Type of measurement (e.g., 'count_rate')
            
        Returns:
            Pydantic model class for that measurement type
            
        Raises:
            ValueError: If measurement type is not registered
        """
        if measurement_type not in cls._PAYLOAD_MODELS:
            raise ValueError(
                f"Unknown measurement type: '{measurement_type}'. "
                f"Available types: {list(cls._PAYLOAD_MODELS.keys())}"
            )
        return cls._PAYLOAD_MODELS[measurement_type]
    
    @classmethod
    def validate_and_parse(cls, measurement_type: str, payload_dict: Dict[str, Any]) -> BaseModel:
        """
        Validate and parse a JSON payload to the appropriate Pydantic model.
        
        Args:
            measurement_type: Type of measurement
            payload_dict: Raw JSON payload as dictionary
            
        Returns:
            Validated Pydantic model instance
            
        Raises:
            ValueError: If measurement type is unknown
            ValidationError: If payload validation fails
        """
        model_class = cls.get_model_for_type(measurement_type)
        # Pydantic will validate and raise ValidationError if data is invalid
        return model_class(**payload_dict)
    
    @classmethod
    def register_model(cls, measurement_type: str, model_class: Type[BaseModel]) -> None:
        """
        Register a new measurement type with its Pydantic model.
        
        Args:
            measurement_type: Type identifier
            model_class: Pydantic model class for this type
        """
        cls._PAYLOAD_MODELS[measurement_type] = model_class
    
    @classmethod
    def list_types(cls) -> list[str]:
        """Get list of registered measurement types."""
        return list(cls._PAYLOAD_MODELS.keys())
    
    @classmethod
    def get_schema(cls, measurement_type: str) -> Dict[str, Any]:
        """
        Get JSON schema for a measurement type.
        
        Args:
            measurement_type: Type of measurement
            
        Returns:
            Schema dictionary
            
        Raises:
            ValueError: If type not found
        """
        if measurement_type not in MeasurementPayloadSchemas.SCHEMAS:
            raise ValueError(f"Schema not found for measurement type: {measurement_type}")
        return MeasurementPayloadSchemas.SCHEMAS[measurement_type]
    
    @classmethod
    def get_all_schemas(cls) -> Dict[str, Dict[str, Any]]:
        """Get all measurement schemas."""
        return MeasurementPayloadSchemas.SCHEMAS.copy()


# ============================================================================
# Helper Functions
# ============================================================================

def get_measurement_type_from_payload(payload_dict: Dict[str, Any]) -> str:
    """
    Extract measurement type from a JSON payload.
    
    Args:
        payload_dict: Raw JSON payload as dictionary
        
    Returns:
        Measurement type string
        
    Raises:
        ValueError: If measurement_type not in payload
    """
    if "measurement_type" not in payload_dict:
        raise ValueError("'measurement_type' field is required in payload")
    return payload_dict["measurement_type"]


def validate_payload_for_type(
    measurement_type: str,
    payload_dict: Dict[str, Any],
) -> BaseModel:
    """
    Validate a payload against the schema for a measurement type.
    
    Args:
        measurement_type: Type of measurement
        payload_dict: Raw JSON payload
        
    Returns:
        Validated Pydantic model instance
        
    Raises:
        ValueError: If type is unknown
        ValidationError: If payload is invalid
    """
    return MeasurementPayloadMapper.validate_and_parse(measurement_type, payload_dict)
