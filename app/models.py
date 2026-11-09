"""Pydantic models for API requests and responses."""

from enum import Enum
from typing import Any, Optional, Union
from pydantic import BaseModel, Field, model_validator
from datetime import datetime


class MeasurementType(str, Enum):
    """Supported measurement types. Extensible for future types."""
    COUNT_RATE = "count_rate"
    COUNT_RATE_LIVE = "count_rate_live"
    COINCIDENCES_LIVE = "coincidences_live"
    SAVE_RAW_TAGS = "save_raw_tags"
    CORRELATION = "correlation"
    COINCIDENCES = "coincidences"
    SET_PARAMETERS = "set_parameters"
    STARTSTOP_LIVE = "startstop_live"
    HISTOGRAM_LIVE = "histogram_live"
    CORRELATION_LIVE = "correlation_live"
    COINCIDENCE = "coincidence"
    COINCIDENCE_LIVE = "coincidence_live"


class CountRateMetadata(BaseModel):
    """Metadata model for count-rate measurements with required and optional fields."""

    channels: list[int] = Field(
        description="List of channel numbers to measure. Required."
    )
    user_name: str = Field(
        description="The user who booked the channels. Required."
    )
    binwidth: int = Field(
        default=int(1e9),
        description="Bin width in picoseconds for histogram. Default: 1e9 (1 second)",
    )
    n_values: int = Field(
        default=1,
        description="Number of bins in the histogram. Default: 1",
    )
    target_location: str = Field(
        default="desktop/MaasData/{datetime}/{measurement-type}",
        description="Target file path for saving results. Supports {datetime} and {measurement-type} placeholders",
    )
    refresh_rate: int = Field(
        default=25,
        description="Refresh rate in Hz for live measurements",
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
    user_name: str = Field(description="The user who booked the channels. Required.")
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
                "user_name": "abc-123-def",
                "binwidth": 1000000000,
                "n_values": 100,
                "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
            }
        }


class TimeHistogramLiveMetadata(BaseModel):
    """Base metadata model for live time histogram measurements (StartStop, Histogram)."""

    click_channel: int = Field(description="Click channel number. Required.")
    start_channel: int = Field(description="Start channel number. Required.")
    user_name: str = Field(description="The user who booked the channels. Required.")
    binwidth: int = Field(
        default=int(1e3),
        description="Bin width in picoseconds for histogram. Default: 1e3 (1 millisecond)",
    )
    n_bins: int = Field(
        default=1000,
        description="Number of bins in the histogram. Default: 1000",
    )
    refresh_rate: int = Field(
        default=25,
        description="Refresh rate in Hz for live measurements",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "click_channel": 1,
                "start_channel": 2,
                "user_name": "abc-123-def",
                "binwidth": 1000000,
                "n_bins": 1000,
                "refresh_rate": 25,
            }
        }

class StartStopLiveMetadata(TimeHistogramLiveMetadata):
    """Metadata model for live StartStop measurements."""
    pass

class HistogramLiveMetadata(TimeHistogramLiveMetadata):
    """Metadata model for live Histogram measurements."""
    pass

class CorrelationLiveMetadata(BaseModel):
    """Metadata model for live correlation measurements."""

    channel1: int = Field(description="First channel number to correlate. Required.")
    channel2: int = Field(description="Second channel number to correlate. Required.")
    user_name: str = Field(description="The user who booked the channels. Required.")
    binwidth: int = Field(
        default=int(1e3),
        description="Bin width in picoseconds for histogram. Default: 1e3",
    )
    n_bins: int = Field(
        default=1000,
        description="Number of bins in the histogram. Default: 1000",
    )
    refresh_rate: int = Field(
        default=25,
        description="Refresh rate in Hz for live measurements",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "channel1": 1,
                "channel2": 2,
                "user_name": "abc-123-def",
                "binwidth": 1000000,
                "n_bins": 1000,
                "refresh_rate": 25,
            }
        }



class CoincidencesMetadata(BaseModel):
    """Metadata model for coincidences measurements supporting multiple coincidence channel groups as a list of lists."""

    channels: Optional[list[list[int]]] = Field(
        default=...,
        description="List of lists of channel numbers (e.g., [[1, 2]], [[1, 2], [2, 3]]). Required.",
    )
    coincidences: Optional[list[list[int]]] = Field(
        default=None,
        description="List of lists of channel numbers representing multiple coincidences. E.g., [[1, 2]], [[1, 2], [2, 3, 5]].",
    )
    coincidence_groups: Optional[list[list[int]]] = Field(
        default=None,
        description="Alias for coincidences following Swabian API naming. List of lists of channel numbers.",
    )
    user_name: str = Field(
        description="The user who booked the channels. Required."
    )
    coincidence_window: int = Field(
        default=1000,
        description="Coincidence window in picoseconds. Default: 1000 (1 ns)",
    )
    timestamp: str = Field(
        default="Last",
        description="Timestamp assignment mode for the coincidence virtual channel ('Last', 'First', 'ListedFirst', 'Average'). Default: 'Last'",
    )
    binwidth: int = Field(
        default=int(1e9),
        description="Bin width in picoseconds for histogram. Default: 1e9 (1 second)",
    )
    n_values: int = Field(
        default=1,
        description="Number of bins in the histogram. Default: 1",
    )
    target_location: str = Field(
        default="desktop/MaasData/{datetime}/{measurement-type}",
        description="Target file path for saving results. Supports {datetime} and {measurement-type} placeholders",
    )
    refresh_rate: int = Field(
        default=25,
        description="Refresh rate in Hz for live measurements",
    )

    @model_validator(mode="before")
    @classmethod
    def validate_coincidences_input(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        data = data.copy()

        # Handle alias coincidenceWindow
        if "coincidenceWindow" in data and "coincidence_window" not in data:
            data["coincidence_window"] = data.pop("coincidenceWindow")

        raw_input = None
        if data.get("coincidences") is not None:
            raw_input = data["coincidences"]
        elif data.get("coincidence_groups") is not None:
            raw_input = data["coincidence_groups"]
        elif data.get("channels") is not None:
            raw_input = data["channels"]

        # If neither coincidences, coincidence_groups, nor channels was provided,
        # return data as-is so Pydantic's missing field validation runs for 'channels'.
        if raw_input is None:
            return data

        if not isinstance(raw_input, (list, tuple)):
            raise ValueError(
                "Coincidence input must be a list of lists of channel numbers (e.g. [[1, 2], [2, 3]]). "
                "Simple 1D channel lists are deprecated and no longer supported."
            )

        if len(raw_input) == 0:
            raise ValueError(
                "Coincidence measurement requires a non-empty list of lists of channel numbers (e.g. coincidences=[[1, 2], [2, 3]])."
            )

        # Deprecate simple 1D lists: reject if any item is not a list or tuple of channels
        if any(isinstance(item, (int, float, str, bool)) or not isinstance(item, (list, tuple)) for item in raw_input):
            raise ValueError(
                "Simple 1D channel lists for coincidence are deprecated and no longer supported. "
                "Coincidence input must be a list of lists of channel numbers (e.g., [[1, 2]] instead of [1, 2])."
            )

        # Validate each coincidence group
        normalized_groups = []
        for i, group in enumerate(raw_input):
            if not isinstance(group, (list, tuple)):
                raise ValueError(
                    f"Coincidence group at index {i} must be a list of channel numbers, got {type(group).__name__}."
                )
            if len(group) < 2:
                raise ValueError(
                    f"Coincidence group at index {i} ({group}) must contain at least 2 channels."
                )
            for ch in group:
                if not isinstance(ch, int) or isinstance(ch, bool):
                    raise ValueError(
                        f"Channel number {ch} in coincidence group {group} must be an integer."
                    )
            normalized_groups.append([int(ch) for ch in group])

        data["coincidences"] = normalized_groups
        data["coincidence_groups"] = normalized_groups
        data["channels"] = normalized_groups

        return data

    @property
    def unique_channels(self) -> list[int]:
        """Return sorted unique list of channel integers involved in all coincidences."""
        groups = self.coincidences or []
        unique = set()
        for group in groups:
            unique.update(group)
        return sorted(list(unique))

    class Config:
        json_schema_extra = {
            "example": {
                "coincidences": [[1, 2], [2, 3, 5]],
                "coincidence_window": 1000,
                "timestamp": "Last",
                "binwidth": 1000000000,
                "n_values": 1,
                "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
                "refresh_rate": 25,
            }
        }


class SaveRawTagsMetadata(BaseModel):
    """Metadata model for save-raw-tags measurements with required fields."""

    channel_list: list[int] = Field(
        description="List of channels to save raw tags from. Required."
    )
    user_name: str = Field(
        description="The user who booked the channels. Required."
    )
    target_file_path: str = Field(
        description="File path to save the raw tags data. Required."
    )

    class Config:
        json_schema_extra = {
            "example": {
                "channel_list": [1, 2, 3],
                "user_name": "abc-123-def",
                "target_file_path": "C:\\Users\\s257050\\Desktop\\fileWriter",
            }
        }


class SetParametersMetadata(BaseModel):
    """Metadata model for setting parameters with required and optional fields."""

    channels: list[int] = Field(
        description="List of channel numbers to configure. Required."
    )
    user_name: str = Field(
        description="The user who booked the channels. Required."
    )
    input_delay: Optional[int] = Field(
        default=None,
        description="Input delay in picoseconds",
    )
    trigger_voltage: Optional[float] = Field(
        default=None,
        description="Trigger voltage in volts",
    )

    class Config:
        json_schema_extra = {
            "example": {
                "channels": [1, 2],
                "user_name": "abc-123-def",
                "input_delay": 1000,
                "trigger_voltage": 0.5,
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

    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            duration_seconds = data.pop("duration_seconds", 60)
            measurement_type = data.pop("measurement_type", MeasurementType.COUNT_RATE)
            return {
                "measurement_type": measurement_type,
                "duration_seconds": duration_seconds,
                "metadata": data,
            }
        return data

    @property
    def channels(self) -> list[int]:
        return self.metadata.channels

    @property
    def user_name(self) -> str:
        return self.metadata.user_name

    @property
    def binwidth(self) -> int:
        return self.metadata.binwidth

    @property
    def n_values(self) -> int:
        return self.metadata.n_values

    @property
    def target_location(self) -> str:
        return self.metadata.target_location

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "count_rate",
                "duration_seconds": 60,
                "metadata": {
                    "channels": [1, 2, 3],
                    "user_name": "abc-123-def",
                    "binwidth": 1000000000,
                    "n_values": 1,
                    "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
                },
            }
        }


class CountRateLiveMeasurementRequest(BaseModel):
    """Request model for live count-rate measurements."""

    measurement_type: MeasurementType = MeasurementType.COUNT_RATE_LIVE
    metadata: CountRateMetadata = Field(
        description="Metadata containing channels, binwidth, and n_values"
    )

    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            # For backward compatibility, drop duration_seconds if present
            data.pop("duration_seconds", None)
            measurement_type = data.pop("measurement_type", MeasurementType.COUNT_RATE_LIVE)
            return {
                "measurement_type": measurement_type,
                "metadata": data,
            }
        return data

    @property
    def channels(self) -> list[int]:
        return self.metadata.channels

    @property
    def user_name(self) -> str:
        return self.metadata.user_name

    @property
    def binwidth(self) -> int:
        return self.metadata.binwidth

    @property
    def n_values(self) -> int:
        return self.metadata.n_values

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "count_rate_live",
                "metadata": {
                    "channels": [1, 2, 3],
                    "user_name": "abc-123-def",
                    "binwidth": 1000000000,
                    "n_values": 1,
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

    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            duration_seconds = data.pop("duration_seconds", 60)
            measurement_type = data.pop("measurement_type", MeasurementType.CORRELATION)
            return {
                "measurement_type": measurement_type,
                "duration_seconds": duration_seconds,
                "metadata": data,
            }
        return data

    @property
    def channel1(self) -> int:
        return self.metadata.channel1

    @property
    def channel2(self) -> int:
        return self.metadata.channel2

    @property
    def user_name(self) -> str:
        return self.metadata.user_name

    @property
    def binwidth(self) -> int:
        return self.metadata.binwidth

    @property
    def n_values(self) -> int:
        return self.metadata.n_values

    @property
    def target_location(self) -> str:
        return self.metadata.target_location

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "correlation",
                "duration_seconds": 60,
                "metadata": {
                    "channel1": 1,
                    "channel2": 2,
                    "user_name": "abc-123-def",
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

    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            duration_seconds = data.pop("duration_seconds", 60)
            measurement_type = data.pop("measurement_type", MeasurementType.COINCIDENCES)
            return {
                "measurement_type": measurement_type,
                "duration_seconds": duration_seconds,
                "metadata": data,
            }
        return data

    @property
    def channels(self) -> list[list[int]]:
        return self.metadata.channels or []

    @property
    def coincidences(self) -> list[list[int]]:
        return self.metadata.coincidences or []

    @property
    def coincidence_groups(self) -> list[list[int]]:
        return self.metadata.coincidence_groups or []

    @property
    def unique_channels(self) -> list[int]:
        return self.metadata.unique_channels

    @property
    def coincidence_window(self) -> int:
        return self.metadata.coincidence_window

    @property
    def user_name(self) -> str:
        return self.metadata.user_name

    @property
    def binwidth(self) -> int:
        return self.metadata.binwidth

    @property
    def n_values(self) -> int:
        return self.metadata.n_values

    @property
    def target_location(self) -> str:
        return self.metadata.target_location

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "coincidences",
                "duration_seconds": 60,
                "metadata": {
                    "coincidences": [[1, 2], [2, 3, 5]],
                    "user_name": "abc-123-def",
                    "coincidence_window": 1000,
                    "binwidth": 1000000000,
                    "n_values": 1,
                    "target_location": "desktop/MaasData/{datetime}/{measurement-type}",
                },
            }
        }


class CoincidencesLiveMeasurementRequest(BaseModel):
    """Request model for live coincidences measurements."""

    measurement_type: MeasurementType = MeasurementType.COINCIDENCES_LIVE
    metadata: CoincidencesMetadata = Field(
        description="Metadata containing channels, binwidth, and n_values"
    )

    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            # Drop duration_seconds if present for backward compatibility
            data.pop("duration_seconds", None)
            measurement_type = data.pop("measurement_type", MeasurementType.COINCIDENCES_LIVE)
            return {
                "measurement_type": measurement_type,
                "metadata": data,
            }
        return data

    @property
    def channels(self) -> list[list[int]]:
        return self.metadata.channels or []

    @property
    def coincidences(self) -> list[list[int]]:
        return self.metadata.coincidences or []

    @property
    def coincidence_groups(self) -> list[list[int]]:
        return self.metadata.coincidence_groups or []

    @property
    def unique_channels(self) -> list[int]:
        return self.metadata.unique_channels

    @property
    def coincidence_window(self) -> int:
        return self.metadata.coincidence_window

    @property
    def user_name(self) -> str:
        return self.metadata.user_name

    @property
    def binwidth(self) -> int:
        return self.metadata.binwidth

    @property
    def n_values(self) -> int:
        return self.metadata.n_values

    @property
    def target_location(self) -> str:
        return self.metadata.target_location

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "coincidences_live",
                "metadata": {
                    "coincidences": [[1, 2], [2, 3, 5]],
                    "user_name": "abc-123-def",
                    "coincidence_window": 1000,
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

    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            duration_seconds = data.pop("duration_seconds", 60)
            measurement_type = data.pop("measurement_type", MeasurementType.SAVE_RAW_TAGS)
            return {
                "measurement_type": measurement_type,
                "duration_seconds": duration_seconds,
                "metadata": data,
            }
        return data

    @property
    def channel_list(self) -> list[int]:
        return self.metadata.channel_list

    @property
    def user_name(self) -> str:
        return self.metadata.user_name

    @property
    def target_file_path(self) -> str:
        return self.metadata.target_file_path

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "save_raw_tags",
                "duration_seconds": 60,
                "metadata": {
                    "channel_list": [1, 2, 3],
                    "user_name": "abc-123-def",
                    "target_file_path": "C:\\Users\\s257050\\Desktop\\fileWriter",
                },
            }
        }


class SetParametersRequest(BaseModel):
    """Request model for setting parameters."""

    measurement_type: MeasurementType = MeasurementType.SET_PARAMETERS
    duration_seconds: int = Field(
        default=0, description="Duration in seconds (typically 0 for immediate application)"
    )
    metadata: SetParametersMetadata = Field(
        description="Metadata containing channels, user_name, input_delay, and trigger_voltage"
    )

    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            duration_seconds = data.pop("duration_seconds", 0)
            measurement_type = data.pop("measurement_type", MeasurementType.SET_PARAMETERS)
            return {
                "measurement_type": measurement_type,
                "duration_seconds": duration_seconds,
                "metadata": data,
            }
        return data

    @property
    def channels(self) -> list[int]:
        return self.metadata.channels

    @property
    def user_name(self) -> str:
        return self.metadata.user_name

    @property
    def input_delay(self) -> Optional[int]:
        return self.metadata.input_delay

    @property
    def trigger_voltage(self) -> Optional[float]:
        return self.metadata.trigger_voltage

    class Config:
        json_schema_extra = {
            "example": {
                "measurement_type": "set_parameters",
                "duration_seconds": 0,
                "metadata": {
                    "channels": [1, 2],
                    "user_name": "abc-123-def",
                    "input_delay": 1000,
                    "trigger_voltage": 0.5,
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
    user_name: Optional[str] = Field(
        None, description="Who booked the channel (user identifier)"
    )
    booking_time: Optional[str] = Field(
        None, description="ISO timestamp of when booked"
    )


class ChannelBookRequest(BaseModel):
    """Request to book channels."""

    user_name: str = Field(
        description="Who is booking the channels; must be the authenticated caller's username"
    )
    channel_numbers: list[int] = Field(
        description="List of channel numbers to book (e.g., [1, 2, 3] or [101, 102])"
    )

    @model_validator(mode="before")
    @classmethod
    def handle_channels_alias(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "channels" in data and "channel_numbers" not in data:
                data = data.copy()
                data["channel_numbers"] = data.pop("channels")
        return data

    @property
    def channels(self) -> list[int]:
        return self.channel_numbers

    class Config:
        json_schema_extra = {
            "example": {"user_name": "abc-123-def", "channel_numbers": [1, 2, 3]}
        }


class ChannelBookResponse(BaseModel):
    """Response after booking channels."""

    user_name: str
    booked_channels: list[int]
    booking_time: str
    total_booked: int


class ChannelReleaseRequest(BaseModel):
    """Body for a channel release: which of the user's channels to free."""

    channel_numbers: list[int] = Field(
        ...,
        min_length=1,
        description=(
            "Channel numbers to release (e.g., [1, 2]). All must be booked by the "
            "user; otherwise nothing is released."
        ),
    )

    @model_validator(mode="before")
    @classmethod
    def handle_channels_alias(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "channels" in data and "channel_numbers" not in data:
                data = data.copy()
                data["channel_numbers"] = data.pop("channels")
        return data

    class Config:
        json_schema_extra = {"example": {"channel_numbers": [1, 2]}}


class ChannelReleaseResponse(BaseModel):
    """Response after releasing channels."""

    user_name: str
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
    user_names: dict[str, list[int]] = Field(
        description="Mapping of user_name identifier to channel lists"
    )

class StartStopLiveMeasurementRequest(BaseModel):
    measurement_type: MeasurementType = MeasurementType.STARTSTOP_LIVE
    metadata: StartStopLiveMetadata = Field(description="Metadata containing channels, binwidth, n_bins")
    
    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            data.pop("duration_seconds", None)
            measurement_type = data.pop("measurement_type", MeasurementType.STARTSTOP_LIVE)
            return {"measurement_type": measurement_type, "metadata": data}
        return data

    @property
    def channels(self) -> list[int]:
        return [self.metadata.click_channel, self.metadata.start_channel]

    @property
    def user_name(self) -> str:
        return self.metadata.user_name

class HistogramLiveMeasurementRequest(BaseModel):
    measurement_type: MeasurementType = MeasurementType.HISTOGRAM_LIVE
    metadata: HistogramLiveMetadata = Field(description="Metadata containing channels, binwidth, n_bins")
    
    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            data.pop("duration_seconds", None)
            measurement_type = data.pop("measurement_type", MeasurementType.HISTOGRAM_LIVE)
            return {"measurement_type": measurement_type, "metadata": data}
        return data

    @property
    def channels(self) -> list[int]:
        return [self.metadata.click_channel, self.metadata.start_channel]

    @property
    def user_name(self) -> str:
        return self.metadata.user_name

class CorrelationLiveMeasurementRequest(BaseModel):
    measurement_type: MeasurementType = MeasurementType.CORRELATION_LIVE
    metadata: CorrelationLiveMetadata = Field(description="Metadata containing channels, binwidth, n_bins")
    
    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if isinstance(data, dict) and "metadata" not in data:
            data.pop("duration_seconds", None)
            measurement_type = data.pop("measurement_type", MeasurementType.CORRELATION_LIVE)
            return {"measurement_type": measurement_type, "metadata": data}
        return data

    @property
    def channels(self) -> list[int]:
        return [self.metadata.channel1, self.metadata.channel2]

    @property
    def user_name(self) -> str:
        return self.metadata.user_name


# Aliases for singular coincidence terminology
CoincidenceMetadata = CoincidencesMetadata
CoincidenceMeasurementRequest = CoincidencesMeasurementRequest
CoincidenceLiveMeasurementRequest = CoincidencesLiveMeasurementRequest
