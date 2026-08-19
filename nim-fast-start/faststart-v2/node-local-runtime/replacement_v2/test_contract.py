from __future__ import annotations
import hashlib, hmac, json, unittest
from replacement_v2.contract import ContractReject, TrustedState, V4Gate, digest

class Adversaries(unittest.TestCase):
    def setUp(self):
        self.key=b"k"*32; self.now=10_000_000_000
        self.g=V4Gate(self.key, TrustedState("i","b","l","owner","env",self.now))
    def t0(self, **kw):
        x={"schema":"external-t0/v2","request_id":"r","attempt_id":"a","accepted_ns":self.now-1_000_000,"client_observed_ns":self.now-2_000_000,"payload_sha256":"p","model_id":"m","model_version":"1","recorder_id":"trusted-external-recorder-v2"}; x.update(kw); body=x.copy(); x["client_signature"]=hmac.new(self.key,digest(body).encode(),hashlib.sha256).hexdigest(); return x
    def cmd(self, **kw):
        x={"schema":"admission/v4","attempt_id":"a","nonce":"n","deadline_ns":self.now+1_000_000,"instance_id":"i","boot_id":"b","lease_id":"l","owner":"owner","environment_digest":"env","input_digest":"x"}; x.update(kw); body=x.copy(); x["signature"]=hmac.new(self.key,digest(body).encode(),hashlib.sha256).hexdigest(); return x
    def test_late_t0_and_untrusted_recorder(self):
        with self.assertRaises(ContractReject): self.g.accept_external_t0(self.t0(accepted_ns=0))
        with self.assertRaises(ContractReject): self.g.accept_external_t0(self.t0(recorder_id="caller"))
    def test_distinct_inputs_and_semantics(self):
        with self.assertRaises(ContractReject): self.g.require_distinct_inputs([b"x",b"x"])
        with self.assertRaises(ContractReject): self.g.validate_response({"input_digest":"x","validator_digest":"bad","semantically_valid":True}, expected_input_digest="x", validator_digest="good")
    def test_admission_trusted_state_deadline_replay(self):
        self.g.accept_external_t0(self.t0())
        with self.assertRaises(ContractReject): self.g.command(self.cmd(instance_id="other"), attempt_id="a")
        self.g.command(self.cmd(), attempt_id="a")
        with self.assertRaises(ContractReject): self.g.command(self.cmd(), attempt_id="a")
    def test_cleanup_must_be_post_cleanup_and_nonempty(self):
        with self.assertRaises(ContractReject): self.g.require_cleanup({"schema":"cleanup-receipt/v3","resources":[]}, resource_ids=[], pre_cleanup=True)
        receipt={"schema":"cleanup-receipt/v3","resources":[{"id":"vm","absent":True,"status":"NOT_FOUND"}]}
        self.g.require_cleanup(receipt, resource_ids=["vm"], pre_cleanup=False)
    def test_checkpoint_environment_and_fallback_are_gates(self):
        with self.assertRaises(ContractReject): self.g.require_observation({"storage":"network-ssd","observed":False}, arm="network-ssd-control")
        with self.assertRaises(ContractReject): self.g.require_observation({"storage":"network-ssd","observed":True,"device_id":"nvme"}, arm="local-nvme")
    def test_drain_gpu_receipts_cannot_be_fabricated(self):
        with self.assertRaises(ContractReject): self.g.require_observation({"storage":"network-ssd","observed":True}, arm="network-ssd-control")

if __name__ == "__main__": unittest.main()
