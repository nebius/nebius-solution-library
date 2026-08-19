"""Trace-driven catalog switch policy simulator.

Deterministic discrete-event simulation of a ~200-model inference catalog
served by a heterogeneous GPU fleet, used to compare routing/placement,
L1 cache eviction, warm-capacity, admission, and prefetch policies under
uniform, skewed, bursty, correlated, and adversarial demand.

Measured inputs come from the faststart-v2 cohorts recorded in
``performance/COLD_START_METRICS.md``; every non-measured quantity is an
explicitly labeled bounded placeholder with a mandatory sensitivity range.
"""

__version__ = "1.0.0"

SCHEMA_VERSION = "1.0.0"
