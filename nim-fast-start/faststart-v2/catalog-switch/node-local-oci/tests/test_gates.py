"""Static source gates: no fake path, no swallowed errors, single CLI surface,
no rejected-lineage identifiers, and exact-byte shared-source binding."""

from __future__ import annotations

import ast
import shutil
import tempfile
import unittest
from pathlib import Path

from . import helpers
from node_local_oci import binding
from node_local_oci.cli import build_parser
from node_local_oci.errors import Refusal

PACKAGE = Path(binding.PACKAGE_DIR)

# Identifiers whose presence would resurrect the rejected mock lineage.
FORBIDDEN_IDENTIFIER_FRAGMENTS = ("fake", "mock", "stub", "deterministicbackend",
                                  "simulat")
FORBIDDEN_TEXT_TOKENS = ("fake_oci", "external-t0/", "admission/v3", "admission/v4",
                         "drain/v3", "drain/v4", "gpu-zero/", "cleanup/v3",
                         "cleanup/v4", "trusted-client-recorder",
                         "trusted-external-recorder", "pinned-semantic-oracle-v1",
                         "node_runtime", "replacement_v")


def _iter_sources():
    for path in sorted(PACKAGE.glob("*.py")):
        yield path, path.read_text(encoding="utf-8")


class NoFakePath(unittest.TestCase):
    def test_no_fake_or_mock_identifiers_in_production_package(self):
        for path, source in _iter_sources():
            tree = ast.parse(source)
            names = set()
            for node in ast.walk(tree):
                for attr in ("id", "name", "attr", "arg", "module"):
                    value = getattr(node, attr, None)
                    if isinstance(value, str):
                        names.add(value)
            for name in names:
                lowered = name.lower()
                for fragment in FORBIDDEN_IDENTIFIER_FRAGMENTS:
                    self.assertNotIn(fragment, lowered,
                                     f"{path.name}: identifier {name!r}")

    def test_no_rejected_lineage_tokens_in_source_text(self):
        for path, source in _iter_sources():
            lowered = source.lower()
            for token in FORBIDDEN_TEXT_TOKENS:
                self.assertNotIn(token, lowered, f"{path.name}: {token!r}")

    def test_no_swallowed_exceptions(self):
        for path, source in _iter_sources():
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, ast.ExceptHandler):
                    only_pass = all(isinstance(stmt, ast.Pass) for stmt in node.body)
                    self.assertFalse(only_pass,
                                     f"{path.name}:{node.lineno} swallows exceptions")

    def test_subprocess_confined_to_execute_module(self):
        for path, source in _iter_sources():
            if path.name == "execute.py":
                continue
            tree = ast.parse(source)
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    modules = [alias.name for alias in node.names]
                    if isinstance(node, ast.ImportFrom) and node.module:
                        modules.append(node.module)
                    self.assertNotIn("subprocess", modules,
                                     f"{path.name}: subprocess outside execute.py")

    def test_cli_surface_has_no_backend_or_mode_selector(self):
        parser = build_parser()
        surfaces = {}
        for action in parser._subparsers._group_actions[0].choices.items():  # noqa: SLF001
            name, sub = action
            flags = set()
            for sub_action in sub._actions:  # noqa: SLF001
                flags.update(sub_action.option_strings)
            surfaces[name] = flags
        allowed = {
            "run": {"-h", "--help", "--keys-dir", "--state-dir", "--evidence-dir",
                    "--exchange-dir", "--policy", "--bundle", "--trace", "--ledger"},
            "recover": {"-h", "--help", "--keys-dir", "--state-dir", "--policy"},
            "verify-evidence": {"-h", "--help", "--trace", "--ledger", "--receipts"},
        }
        self.assertEqual(set(surfaces), set(allowed))
        for name, flags in surfaces.items():
            self.assertEqual(flags, allowed[name], name)


class SharedSourceBinding(unittest.TestCase):
    def test_pinned_bytes_verify_and_tamper_refuses(self):
        pins = binding.verify_shared_sources()
        self.assertEqual(pins["schema"], "catalog-switch/nlo-shared-sources/v1")
        commits = {entry["commit"] for entry in pins["files"]}
        self.assertEqual(commits, {binding.REQUEST_SLO_COMMIT,
                                   binding.SECURITY_MODEL_COMMIT})
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for rel in ("performance/request_slo",
                        "catalog-switch/security-reliability"):
                shutil.copytree(binding.FASTSTART_ROOT / rel, root / rel)
            target = root / "performance/request_slo/harness.py"
            target.write_text(target.read_text(encoding="utf-8")
                              .replace("request.accepted", "request.acceptedX"),
                              encoding="utf-8")
            with self.assertRaises(Refusal) as caught:
                binding.verify_shared_sources(root)
            self.assertIn(caught.exception.code,
                          ("binding.pin-sha256", "binding.pin-bytes"))

    def test_source_manifest_covers_whole_package(self):
        manifest = binding.verify_source_manifest()
        self.assertEqual(set(manifest["files"]),
                         {f"node_local_oci/{p.name}"
                          for p in PACKAGE.glob("*.py")})

    def test_shared_validator_is_the_pinned_t0_authority(self):
        harness = binding.import_shared_harness()
        self.assertEqual(harness.T0_BOUNDARY, "external-client-request-accepted/v1")
        self.assertEqual(
            harness.TERMINAL_BOUNDARY,
            "first-complete-semantically-valid-response/v1")
        # The production package must not define any private T0 boundary string.
        for path, source in _iter_sources():
            self.assertNotIn("request-accepted/v", source.replace(
                "external-client-request-accepted/v1", ""), path.name)


if __name__ == "__main__":
    unittest.main()
