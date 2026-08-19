"""GPU observation adversaries: fake proofs of idleness and partial scrubs."""

from __future__ import annotations

import unittest

from . import helpers
from node_local_oci.errors import Refusal
from node_local_oci.execute import Execution
from node_local_oci.gpu import (GpuObserver, MIB, assert_gpu_identity,
                                parse_compute_apps, parse_gpu_sample, parse_pmon,
                                verify_scrub_claim)

POLICY_GPU = {"product": helpers.STUB_GPU_PRODUCT, "count": 1,
              "uuids": [helpers.STUB_GPU_UUID],
              "memory_total_mib": helpers.STUB_GPU_MEMORY_MIB}


def execution(stdout: str, returncode: int = 0, stderr: str = "") -> Execution:
    return Execution(binary="nvidia-smi", resolved_path="/pinned/nvidia-smi",
                     binary_sha256="0" * 64, argv=("nvidia-smi",),
                     returncode=returncode, stdout=stdout, stderr=stderr,
                     started_monotonic_ns=1, ended_monotonic_ns=2)


def gpu_row(used: int = 0) -> str:
    return (f"{helpers.STUB_GPU_UUID}, {helpers.STUB_GPU_PRODUCT}, "
            f"{helpers.STUB_GPU_MEMORY_MIB}, {used}, {helpers.STUB_DRIVER}")


class _StaticObserver(GpuObserver):
    """Observer over pre-built observation dicts (assertion methods only)."""

    def __init__(self):  # noqa: super not called: only assertion methods used
        self.policy_gpu = POLICY_GPU


def observation(gpus=None, compute_apps=None, pmon=None) -> dict:
    return {"gpus": gpus if gpus is not None else parse_gpu_sample(
                execution(gpu_row() + "\n")),
            "compute_apps": compute_apps or [],
            "pmon": pmon or {"compute_clients": 0, "graphics_clients": 0},
            "executions": []}


class IdentityRules(unittest.TestCase):
    def test_empty_identity_output_is_not_evidence(self):
        with self.assertRaises(Refusal) as caught:
            parse_gpu_sample(execution(""))
        self.assertEqual(caught.exception.code, "gpu.query-empty")

    def test_failed_query_is_not_evidence(self):
        with self.assertRaises(Refusal):
            parse_gpu_sample(execution(gpu_row(), returncode=9))

    def test_wrong_uuid_product_count_memory_refuse(self):
        gpus = parse_gpu_sample(execution(gpu_row() + "\n"))
        for mutation, code in [
            ({"uuid": "GPU-ffffffff-1111-2222-3333-444455556666"},
             "gpu.identity-uuids"),
            ({"product": "NVIDIA H100 80GB HBM3"}, "gpu.identity-product"),
            ({"memory_total_mib": 81559}, "gpu.identity-memory"),
        ]:
            doctored = [dict(gpus[0], **mutation)]
            with self.assertRaises(Refusal) as caught:
                assert_gpu_identity(doctored, POLICY_GPU)
            self.assertEqual(caught.exception.code, code)
        with self.assertRaises(Refusal) as caught:
            assert_gpu_identity(gpus + gpus, POLICY_GPU)
        self.assertEqual(caught.exception.code, "gpu.identity-uuids")


class ZeroClientRules(unittest.TestCase):
    def test_99_compute_clients_refuse(self):
        rows = "\n".join(
            f"{helpers.STUB_GPU_UUID}, {1000 + i}, python3, 64" for i in range(99))
        apps = parse_compute_apps(execution(rows + "\n"))
        self.assertEqual(len(apps), 99)
        observer = _StaticObserver()
        with self.assertRaises(Refusal) as caught:
            observer.assert_zero_clients(observation(compute_apps=apps))
        self.assertEqual(caught.exception.code, "gpu.compute-clients")

    def test_single_graphics_client_refuses(self):
        observer = _StaticObserver()
        with self.assertRaises(Refusal) as caught:
            observer.assert_zero_clients(observation(
                pmon={"compute_clients": 0, "graphics_clients": 1}))
        self.assertEqual(caught.exception.code, "gpu.graphics-clients")

    def test_empty_pmon_is_not_zero_process_proof(self):
        with self.assertRaises(Refusal) as caught:
            parse_pmon(execution(""), 1)
        self.assertEqual(caught.exception.code, "gpu.pmon-empty")

    def test_header_only_pmon_is_not_zero_process_proof(self):
        header_only = ("# gpu   pid  type    sm   mem   enc   dec   command\n"
                       "# Idx     #   C/G     %     %     %     %   name\n")
        with self.assertRaises(Refusal) as caught:
            parse_pmon(execution(header_only), 1)
        self.assertEqual(caught.exception.code, "gpu.pmon-coverage")

    def test_pmon_missing_gpu_coverage_refuses(self):
        text = helpers.default_pmon_text()
        with self.assertRaises(Refusal) as caught:
            parse_pmon(execution(text), 2)  # two GPUs admitted, one row
        self.assertEqual(caught.exception.code, "gpu.pmon-coverage")

    def test_pmon_counts_compute_and_graphics(self):
        text = ("# gpu   pid  type    sm   mem   enc   dec   command\n"
                "# Idx     #   C/G     %     %     %     %   name\n"
                "    0  4242     C    90    50     -     -   python3\n"
                "    0  4343     G     1     1     -     -   Xorg\n")
        counts = parse_pmon(execution(text), 1)
        self.assertEqual(counts, {"compute_clients": 1, "graphics_clients": 1})

    def test_unparseable_pmon_row_refuses(self):
        text = ("# gpu   pid  type    sm   mem   enc   dec   command\n"
                "# Idx     #   C/G     %     %     %     %   name\n"
                "garbage row that cannot be parsed\n")
        with self.assertRaises(Refusal):
            parse_pmon(execution(text), 1)

    def test_compute_row_without_pid_refuses(self):
        with self.assertRaises(Refusal):
            parse_compute_apps(execution(
                f"{helpers.STUB_GPU_UUID}, not-a-pid, python3, 64\n"))


class ScrubRules(unittest.TestCase):
    def setUp(self):
        self.gpus = parse_gpu_sample(execution(gpu_row() + "\n"))
        self.observer = _StaticObserver()
        self.total_bytes = helpers.STUB_GPU_MEMORY_MIB * MIB

    def good_post(self):
        return observation()

    def test_full_scrub_passes(self):
        verified = verify_scrub_claim(
            {"gpu_uuid": helpers.STUB_GPU_UUID, "method": "full-vram-zero",
             "bytes_scrubbed": self.total_bytes},
            self.gpus, self.good_post(), self.observer)
        self.assertEqual(verified["bytes_scrubbed"], self.total_bytes)

    def test_one_byte_scrub_refuses(self):
        with self.assertRaises(Refusal) as caught:
            verify_scrub_claim(
                {"gpu_uuid": helpers.STUB_GPU_UUID, "method": "full-vram-zero",
                 "bytes_scrubbed": 1},
                self.gpus, self.good_post(), self.observer)
        self.assertEqual(caught.exception.code, "gpu.scrub-bytes")

    def test_scrub_bytes_use_observed_total_not_claimed(self):
        with self.assertRaises(Refusal) as caught:
            verify_scrub_claim(
                {"gpu_uuid": helpers.STUB_GPU_UUID, "method": "full-vram-zero",
                 "bytes_scrubbed": self.total_bytes - MIB},
                self.gpus, self.good_post(), self.observer)
        self.assertEqual(caught.exception.code, "gpu.scrub-bytes")

    def test_foreign_gpu_and_unknown_method_refuse(self):
        with self.assertRaises(Refusal) as caught:
            verify_scrub_claim(
                {"gpu_uuid": "GPU-other", "method": "full-vram-zero",
                 "bytes_scrubbed": self.total_bytes},
                self.gpus, self.good_post(), self.observer)
        self.assertEqual(caught.exception.code, "gpu.scrub-target")
        with self.assertRaises(Refusal) as caught:
            verify_scrub_claim(
                {"gpu_uuid": helpers.STUB_GPU_UUID, "method": "wipe-ish",
                 "bytes_scrubbed": self.total_bytes},
                self.gpus, self.good_post(), self.observer)
        self.assertEqual(caught.exception.code, "gpu.scrub-method")

    def test_post_scrub_residue_or_client_refuses(self):
        dirty_gpus = parse_gpu_sample(execution(gpu_row(used=12) + "\n"))
        with self.assertRaises(Refusal) as caught:
            verify_scrub_claim(
                {"gpu_uuid": helpers.STUB_GPU_UUID, "method": "full-vram-zero",
                 "bytes_scrubbed": self.total_bytes},
                self.gpus, observation(gpus=dirty_gpus), self.observer)
        self.assertEqual(caught.exception.code, "gpu.memory-not-zero")
        busy = observation(pmon={"compute_clients": 1, "graphics_clients": 0})
        with self.assertRaises(Refusal) as caught:
            verify_scrub_claim(
                {"gpu_uuid": helpers.STUB_GPU_UUID, "method": "full-vram-zero",
                 "bytes_scrubbed": self.total_bytes},
                self.gpus, busy, self.observer)
        self.assertEqual(caught.exception.code, "gpu.pmon-compute-clients")


if __name__ == "__main__":
    unittest.main()
