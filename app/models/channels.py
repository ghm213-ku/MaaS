"""Request and response models for channel booking, release and parameters."""

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _accept_channels_alias(data: Any) -> Any:
    """Accept "channels" as another name for "channel_numbers"."""
    if isinstance(data, dict) and "channels" in data and "channel_numbers" not in data:
        data = data.copy()
        data["channel_numbers"] = data.pop("channels")
    return data


class ChannelInfo(BaseModel):
    """One channel and its booking."""

    channel_number: int = Field(description="Channel number (1-16, 101-116, or 201-216)")
    status: str = Field(description="Channel status: 'available' or 'booked'")
    user_name: Optional[str] = Field(None, description="Who booked the channel")
    booking_time: Optional[str] = Field(None, description="ISO timestamp of when booked")


class ChannelBookRequest(BaseModel):
    """Body of POST /api/v1/channels/book."""

    user_name: str = Field(description="Who is booking the channels; must be the authenticated caller's username")
    channel_numbers: list[int] = Field(description="List of channel numbers to book (e.g., [1, 2, 3] or [101, 102])")

    @model_validator(mode="before")
    @classmethod
    def handle_channels_alias(cls, data: Any) -> Any:
        return _accept_channels_alias(data)

    @property
    def channels(self) -> list[int]:
        return self.channel_numbers

    model_config = ConfigDict(json_schema_extra={"example": {"user_name": "abc-123-def", "channel_numbers": [1, 2, 3]}})


class ChannelBookResponse(BaseModel):
    user_name: str
    booked_channels: list[int]
    booking_time: str
    total_booked: int


class ChannelReleaseRequest(BaseModel):
    """Body of POST /api/v1/channels/release/{user_name}: which of the user's channels to free."""

    channel_numbers: list[int] = Field(
        ...,
        min_length=1,
        description="Channel numbers to release (e.g., [1, 2]). All must be booked by the user; otherwise nothing is released.",
    )

    @model_validator(mode="before")
    @classmethod
    def handle_channels_alias(cls, data: Any) -> Any:
        return _accept_channels_alias(data)

    model_config = ConfigDict(json_schema_extra={"example": {"channel_numbers": [1, 2]}})


class ChannelReleaseResponse(BaseModel):
    user_name: str
    released_channels: list[int]
    total_released: int
    parameter_reset_id: Optional[str] = Field(
        None,
        description=(
            "ID of the queued set-parameters job that resets the released channels "
            "to trigger 0.5 V / delay 0 ps. Poll GET /api/v1/measurements/{id}/status "
            "to see when it has been applied."
        ),
    )


class ChannelParameters(BaseModel):
    """Current trigger level and input delay of one channel, as read from the Time Tagger."""

    channel_number: int
    trigger_voltage: float = Field(description="Trigger level in V")
    input_delay: int = Field(description="Input delay in ps")


class ChannelParametersResponse(BaseModel):
    """Current trigger level and input delay of every channel the worker has reported."""

    channels: list[ChannelParameters]


class ChannelListResponse(BaseModel):
    channels: list[ChannelInfo]
    total_channels: int
    available_channels: int
    booked_channels: int


class ChannelStatsResponse(BaseModel):
    total_channels: int
    available_channels: int
    booked_channels: int
    utilization_percent: float
    available_channel_numbers: list[int] = Field(description="List of available channel numbers")
    user_names: dict[str, list[int]] = Field(description="Mapping of user_name to their booked channels")
