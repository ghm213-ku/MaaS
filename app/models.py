"""Pydantic models for API requests and responses."""

from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel, Field
from datetime import datetime


class MeasurementType(str, Enum):
    """Supported measurement types. Extensible for future types."""

    COUNT_RATE = "count_rate"
    SAVE_RAW_TAGS = "save_raw_tags"
    CORRELATION = "correlation"
    COINCIDENCES = "coincidences"


class CountRateMetadata(BaseModel):
    """Metadata model for count-rate measurements with required and optional fields."""

    channels: list[int] = Field(
        description="List of channel numbers to measure. Required."
    )
    binwidth: int = Field(
        default=int(1e9),
        description="Bin width in picoseconds for histogram. Default: 1e9 (1 second)",
    )
    n_values: int = Field(
        default=100,
        description="Number of bins in the histogram. Default: 1",
    )
    target_location: str = Field(
        default="desktop/MaasData/{datetime}/{measurement-type}",
        description="Target file path for saving results. Supports {datetime} and {measurement-type} placeholders",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "channels": [1, 2, 3],
                "binwidth": 1000000000,
                "n_values": 1,
                "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
            }
        }


class CorrelationMetadata(BaseModel):
    """Metadata model for correlation measurements with required and optional fields."""

    channel1: int = Field(description="First channel number to correlate. Required.")
    channel2: int = Field(description="Second channel number to correlate. Required.")
    binwidth: int = Field(
        default=int(1e3),
        description="Bin width in picoseconds for histogram. Default: 1e3 (1 millisecond)",
    )
    n_values: int = Field(
        default=1000,
        description="Number of bins in the histogram. Default: 1000",
    )
    target_location: str = Field(
        default="desktop/MaasData/{datetime}/{measurement-type}",
        description="Target file path for saving results. Supports {datetime} and {measurement-type} placeholders",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "channel1": 1,
                "channel2": 2,
                "binwidth": 1000000000,
                "n_values": 100,
                "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
            }
        }


class CoincidencesMetadata(BaseModel):
    """Metadata model for coincidences measurements with required and optional fields."""

    channels: list[int] = Field(
        description="List of channel numbers to measure. Required."
    )
    binwidth: int = Field(
        default=int(1e9),
        description="Bin width in picoseconds for histogram. Default: 1e9 (1 second)",
    )
    n_values: int = Field(
        default=100,
        description="Number of bins in the histogram. Default: 1",
    )
    target_location: str = Field(
        default="desktop/MaasData/{datetime}/{measurement-type}",
        description="Target file path for saving results. Supports {datetime} and {measurement-type} placeholders",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "channels": [1, 2, 3],
                "binwidth": 1000000000,
                "n_values": 1,
                "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
            }
        }


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
                "target_file_path": "C:\\Users\\s257050\\Desktop\\fileWriter",
            }
        }


class CountRateMeasurementRequest(BaseModel):
    """Request model for count-rate measurements."""

    measurement_type: MeasurementType = MeasurementType.COUNT_RATE
    duration_seconds: int = Field(
        description="Duration in seconds for the count-rate measurement"
    )
    metadata: CountRateMetadata = Field(
        description="Metadata containing channels, binwidth, n_values, and target_location"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "count_rate",
                "duration_seconds": 60,
                "metadata": {
                    "channels": [1, 2, 3],
                    "binwidth": 1000000000,
                    "n_values": 1,
                    "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
                },
            }
        }


class CorrelationMeasurementRequest(BaseModel):
    """Request model for correlation measurements."""

    measurement_type: MeasurementType = MeasurementType.CORRELATION
    duration_seconds: int = Field(
        description="Duration in seconds for the correlation measurement"
    )
    metadata: CorrelationMetadata = Field(
        description="Metadata containing channel1, channel2, binwidth, n_values, and target_location"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "correlation",
                "duration_seconds": 60,
                "metadata": {
                    "channel1": 1,
                    "channel2": 2,
                    "binwidth": 1000000000,
                    "n_values": 100,
                    "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
                },
            }
        }


class CoincidencesMeasurementRequest(BaseModel):
    """Request model for coincidences measurements."""

    measurement_type: MeasurementType = MeasurementType.COINCIDENCES
    duration_seconds: int = Field(
        description="Duration in seconds for the coincidences measurement"
    )
    metadata: CoincidencesMetadata = Field(
        description="Metadata containing channels, binwidth, n_values, and target_location"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "coincidences",
                "duration_seconds": 60,
                "metadata": {
                    "channels": [1, 2, 3],
                    "binwidth": 1000000000,
                    "n_values": 1,
                    "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
                },
            }
        }


class SaveRawTagsMeasurmentRequest(BaseModel):
    """Request model for saving raw tags measurements."""

    measurement_type: MeasurementType = MeasurementType.SAVE_RAW_TAGS
    duration_seconds: int = Field(description="Duration in seconds to save raw tags")
    metadata: SaveRawTagsMetadata = Field(
        description="Metadata containing required channel_list and target_file_path"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "save_raw_tags",
                "duration_seconds": 60,
                "metadata": {
                    "channel_list": [1, 2, 3],
                    "target_file_path": "C:\\Users\\s257050\\Desktop\\fileWriter",
                },
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
        None, description="Preliminary results (if available)"
    )


class ErrorResponse(BaseModel):
    """Standard error response model."""

    error: str = Field(description="Error type")
    message: str = Field(description="Detailed error message")
    measurement_id: Optional[str] = Field(
        None, description="Related measurement ID if applicable"
    )


# Channel Management Models


class ChannelInfo(BaseModel):
    """Information about a single channel."""

    channel_number: int = Field(
        description="Channel number (1-16, 101-116, or 201-216)"
    )
    status: str = Field(description="Channel status: 'available' or 'booked'")
    booked_by: Optional[str] = Field(
        None, description="Who booked the channel (measurement_id or user identifier)"
    )
    booking_time: Optional[str] = Field(
        None, description="ISO timestamp of when booked"
    )


class ChannelBookRequest(BaseModel):
    """Request to book channels."""

    booked_by: str = Field(
        description="Who is booking the channels (measurement_id or user identifier)"
    )
    channel_numbers: list[int] = Field(
        description="List of channel numbers to book (e.g., [1, 2, 3] or [101, 102])"
    )

    class Config:
        json_schema_extra = {
            "example": {"booked_by": "abc-123-def", "channel_numbers": [1, 2, 3]}
        }


class ChannelBookResponse(BaseModel):
    """Response after booking channels."""

    booked_by: str
    booked_channels: list[int]
    booking_time: str
    total_booked: int


class ChannelReleaseResponse(BaseModel):
    """Response after releasing channels."""

    booked_by: str
    released_channels: list[int]
    total_released: int


class ChannelListResponse(BaseModel):
    """Response containing list of channels."""

    channels: list[ChannelInfo]
    total_channels: int
    available_channels: int
    booked_channels: int


class ChannelStatsResponse(BaseModel):
    """Response with channel statistics."""

    total_channels: int
    available_channels: int
    booked_channels: int
    utilization_percent: float
    available_channel_numbers: list[int] = Field(
        description="List of available channel numbers"
    )
    booked_by_identifier: dict[str, list[int]] = Field(
        description="Mapping of booked_by identifier to channel lists"
    )
