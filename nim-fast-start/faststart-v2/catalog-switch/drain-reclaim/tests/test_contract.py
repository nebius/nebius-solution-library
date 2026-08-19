from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from validate_contract import ContractError, validate  # noqa: E402


class ContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.contract = json.loads((ROOT / "contract.json").read_text())
        cls.threat = json.loads(
            (ROOT.parent / "security-reliability" / "threat_model.json").read_text()
        )

    def test_checked_in_contract_matches_implementation_and_reviewed_security(self) -> None:
        result = validate(self.contract, self.threat)
        self.assertEqual(result["status"], "valid")
        self.assertEqual(result["backends"], ["kubernetes", "node-local"])

    def test_missing_state_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["states"].pop()
        with self.assertRaisesRegex(ContractError, "states differ"):
            validate(mutated, self.threat)

    def test_missing_security_control_fails_closed(self) -> None:
        mutated = copy.deepcopy(self.threat)
        mutated["controls"] = [
            item for item in mutated["controls"] if item["id"] != "CTL-04"
        ]
        with self.assertRaisesRegex(ContractError, "missing security controls"):
            validate(self.contract, mutated)

    def test_modal_cannot_enter_measured_backend_scope(self) -> None:
        mutated = copy.deepcopy(self.contract)
        mutated["backends"]["measured_internal"].append("modal")
        with self.assertRaisesRegex(ContractError, "Kubernetes and node-local only"):
            validate(mutated, self.threat)


if __name__ == "__main__":
    unittest.main()
