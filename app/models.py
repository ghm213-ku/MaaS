"""Pydantic models for API requests and responses."""
from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime


class MeasurementType(str, Enum):
    """Supported measurement types. Extensible for future types."""
    COUNT_RATE = "count_rate"
    SAVE_RAW_TAGS = "save_raw_tags"


class SaveRawTagsMetadata(BaseModel):
    """Metadata model for save-raw-tags measurements with required fields."""
    
    channel_list: list[int] = Field(
        description="List of channels to save raw tags from. Required."
    )
    target_file_path: str = Field(
        description="File path to save the raw tags data. Required."
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "channel_list": [1, 2, 3],
                "target_file_path": "C:\\Users\\s257050\\Desktop\\fileWriter"
            }
        }


class CountRateMeasurementRequest(BaseModel):
    """Request model for count-rate measurements."""
    
    measurement_type: MeasurementType = MeasurementType.COUNT_RATE
    duration_seconds: Optional[int] = Field(
        None,
        description="Optional: auto-stop after this many seconds. None = manual stop only"
    )
    metadata: Optional[dict[str, Any]] = Field(
        None,
        description="Optional: custom metadata for this measurement"
    )
    
    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "count_rate",
                "duration_seconds": 60,
                "metadata": {"detector_id": "det_001", "source": "lab_B"}
            }
        }

class SaveRawTagsMeasurmentRequest(BaseModel):
    """Request model for saving raw tags measurements."""

    measurement_type: MeasurementType = MeasurementType.SAVE_RAW_TAGS
    duration_seconds: int = Field(description="Duration in seconds to save raw tags")
    metadata: SaveRawTagsMetadata = Field(description="Metadata containing required channel_list and target_file_path")
    
    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "save_raw_tags",
                "duration_seconds": 60,
                "metadata": {
                    "channel_list": [1, 2, 3],
                    "target_file_path": "C:\\Users\\s257050\\Desktop\\fileWriter"
                }
            }
        }


class MeasurementResponse(BaseModel):
    """Response model for measurement operations."""
    
    measurement_id: str = Field(description="Unique identifier for this measurement")
    measurement_type: MeasurementType
    status: str = Field(description="Current status: 'active', 'completed', 'stopped'")
    started_at: datetime = Field(description="When the measurement started")
    message: str = Field(description="Status message")


class MeasurementStatusResponse(BaseModel):
    """Response model for measurement status queries."""
    
    measurement_id: str
    measurement_type: MeasurementType
    status: str
    started_at: datetime
    duration_so_far: float = Field(description="Duration in seconds since start")
    metadata: Optional[dict[str, Any]]
    results: Optional[dict[str, Any]] = Field(
        None,
        description="Preliminary results (if available)"
    )


class ErrorResponse(BaseModel):
    """Standard error response model."""
    
    error: str = Field(description="Error type")
    message: str = Field(description="Detailed error message")
    measurement_id: Optional[str] = Field(None, description="Related measurement ID if applicable")
