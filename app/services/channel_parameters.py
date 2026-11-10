"""Current trigger level and input delay of each Time Tagger input channel.

The Time Tagger lives in the worker process, so the API cannot read it
directly. The worker records each channel's values in a Redis hash whenever it
changes them (at startup and after every set-parameters job), and the API
serves that hash from GET /api/v1/channels/parameters.
"""

import logging
import json
from typing import Any, Dict, Iterable, List


logger = logging.getLogger(__name__)

CHANNEL_PARAMETERS_KEY = "channels:parameters"


def record_channel_parameters(redis_client: Any, tagger: Any, channels: Iterable[int]) -> None:
    """Read each channel's trigger level and input delay back from the tagger and store them."""
    values = {}
    for channel in channels:
        channel = int(channel)
        try:
            values[str(channel)] = json.dumps({
                "trigger_voltage": float(tagger.getTriggerLevel(channel)),
                "input_delay": int(tagger.getInputDelay(channel)),
            })
        except Exception as e:
            logger.warning(f"Could not read parameters of channel {channel}: {e}")
    if values:
        redis_client.hset(CHANNEL_PARAMETERS_KEY, mapping=values)


def get_channel_parameters(redis_client: Any) -> List[Dict[str, Any]]:
    """Return the recorded parameters as [{channel_number, trigger_voltage, input_delay}], sorted by channel."""
    stored = redis_client.hgetall(CHANNEL_PARAMETERS_KEY) or {}
    result = []
    for channel, raw in stored.items():
        if isinstance(channel, bytes):
            channel = channel.decode("utf-8")
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        try:
            params = json.loads(raw)
            result.append({
                "channel_number": int(channel),
                "trigger_voltage": float(params["trigger_voltage"]),
                "input_delay": int(params["input_delay"]),
            })
        except (ValueError, KeyError, TypeError) as e:
            logger.warning(f"Ignoring malformed parameters for channel {channel}: {e}")
    return sorted(result, key=lambda p: p["channel_number"])
