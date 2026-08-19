#!/usr/bin/env python3
"""Offline tests for the frozen Modal pilot request-event schema."""

from __future__ import annotations

import ast
import json
import tempfile
import unittest
from pathlib import Path

from .event_schema import (
    SCHEMA,
    UNOBSERVABLE,
    EventValidationError,
    latency_seconds,
    load_events,
    validate_event,
)


def make_event(**overrides):
    event = {
        "schema": SCHEMA,
        "run_id": "of2-m0-001",
        "pilot": "of2",
        "model_id": "openfold2",
        "mode": "cold",
        "cache_state": "remote-miss",
        "outcome": "valid_response",
        "gpu_requested": "A100-80GB!",
        "gpu_allocated": "A100-80GB",
        "region_requested": "eu",
        "image_ref": "nvcr.io/nim/deepmind/openfold2:2.5.0@sha256:" + "a" * 64,
        "t0_wall_utc": "2026-08-19T12:00:00.000000Z",
        "t0_monotonic_s": 100.0,
        "t_first_valid_response_monotonic_s": 245.5,
        "attempts": 1,
        "semantic_validator": "validate_openfold2.py",
        "phases": {
            "http_ready": {"provenance": "client", "offset_from_t0_s": 140.0},
            "model_load": {"provenance": "container-log", "offset_from_t0_s": 120.0},
            "placement": {"provenance": UNOBSERVABLE},
        },
    }
    event.update(overrides)
    return event


class ValidateEventTest(unittest.TestCase):
    def test_accepts_complete_valid_response(self):
        self.assertEqual(validate_event(make_event())["pilot"], "of2")

    def test_latency_is_t0_to_first_valid_response(self):
        self.assertAlmostEqual(latency_seconds(make_event()), 145.5)

    def test_rejects_wrong_schema(self):
        with self.assertRaises(EventValidationError):
            validate_event(make_event(schema="v0"))

    def test_rejects_unpinned_image(self):
        with self.assertRaises(EventValidationError):
            validate_event(make_event(image_ref="nvcr.io/nim/deepmind/openfold2:2.5.0"))

    def test_rejects_completion_before_t0(self):
        with self.assertRaises(EventValidationError):
            validate_event(make_event(t_first_valid_response_monotonic_s=99.0))

    def test_rejects_valid_response_without_validator(self):
        event = make_event()
        del event["semantic_validator"]
        with self.assertRaises(EventValidationError):
            validate_event(event)

    def test_failure_requires_reason(self):
        with self.assertRaises(EventValidationError):
            validate_event(make_event(outcome="error"))
        validated = validate_event(
            make_event(outcome="error", failure_reason="Resource Exhausted")
        )
        self.assertEqual(validated["outcome"], "error")

    def test_rejects_phase_before_t0(self):
        phases = {"early": {"provenance": "client", "offset_from_t0_s": -0.1}}
        with self.assertRaises(EventValidationError):
            validate_event(make_event(phases=phases))

    def test_unobservable_phase_needs_no_offset(self):
        phases = {"drain": {"provenance": UNOBSERVABLE}}
        validate_event(make_event(phases=phases))

    def test_rejects_unknown_mode_and_cache_state(self):
        with self.assertRaises(EventValidationError):
            validate_event(make_event(mode="prewarmed-secretly"))
        with self.assertRaises(EventValidationError):
            validate_event(make_event(cache_state="probably-warm"))

    def test_rejects_zero_attempts(self):
        with self.assertRaises(EventValidationError):
            validate_event(make_event(attempts=0))


class LoadEventsTest(unittest.TestCase):
    def test_loads_jsonl_and_fails_closed_on_bad_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "events.jsonl"
            path.write_text(
                json.dumps(make_event()) + "\n" + json.dumps({"schema": "bad"}) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(EventValidationError):
                load_events(str(path))
            path.write_text(json.dumps(make_event()) + "\n", encoding="utf-8")
            self.assertEqual(len(load_events(str(path))), 1)


class ModalAppTemplateTest(unittest.TestCase):
    def test_template_parses_without_modal_installed(self):
        source = (Path(__file__).parent / "modal_nim_app.py").read_text(encoding="utf-8")
        ast.parse(source)
        self.assertIn("UNVALIDATED", source)
        self.assertIn("mlspec-catswitch-ngc", source)


if __name__ == "__main__":
    unittest.main()
