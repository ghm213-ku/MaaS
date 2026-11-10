"""Request and response models for measurements and set-parameters.

Every measurement request has the same shape::

    {"measurement_type": ..., "duration_seconds": ..., "metadata": {...}}

The metadata model holds the measurement's own settings; the worker validates
the queued metadata against it again before running the job.
"""

from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# Default results folder: the worker user's Desktop ("~" is expanded when the
# job runs), not a "desktop" folder under the worker's working directory.
DEFAULT_TARGET_LOCATION = "~/Desktop/MaasData/{datetime}/{measurement-type}"

TARGET_LOCATION_HELP = (
    "Target file path for saving results. Supports {datetime} and {measurement-type} placeholders"
)
REFRESH_RATE_HELP = "Refresh rate in Hz for live measurements"
USER_NAME_HELP = "The user who booked the channels. Required."
LIVE_DURATION_HELP = (
    "Optional acquisition time in seconds. When set, the counter runs for "
    "exactly this long (Time Tagger startFor), a last update flagged "
    "\"final\": true is published, and the job completes. Omit to stream "
    "until stopped."
)

COINCIDENCE_TIMESTAMPS = ("Last", "First", "ListedFirst", "Average")


class MeasurementType(str, Enum):
    """Measurement types; each has a request model (REQUEST_MODELS) and a worker handler."""

    COUNT_RATE = "count_rate"
    COUNT_RATE_LIVE = "count_rate_live"
    CORRELATION = "correlation"
    CORRELATION_LIVE = "correlation_live"
    COINCIDENCES = "coincidences"
    COINCIDENCES_LIVE = "coincidences_live"
    COINCIDENCE = "coincidence"  # alias of COINCIDENCES
    COINCIDENCE_LIVE = "coincidence_live"  # alias of COINCIDENCES_LIVE
    STARTSTOP_LIVE = "startstop_live"
    HISTOGRAM_LIVE = "histogram_live"
    SAVE_RAW_TAGS = "save_raw_tags"
    SET_PARAMETERS = "set_parameters"


# ============================================================================
# Metadata models (the "metadata" object of each request)
# ============================================================================


class CountRateMetadata(BaseModel):
    """Settings of a count-rate measurement (TimeTagger Counter)."""

    channels: list[int] = Field(description="List of channel numbers to measure. Required.")
    user_name: str = Field(description=USER_NAME_HELP)
    binwidth: int = Field(default=int(1e9), description="Bin width in picoseconds. Default: 1e9 (1 second)")
    n_values: int = Field(default=1, description="Number of bins. Default: 1")
    target_location: str = Field(default=DEFAULT_TARGET_LOCATION, description=TARGET_LOCATION_HELP)
    refresh_rate: int = Field(default=25, description=REFRESH_RATE_HELP)

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "channels": [1, 2, 3],
            "user_name": "abc-123-def",
            "binwidth": 1000000000,
            "n_values": 1,
            "target_location": DEFAULT_TARGET_LOCATION,
        }
    })


class CorrelationMetadata(BaseModel):
    """Settings of a correlation measurement (TimeTagger Correlation)."""

    channel1: int = Field(description="First channel number to correlate. Required.")
    channel2: int = Field(description="Second channel number to correlate. Required.")
    user_name: str = Field(description=USER_NAME_HELP)
    binwidth: int = Field(default=int(1e3), description="Bin width in picoseconds. Default: 1e3 (1 ns)")
    n_values: int = Field(
        default=1000,
        description="Number of bins (TimeTagger's n_bins; 'n_bins' is accepted too). Default: 1000",
    )
    target_location: str = Field(default=DEFAULT_TARGET_LOCATION, description=TARGET_LOCATION_HELP)

    @model_validator(mode="before")
    @classmethod
    def accept_n_bins(cls, data: Any) -> Any:
        """Accept TimeTagger's name 'n_bins' (also used by /correlation-live)."""
        if isinstance(data, dict) and "n_bins" in data and "n_values" not in data:
            data = data.copy()
            data["n_values"] = data.pop("n_bins")
        return data

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "channel1": 1,
            "channel2": 2,
            "user_name": "abc-123-def",
            "binwidth": 1000000000,
            "n_values": 100,
            "target_location": DEFAULT_TARGET_LOCATION,
        }
    })


class CorrelationLiveMetadata(BaseModel):
    """Settings of a live correlation measurement."""

    channel1: int = Field(description="First channel number to correlate. Required.")
    channel2: int = Field(description="Second channel number to correlate. Required.")
    user_name: str = Field(description=USER_NAME_HELP)
    binwidth: int = Field(default=int(1e3), description="Bin width in picoseconds. Default: 1e3")
    n_bins: int = Field(default=1000, description="Number of bins. Default: 1000")
    refresh_rate: int = Field(default=25, description=REFRESH_RATE_HELP)

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "channel1": 1,
            "channel2": 2,
            "user_name": "abc-123-def",
            "binwidth": 1000000,
            "n_bins": 1000,
            "refresh_rate": 25,
        }
    })


class TimeHistogramLiveMetadata(BaseModel):
    """Settings shared by the live StartStop and Histogram measurements."""

    click_channel: int = Field(description="Click (stop) channel number. Required.")
    start_channel: int = Field(description="Start channel number. Required.")
    user_name: str = Field(description=USER_NAME_HELP)
    binwidth: int = Field(default=int(1e3), description="Bin width in picoseconds. Default: 1e3 (1 ns)")
    refresh_rate: int = Field(default=25, description=REFRESH_RATE_HELP)


class StartStopLiveMetadata(TimeHistogramLiveMetadata):
    """Settings of a live StartStop measurement.

    TimeTagger's StartStop has no bin count: its range grows to the largest
    time difference seen, and it returns only non-empty bins.
    """

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "click_channel": 1,
            "start_channel": 2,
            "user_name": "abc-123-def",
            "binwidth": 1000000,
            "refresh_rate": 25,
        }
    })


class HistogramLiveMetadata(TimeHistogramLiveMetadata):
    """Settings of a live Histogram measurement."""

    n_bins: int = Field(default=1000, description="Number of bins. Default: 1000")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "click_channel": 1,
            "start_channel": 2,
            "user_name": "abc-123-def",
            "binwidth": 1000000,
            "n_bins": 1000,
            "refresh_rate": 25,
        }
    })


class CoincidencesMetadata(BaseModel):
    """Settings of a coincidences measurement: one or more groups of channels.

    The groups can be given as ``coincidences``, ``coincidence_groups`` (Swabian
    naming) or ``channels``; after validation all three hold the same list.
    """

    channels: Optional[list[list[int]]] = Field(
        default=...,
        description="List of lists of channel numbers (e.g., [[1, 2]], [[1, 2], [2, 3]]). Required.",
    )
    coincidences: Optional[list[list[int]]] = Field(
        default=None,
        description="List of lists of channel numbers, one per coincidence group. E.g., [[1, 2]], [[1, 2], [2, 3, 5]].",
    )
    coincidence_groups: Optional[list[list[int]]] = Field(
        default=None,
        description="Alias for coincidences following Swabian API naming.",
    )
    user_name: str = Field(description=USER_NAME_HELP)
    coincidence_window: int = Field(default=1000, description="Coincidence window in picoseconds. Default: 1000 (1 ns)")
    timestamp: str = Field(
        default="Last",
        description="Timestamp of the coincidence virtual channel ('Last', 'First', 'ListedFirst', 'Average'). Default: 'Last'",
    )
    binwidth: int = Field(default=int(1e9), description="Bin width in picoseconds. Default: 1e9 (1 second)")
    n_values: int = Field(default=1, description="Number of bins. Default: 1")
    target_location: str = Field(default=DEFAULT_TARGET_LOCATION, description=TARGET_LOCATION_HELP)
    refresh_rate: int = Field(default=25, description=REFRESH_RATE_HELP)

    @field_validator("timestamp", mode="before")
    @classmethod
    def validate_timestamp(cls, value: Any) -> str:
        """Accept only TimeTagger's CoincidenceTimestamp names (case-insensitive).

        TimeTagger rejects an unknown timestamp type, so MaaS does too instead
        of silently falling back to 'Last'.
        """
        canonical = {name.lower(): name for name in COINCIDENCE_TIMESTAMPS}
        key = value.lower() if isinstance(value, str) else None
        if key not in canonical:
            raise ValueError(
                f"Invalid coincidence timestamp {value!r}. Must be one of {list(COINCIDENCE_TIMESTAMPS)}."
            )
        return canonical[key]

    @model_validator(mode="before")
    @classmethod
    def validate_coincidences_input(cls, data: Any) -> Any:
        """Normalize the groups into coincidences/coincidence_groups/channels and check each group."""
        if not isinstance(data, dict):
            return data
        data = data.copy()

        if "coincidenceWindow" in data and "coincidence_window" not in data:
            data["coincidence_window"] = data.pop("coincidenceWindow")

        raw_input = next(
            (data[key] for key in ("coincidences", "coincidence_groups", "channels") if data.get(key) is not None),
            None,
        )
        # Nothing given: let Pydantic report the missing 'channels' field.
        if raw_input is None:
            return data

        if not isinstance(raw_input, (list, tuple)):
            raise ValueError(
                "Coincidence input must be a list of lists of channel numbers (e.g. [[1, 2], [2, 3]]). "
                "Simple 1D channel lists are deprecated and no longer supported."
            )
        if len(raw_input) == 0:
            raise ValueError(
                "Coincidence measurement requires a non-empty list of lists of channel numbers "
                "(e.g. coincidences=[[1, 2], [2, 3]])."
            )
        if any(not isinstance(item, (list, tuple)) for item in raw_input):
            raise ValueError(
                "Simple 1D channel lists for coincidence are deprecated and no longer supported. "
                "Coincidence input must be a list of lists of channel numbers (e.g., [[1, 2]] instead of [1, 2])."
            )

        groups = []
        for i, group in enumerate(raw_input):
            if len(group) < 2:
                raise ValueError(f"Coincidence group at index {i} ({group}) must contain at least 2 channels.")
            for ch in group:
                if not isinstance(ch, int) or isinstance(ch, bool):
                    raise ValueError(f"Channel number {ch} in coincidence group {group} must be an integer.")
            groups.append([int(ch) for ch in group])

        data["coincidences"] = data["coincidence_groups"] = data["channels"] = groups
        return data

    @property
    def unique_channels(self) -> list[int]:
        """Sorted unique channel numbers used by any group."""
        return sorted({ch for group in self.coincidences or [] for ch in group})

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "coincidences": [[1, 2], [2, 3, 5]],
            "user_name": "abc-123-def",
            "coincidence_window": 1000,
            "timestamp": "Last",
            "binwidth": 1000000000,
            "n_values": 1,
            "target_location": DEFAULT_TARGET_LOCATION,
            "refresh_rate": 25,
        }
    })


class SaveRawTagsMetadata(BaseModel):
    """Settings of a save-raw-tags measurement (TimeTagger FileWriter)."""

    channel_list: list[int] = Field(description="List of channels to save raw tags from. Required.")
    user_name: str = Field(description=USER_NAME_HELP)
    target_file_path: str = Field(description="File path to save the raw tags data. Required.")

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "channel_list": [1, 2, 3],
            "user_name": "abc-123-def",
            "target_file_path": "~/Desktop/MaasData/{datetime}/raw_tags.ttbin",
        }
    })


class SetParametersMetadata(BaseModel):
    """Input delay and/or trigger voltage to apply to booked channels."""

    channels: list[int] = Field(description="List of channel numbers to configure. Required.")
    user_name: str = Field(description=USER_NAME_HELP)
    input_delay: Optional[int] = Field(default=None, description="Input delay in picoseconds")
    trigger_voltage: Optional[float] = Field(default=None, description="Trigger voltage in volts")

    model_config = ConfigDict(json_schema_extra={
        "example": {"channels": [1, 2], "user_name": "abc-123-def", "input_delay": 1000, "trigger_voltage": 0.5}
    })


# ============================================================================
# Request models
# ============================================================================


class MeasurementRequest(BaseModel):
    """Base for all measurement requests.

    - A flat payload (metadata fields at the top level, no "metadata" key) is
      accepted and wrapped into {"measurement_type", "duration_seconds", "metadata"}.
    - Attributes of the metadata can be read directly from the request:
      ``request.binwidth`` is ``request.metadata.binwidth``.
    """

    # duration_seconds used for a flat payload that does not give one
    FLAT_DEFAULT_DURATION: ClassVar[Optional[float]] = None

    @model_validator(mode="before")
    @classmethod
    def wrap_flat_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict) or "metadata" in data:
            return data
        metadata = dict(data)
        wrapped: dict[str, Any] = {"metadata": metadata}
        if "measurement_type" in metadata:
            wrapped["measurement_type"] = metadata.pop("measurement_type")
        duration_seconds = metadata.pop("duration_seconds", cls.FLAT_DEFAULT_DURATION)
        if "duration_seconds" in cls.model_fields:
            wrapped["duration_seconds"] = duration_seconds
        return wrapped

    def __getattr__(self, name: str) -> Any:
        try:
            return super().__getattr__(name)
        except AttributeError:
            metadata = self.__dict__.get("metadata")
            if metadata is not None and not name.startswith("_") and hasattr(metadata, name):
                return getattr(metadata, name)
            raise


class CountRateMeasurementRequest(MeasurementRequest):
    """Count events on `channels` for `duration_seconds` and save the counts."""

    FLAT_DEFAULT_DURATION: ClassVar[Optional[float]] = 60

    measurement_type: MeasurementType = MeasurementType.COUNT_RATE
    duration_seconds: int = Field(description="Duration in seconds for the count-rate measurement")
    metadata: CountRateMetadata

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "measurement_type": "count_rate",
            "duration_seconds": 60,
            "metadata": CountRateMetadata.model_config["json_schema_extra"]["example"],
        }
    })


class CountRateLiveMeasurementRequest(MeasurementRequest):
    """Stream counts on `channels` to Redis until stopped, or for `duration_seconds`."""

    measurement_type: MeasurementType = MeasurementType.COUNT_RATE_LIVE
    duration_seconds: Optional[float] = Field(None, gt=0, description=LIVE_DURATION_HELP)
    metadata: CountRateMetadata

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "measurement_type": "count_rate_live",
            "metadata": {"channels": [1, 2, 3], "user_name": "abc-123-def", "binwidth": 1000000000, "n_values": 1},
        }
    })


class CorrelationMeasurementRequest(MeasurementRequest):
    """Histogram time differences between channel1 and channel2 for `duration_seconds`."""

    FLAT_DEFAULT_DURATION: ClassVar[Optional[float]] = 60

    measurement_type: MeasurementType = MeasurementType.CORRELATION
    duration_seconds: int = Field(description="Duration in seconds for the correlation measurement")
    metadata: CorrelationMetadata

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "measurement_type": "correlation",
            "duration_seconds": 60,
            "metadata": CorrelationMetadata.model_config["json_schema_extra"]["example"],
        }
    })


class CorrelationLiveMeasurementRequest(MeasurementRequest):
    """Stream a correlation histogram of channel1 and channel2 until stopped."""

    measurement_type: MeasurementType = MeasurementType.CORRELATION_LIVE
    metadata: CorrelationLiveMetadata

    @property
    def channels(self) -> list[int]:
        return [self.metadata.channel1, self.metadata.channel2]


class CoincidencesMeasurementRequest(MeasurementRequest):
    """Count coincidences of each channel group for `duration_seconds`."""

    FLAT_DEFAULT_DURATION: ClassVar[Optional[float]] = 60

    measurement_type: MeasurementType = MeasurementType.COINCIDENCES
    duration_seconds: int = Field(description="Duration in seconds for the coincidences measurement")
    metadata: CoincidencesMetadata

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "measurement_type": "coincidences",
            "duration_seconds": 60,
            "metadata": CoincidencesMetadata.model_config["json_schema_extra"]["example"],
        }
    })


class CoincidencesLiveMeasurementRequest(MeasurementRequest):
    """Stream coincidence counts of each channel group until stopped, or for `duration_seconds`."""

    measurement_type: MeasurementType = MeasurementType.COINCIDENCES_LIVE
    duration_seconds: Optional[float] = Field(None, gt=0, description=LIVE_DURATION_HELP)
    metadata: CoincidencesMetadata

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "measurement_type": "coincidences_live",
            "metadata": CoincidencesMetadata.model_config["json_schema_extra"]["example"],
        }
    })


class StartStopLiveMeasurementRequest(MeasurementRequest):
    """Stream a start-stop histogram until stopped."""

    measurement_type: MeasurementType = MeasurementType.STARTSTOP_LIVE
    metadata: StartStopLiveMetadata

    @property
    def channels(self) -> list[int]:
        return [self.metadata.click_channel, self.metadata.start_channel]


class HistogramLiveMeasurementRequest(MeasurementRequest):
    """Stream a time histogram until stopped."""

    measurement_type: MeasurementType = MeasurementType.HISTOGRAM_LIVE
    metadata: HistogramLiveMetadata

    @property
    def channels(self) -> list[int]:
        return [self.metadata.click_channel, self.metadata.start_channel]


class SaveRawTagsMeasurmentRequest(MeasurementRequest):
    """Write every time tag on `channel_list` to a .ttbin file for `duration_seconds`."""

    FLAT_DEFAULT_DURATION: ClassVar[Optional[float]] = 60

    measurement_type: MeasurementType = MeasurementType.SAVE_RAW_TAGS
    duration_seconds: int = Field(description="Duration in seconds to save raw tags")
    metadata: SaveRawTagsMetadata

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "measurement_type": "save_raw_tags",
            "duration_seconds": 60,
            "metadata": SaveRawTagsMetadata.model_config["json_schema_extra"]["example"],
        }
    })


class SetParametersRequest(MeasurementRequest):
    """Set input delay and/or trigger voltage of booked channels."""

    FLAT_DEFAULT_DURATION: ClassVar[Optional[float]] = 0

    measurement_type: MeasurementType = MeasurementType.SET_PARAMETERS
    duration_seconds: int = Field(default=0, description="Duration in seconds (0: apply immediately)")
    metadata: SetParametersMetadata

    model_config = ConfigDict(json_schema_extra={
        "example": {
            "measurement_type": "set_parameters",
            "duration_seconds": 0,
            "metadata": SetParametersMetadata.model_config["json_schema_extra"]["example"],
        }
    })


# Request model for each measurement type (the worker validates queued metadata with it)
REQUEST_MODELS: dict[str, type[MeasurementRequest]] = {
    MeasurementType.COUNT_RATE.value: CountRateMeasurementRequest,
    MeasurementType.COUNT_RATE_LIVE.value: CountRateLiveMeasurementRequest,
    MeasurementType.CORRELATION.value: CorrelationMeasurementRequest,
    MeasurementType.CORRELATION_LIVE.value: CorrelationLiveMeasurementRequest,
    MeasurementType.COINCIDENCES.value: CoincidencesMeasurementRequest,
    MeasurementType.COINCIDENCES_LIVE.value: CoincidencesLiveMeasurementRequest,
    MeasurementType.COINCIDENCE.value: CoincidencesMeasurementRequest,
    MeasurementType.COINCIDENCE_LIVE.value: CoincidencesLiveMeasurementRequest,
    MeasurementType.STARTSTOP_LIVE.value: StartStopLiveMeasurementRequest,
    MeasurementType.HISTOGRAM_LIVE.value: HistogramLiveMeasurementRequest,
    MeasurementType.SAVE_RAW_TAGS.value: SaveRawTagsMeasurmentRequest,
    MeasurementType.SET_PARAMETERS.value: SetParametersRequest,
}


def get_metadata_model(measurement_type: str) -> type[BaseModel]:
    """Metadata model of a measurement type.

    Raises:
        ValueError: unknown measurement type
    """
    try:
        request_model = REQUEST_MODELS[measurement_type]
    except KeyError:
        raise ValueError(
            f"Unknown measurement type: '{measurement_type}'. Available types: {list(REQUEST_MODELS)}"
        ) from None
    return request_model.model_fields["metadata"].annotation


# ============================================================================
# Responses
# ============================================================================


class MeasurementResponse(BaseModel):
    """Returned when a measurement is started or stopped."""

    measurement_id: str = Field(description="Unique identifier for this measurement")
    measurement_type: MeasurementType
    status: str = Field(description="Current status: 'queued', 'active', 'completed', 'stopped', 'failed'")
    started_at: datetime = Field(description="When the measurement started")
    message: str = Field(description="Status message")
    stop_acknowledged: Optional[bool] = Field(
        default=None,
        description=(
            "Only set by DELETE: true once the worker confirmed the measurement has "
            "ended, false if it did not confirm within STOP_ACK_TIMEOUT_SECONDS"
        ),
    )


class MeasurementStatusResponse(BaseModel):
    """Returned by GET /api/v1/measurements/{id}/status."""

    measurement_id: str
    measurement_type: MeasurementType
    status: str
    started_at: datetime
    duration_so_far: float = Field(description="Duration in seconds since start")
    metadata: Optional[dict[str, Any]]
    results: Optional[dict[str, Any]] = Field(None, description="Results (once available)")
    message: Optional[str] = Field(None, description="Latest status message, e.g. the error of a failed job")
