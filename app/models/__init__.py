"""Pydantic models for API requests and responses.

- measurements.py: measurement types, their metadata/request models, responses
- channels.py: channel booking, release and parameter models
"""

from app.models.channels import (
    ChannelBookRequest,
    ChannelBookResponse,
    ChannelInfo,
    ChannelListResponse,
    ChannelParameters,
    ChannelParametersResponse,
    ChannelReleaseRequest,
    ChannelReleaseResponse,
    ChannelStatsResponse,
)
from app.models.measurements import (
    COINCIDENCE_TIMESTAMPS,
    DEFAULT_TARGET_LOCATION,
    REQUEST_MODELS,
    CoincidencesLiveMeasurementRequest,
    CoincidencesMeasurementRequest,
    CoincidencesMetadata,
    CorrelationLiveMeasurementRequest,
    CorrelationLiveMetadata,
    CorrelationMeasurementRequest,
    CorrelationMetadata,
    CountRateLiveMeasurementRequest,
    CountRateMeasurementRequest,
    CountRateMetadata,
    HistogramLiveMeasurementRequest,
    HistogramLiveMetadata,
    MeasurementRequest,
    MeasurementResponse,
    MeasurementStatusResponse,
    MeasurementType,
    SaveRawTagsMeasurmentRequest,
    SaveRawTagsMetadata,
    SetParametersMetadata,
    SetParametersRequest,
    StartStopLiveMeasurementRequest,
    StartStopLiveMetadata,
    TimeHistogramLiveMetadata,
    get_metadata_model,
)
