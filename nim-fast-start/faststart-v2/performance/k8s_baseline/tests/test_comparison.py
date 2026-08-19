from __future__ import annotations

import copy
import unittest

from performance.k8s_baseline.comparison import validate_pair_values
from performance.k8s_baseline.contract import BaselineError


class OneVariableComparisonTests(unittest.TestCase):
    def plans(self) -> tuple[dict, dict]:
        baseline = {
            "schema": "plan/v2", "experiment_id": "baseline",
            "variant": "per_run_service", "precreated_support": [],
            "trace_sha256": "a" * 64,
            "models": [{"model_id": "boltz2", "input": {"payload_sha256": "b" * 64}}],
            "kubernetes": {
                "context": "fresh-context", "expected_server": "https://fresh.invalid",
                "namespace": "mlsp-csw-pair", "namespace_uid": "namespace-uid-1",
                "node_name": "fresh-h100-node", "node_uid": "node-uid-1",
                "broker_node_id": "computeinstance-node-1",
                "broker_node_group_id": "mk8snodegroup-1",
            },
            "resource_lease": {
                "lease_id": "lease-1", "sha256": "c" * 64,
                "request_sha256": "d" * 64,
            },
            "security": {"credentials": {"secret_uid": "secret-uid-1"}},
        }
        candidate = copy.deepcopy(baseline)
        candidate.update(
            {
                "experiment_id": "candidate", "variant": "precreated_service",
                "precreated_support": ["service"],
            }
        )
        return baseline, candidate

    def test_only_precreated_service_change_is_admitted(self) -> None:
        baseline, candidate = self.plans()
        self.assertEqual(len(validate_pair_values(baseline, candidate)), 64)

    def test_trace_model_node_lease_and_credential_changes_are_rejected(self) -> None:
        mutations = (
            ("trace", lambda plan: plan.__setitem__("trace_sha256", "f" * 64)),
            ("model", lambda plan: plan["models"][0].__setitem__("model_id", "openfold2")),
            ("node", lambda plan: plan["kubernetes"].__setitem__("node_uid", "foreign-node")),
            ("lease", lambda plan: plan["resource_lease"].__setitem__("lease_id", "lease-2")),
            ("credential", lambda plan: plan["security"]["credentials"].__setitem__("secret_uid", "secret-2")),
        )
        for label, mutate in mutations:
            with self.subTest(label=label):
                baseline, candidate = self.plans()
                mutate(candidate)
                with self.assertRaisesRegex(BaselineError, "differ outside"):
                    validate_pair_values(baseline, candidate)


if __name__ == "__main__":
    unittest.main()
