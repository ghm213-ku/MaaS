"""Helpers for reading totals from a TimeTagger Counter.

Counter.getData() is a circular buffer that holds only the last ``n_values``
bins, so summing it gives the counts of those bins, not of the whole
measurement. The totals below use Counter.getDataTotalCounts(), which counts
every event since the counter was last cleared (startFor clears it), excluding
the bin still being integrated.
"""

import asyncio
import logging
from typing import Any, Dict, Optional

import numpy as np


def counter_summary(counter: Any, binwidth: int) -> Dict[str, Any]:
    """Return total counts and average rates for a running or finished Counter.

    Args:
        counter: TimeTagger.Counter instance
        binwidth: The counter's bin width in ps

    Returns:
        counts_per_channel: total events per channel (Counter.getDataTotalCounts)
        count: sum of counts_per_channel
        integration_time_seconds: time covered by the completed bins
        count_rate_cps_per_channel: counts_per_channel / integration_time_seconds
        count_rate_cps: count / integration_time_seconds
    """
    counts = [int(x) for x in np.asarray(counter.getDataTotalCounts()).ravel()]
    integration_s = _integration_seconds(counter, binwidth)
    rates = [c / integration_s if integration_s > 0 else 0.0 for c in counts]
    total = sum(counts)
    return {
        "counts_per_channel": counts,
        "count": total,
        "integration_time_seconds": integration_s,
        "count_rate_cps_per_channel": rates,
        "count_rate_cps": total / integration_s if integration_s > 0 else 0.0,
    }


def _integration_seconds(counter: Any, binwidth: int) -> float:
    """Time in seconds covered by the completed bins that getDataTotalCounts includes."""
    capture_ps = _capture_duration_ps(counter)
    if capture_ps is None or binwidth <= 0:
        return 0.0
    completed_bins = capture_ps // int(binwidth)
    return completed_bins * int(binwidth) * 1e-12


def _capture_duration_ps(counter: Any) -> Optional[int]:
    try:
        return int(counter.getCaptureDuration())
    except Exception:
        return None


async def wait_until_finished(counter: Any, timeout_ms: int = 2000) -> None:
    """Wait, off the event loop, for a startFor acquisition to finish.

    Uses the Time Tagger's waitUntilFinished(timeout) (timeout in ms) so the
    caller can read the complete buffer afterwards.
    """
    try:
        await asyncio.get_event_loop().run_in_executor(
            None, counter.waitUntilFinished, timeout_ms
        )
    except Exception as e:
        logging.getLogger(__name__).warning(f"waitUntilFinished failed: {e}")
