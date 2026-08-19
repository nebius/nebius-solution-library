"""Versioned input schema with mandatory measured/placeholder provenance.

Every scalar or distribution the simulator consumes is one of:

- ``MeasuredQuantity`` / ``EmpiricalDist``: backed by retained evidence; the
  ``source`` reference is mandatory and points at the evidence file.
- ``PlaceholderQuantity``: an assumption; a bounded sensitivity range
  ``low <= base <= high`` (with ``low < high``) is mandatory, and every
  experiment is expected to be swept across it.

Scenario documents serialize to JSON with an explicit ``schema_version`` so
downstream consumers (router/runtime tasks) can validate compatibility.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Sequence

from . import SCHEMA_VERSION
from .units import UnitError, seconds_to_micros

SENSITIVITY_LEVELS = ("low", "base", "high")


class SchemaError(ValueError):
    """Raised when an input document violates the versioned schema."""


@dataclass(frozen=True)
class MeasuredQuantity:
    """A single measured scalar with a mandatory evidence reference."""

    name: str
    value: float
    unit: str
    source: str

    def __post_init__(self) -> None:
        if not self.source or not self.source.strip():
            raise SchemaError(f"measured quantity {self.name!r} requires a source")
        if self.value < 0:
            raise SchemaError(f"measured quantity {self.name!r} must be >= 0")

    @property
    def provenance(self) -> str:
        return "measured"

    def to_json(self) -> dict:
        return {
            "provenance": "measured",
            "name": self.name,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
        }


@dataclass(frozen=True)
class PlaceholderQuantity:
    """An assumed scalar with a mandatory bounded sensitivity range."""

    name: str
    low: float
    base: float
    high: float
    unit: str
    rationale: str

    def __post_init__(self) -> None:
        if not self.rationale or not self.rationale.strip():
            raise SchemaError(f"placeholder {self.name!r} requires a rationale")
        if not (self.low <= self.base <= self.high):
            raise SchemaError(
                f"placeholder {self.name!r} needs low <= base <= high, got "
                f"{self.low!r}/{self.base!r}/{self.high!r}"
            )
        if self.low == self.high:
            raise SchemaError(
                f"placeholder {self.name!r} needs a non-degenerate sensitivity "
                f"range (low < high)"
            )
        if self.low < 0:
            raise SchemaError(f"placeholder {self.name!r} must be >= 0")

    @property
    def provenance(self) -> str:
        return "placeholder"

    def at(self, level: str) -> float:
        if level not in SENSITIVITY_LEVELS:
            raise SchemaError(f"unknown sensitivity level {level!r}")
        return {"low": self.low, "base": self.base, "high": self.high}[level]

    def to_json(self) -> dict:
        return {
            "provenance": "placeholder",
            "name": self.name,
            "low": self.low,
            "base": self.base,
            "high": self.high,
            "unit": self.unit,
            "rationale": self.rationale,
        }


@dataclass(frozen=True)
class EmpiricalDist:
    """An empirical sample set, sampled uniformly at replay time.

    Samples are stored in integer microseconds. ``percentile`` uses the
    repository's nearest-rank convention (1-indexed rank ``ceil(p/100 * n)``).
    ``provenance`` is ``"measured"`` only for evidence-backed sample sets;
    any transformation (e.g. ``scaled``) demotes the result to
    ``"placeholder"`` so inferred distributions can never masquerade as
    measurements.
    """

    name: str
    samples_micros: tuple
    source: str
    provenance: str = "measured"

    def __post_init__(self) -> None:
        if not self.source or not self.source.strip():
            raise SchemaError(f"empirical dist {self.name!r} requires a source")
        if self.provenance not in ("measured", "placeholder"):
            raise SchemaError(
                f"empirical dist {self.name!r} provenance must be measured or "
                f"placeholder, got {self.provenance!r}"
            )
        if len(self.samples_micros) == 0:
            raise SchemaError(f"empirical dist {self.name!r} must be non-empty")
        for s in self.samples_micros:
            if not isinstance(s, int) or isinstance(s, bool) or s < 0:
                raise SchemaError(
                    f"empirical dist {self.name!r} samples must be non-negative "
                    f"integer micros, got {s!r}"
                )

    @classmethod
    def from_seconds(
        cls, name: str, samples_seconds: Sequence[float], source: str
    ) -> "EmpiricalDist":
        try:
            micros = tuple(seconds_to_micros(s) for s in samples_seconds)
        except UnitError as exc:
            raise SchemaError(f"empirical dist {name!r}: {exc}") from exc
        return cls(name=name, samples_micros=micros, source=source)

    @classmethod
    def scaled(cls, base: "EmpiricalDist", factor: float, name: str) -> "EmpiricalDist":
        if factor <= 0:
            raise SchemaError(f"scale factor for {name!r} must be positive")
        return cls(
            name=name,
            samples_micros=tuple(int(s * factor + 0.5) for s in base.samples_micros),
            source=f"{base.source} (scaled x{factor:.4f}, placeholder factor)",
            provenance="placeholder",
        )

    def sample(self, rng) -> int:
        return self.samples_micros[rng.randrange(len(self.samples_micros))]

    def percentile(self, p: float) -> int:
        if not (0 < p <= 100):
            raise SchemaError(f"percentile must be in (0, 100], got {p!r}")
        ordered = sorted(self.samples_micros)
        rank = math.ceil(p * len(ordered) / 100)
        rank = max(1, min(len(ordered), rank))
        return ordered[rank - 1]

    def median_micros(self) -> int:
        return self.percentile(50)

    def to_json(self) -> dict:
        return {
            "provenance": self.provenance,
            "name": self.name,
            "samples_micros": list(self.samples_micros),
            "source": self.source,
        }


@dataclass(frozen=True)
class ScenarioHeader:
    """Header every serialized scenario/result document carries."""

    schema_version: str = SCHEMA_VERSION
    generator: str = "catalog_sim"
    extra: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        doc = {"schema_version": self.schema_version, "generator": self.generator}
        doc.update(self.extra)
        return doc


def require_schema_version(doc: dict, context: str) -> None:
    version = doc.get("schema_version")
    if version != SCHEMA_VERSION:
        raise SchemaError(
            f"{context}: schema_version {version!r} is not supported "
            f"(expected {SCHEMA_VERSION!r})"
        )
