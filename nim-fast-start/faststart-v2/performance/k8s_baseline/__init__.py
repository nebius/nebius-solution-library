"""Causal Kubernetes catalog-switch baseline.

The package deliberately builds on :mod:`performance.request_slo`; it does not
define another event, timing, percentile, or resource-ownership contract.
"""

from .contract import BASELINE_PLAN_SCHEMA, BaselineError, load_plan, validate_plan

__all__ = ["BASELINE_PLAN_SCHEMA", "BaselineError", "load_plan", "validate_plan"]
