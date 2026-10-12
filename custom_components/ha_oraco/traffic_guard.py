"""Guard cumulative switch byte counters against resets and impossible jumps.

Unknown speed uses a generous 10 Gbit/s ceiling. Never infer counter wraps.
"""
import math
import re

MAX_SAMPLE_SECONDS = 120
HEADROOM = 1.25
UNKNOWN_LINK_BPS = 10_000_000_000


def link_capacity(speed):
    match = re.fullmatch(r"\s*(\d+(?:\.\d+)?)\s*([GMK]?)\s*(?:bps|b/s|b)?\s*", str(speed or ""), re.I)
    if not match:
        return UNKNOWN_LINK_BPS
    multipliers = {"": 1_000_000, "K": 1_000, "M": 1_000_000, "G": 1_000_000_000}
    value = float(match.group(1)) * multipliers[match.group(2).upper()]
    return value if 100_000 <= value <= 100_000_000_000 else UNKNOWN_LINK_BPS


def valid_counter(value):
    return type(value) is int and 0 <= value <= 2**64 - 1


def counter_delta(previous, current, seconds, speed):
    """Return (bytes, reason). None means no safe delta can be attributed."""
    if not valid_counter(current):
        return None, "missing_or_invalid"
    if previous is None or not valid_counter(previous):
        return None, "baseline"
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds <= 0:
        return None, "invalid_interval"
    if seconds > MAX_SAMPLE_SECONDS:
        return None, "collection_gap"
    if current < previous:
        return None, "counter_reset_or_wrap"
    difference = current - previous
    max_bytes = (link_capacity(speed) / 8) * seconds * HEADROOM
    if difference > max_bytes:
        return None, "impossible_jump"
    return difference, None
