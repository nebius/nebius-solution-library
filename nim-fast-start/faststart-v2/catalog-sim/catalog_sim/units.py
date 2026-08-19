"""Validated unit handling for the catalog switch simulator.

All simulator-internal time is integer microseconds and all data volume is
integer bytes so that discrete-event arithmetic stays exact and replayable.
Floating-point seconds only appear at the input (measured evidence) and
output (report) boundaries, through the converters below.
"""

from __future__ import annotations

MICROS_PER_SECOND = 1_000_000
SECONDS_PER_HOUR = 3_600
BYTES_PER_GIB = 1024**3


class UnitError(ValueError):
    """Raised when a value cannot be a valid physical quantity."""


def seconds_to_micros(seconds: float) -> int:
    """Convert non-negative seconds to integer microseconds (round half up)."""
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        raise UnitError(f"seconds must be numeric, got {type(seconds).__name__}")
    if seconds != seconds or seconds in (float("inf"), float("-inf")):
        raise UnitError(f"seconds must be finite, got {seconds!r}")
    if seconds < 0:
        raise UnitError(f"seconds must be non-negative, got {seconds!r}")
    return int(seconds * MICROS_PER_SECOND + 0.5)


def micros_to_seconds(micros: int) -> float:
    if not isinstance(micros, int) or isinstance(micros, bool):
        raise UnitError(f"micros must be int, got {type(micros).__name__}")
    if micros < 0:
        raise UnitError(f"micros must be non-negative, got {micros!r}")
    return micros / MICROS_PER_SECOND


def micros_to_hours(micros: int) -> float:
    return micros_to_seconds(micros) / SECONDS_PER_HOUR


def gib_to_bytes(gib: float) -> int:
    if not isinstance(gib, (int, float)) or isinstance(gib, bool):
        raise UnitError(f"GiB must be numeric, got {type(gib).__name__}")
    if gib < 0:
        raise UnitError(f"GiB must be non-negative, got {gib!r}")
    return int(gib * BYTES_PER_GIB + 0.5)


def check_bytes(value: int, label: str = "bytes") -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise UnitError(f"{label} must be int, got {type(value).__name__}")
    if value < 0:
        raise UnitError(f"{label} must be non-negative, got {value!r}")
    return value


def transfer_micros(num_bytes: int, bytes_per_second: int) -> int:
    """Exact ceiling-division transfer time for a byte payload."""
    check_bytes(num_bytes, "num_bytes")
    check_bytes(bytes_per_second, "bytes_per_second")
    if bytes_per_second == 0:
        raise UnitError("bytes_per_second must be positive")
    return (num_bytes * MICROS_PER_SECOND + bytes_per_second - 1) // bytes_per_second
