from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


TEST_DIR = Path(__file__).resolve().parent
MODULE_DIR = TEST_DIR.parent
sys.path.insert(0, str(MODULE_DIR))

import render  # noqa: E402
import aggregate_results  # noqa: E402
import artifact_variant  # noqa: E402
import bind_target  # noqa: E402
import prewarm_artifact  # noqa: E402
import render_capture  # noqa: E402
import validate_rfdiffusion as validator  # noqa: E402


POD_UID = "11111111-1111-4111-8111-111111111111"
CONTAINER_ID = "containerd://" + "a" * 64
MANIFEST_SHA256 = "b" * 64


def contract() -> dict[str, Any]:
    return json.loads(
        (MODULE_DIR / "restore-interface.performance.json").read_text(encoding="utf-8")
    )


def run_config(mode: str = "direct", run_id: str = "rfd-offline-1") -> dict[str, Any]:
    artifact = render.PROFILE["artifacts"][mode]
    return {
        "schema": render.RUN_SCHEMA,
        "demand_at": "2026-08-18T06:00:00.000000Z",
        "run_id": run_id,
        "target_node": render.TARGET_NODE,
        "checkpoint_id": artifact["checkpoint_id"],
        "artifact_version": artifact["artifact_version"],
        "artifact_manifest_sha256": MANIFEST_SHA256,
        "artifact_pvc": render.PROFILE["storage"]["artifact_pvc"],
        "cache_pvc": render.PROFILE["storage"]["cache_pvc"],
        "image_io_mode": mode,
    }


def generated_pdb(residue_count: int = 67) -> str:
    lines: list[str] = []
    serial = 1
    for residue in range(1, residue_count + 1):
        ca_x = (residue - 1) * 3.8
        for atom, x, element in (
            ("N", ca_x - 1.2, "N"),
            ("CA", ca_x, "C"),
            ("C", ca_x + 1.2, "C"),
        ):
            lines.append(
                f"ATOM  {serial:5d} {atom:>4s} ALA A{residue:4d}    "
                f"{x:8.3f}{0.0:8.3f}{0.0:8.3f}  1.00 20.00           {element:>2s}"
            )
            serial += 1
    return "\n".join(lines) + "\n"


def response_for(probe: validator.Probe, residue_count: int = 67) -> dict[str, Any]:
    return {
        "output_pdb": generated_pdb(residue_count),
        "elapsed_ms": 5800,
    }


def live_target() -> dict[str, Any]:
    run = render.validate_run(run_config())
    approved = render.validate_contract(contract())
    documents = render.render_target(run, approved)
    pod = copy.deepcopy(next(item for item in documents if item["kind"] == "Pod"))
    pod["metadata"]["uid"] = POD_UID
    pod["spec"].update(
        {
            "nodeName": run["target_node"],
            "dnsPolicy": "ClusterFirst",
            "schedulerName": "default-scheduler",
            "serviceAccount": "default",
            "serviceAccountName": "default",
        }
    )
    for omitted_false in ("hostIPC", "hostNetwork", "hostPID"):
        pod["spec"].pop(omitted_false, None)
    pod["status"] = {
        "phase": "Running",
        "qosClass": "Guaranteed",
        "podIP": "10.126.62.248",
        "podIPs": [{"ip": "10.126.62.248"}],
        "conditions": [{"type": "PodScheduled", "status": "True"}],
        "containerStatuses": [
            {
                "name": render.CONTAINER_NAME,
                "containerID": CONTAINER_ID,
                "image": render.NIM_IMAGE,
                "imageID": render.NIM_IMAGE,
                "state": {"running": {"startedAt": "2026-08-18T06:00:01Z"}},
            }
        ],
    }
    return pod


def trial_summary(index: int, mode: str = "direct") -> dict[str, Any]:
    return {
        "schema": "archvteams.nebius.ai/rfdiffusion-native-trial-summary/v1",
        "run_id": f"run-{index}",
        "status": "PASS",
        "model": "RFdiffusion",
        "image": render.NIM_IMAGE,
        "gpu_topology": "1x NVIDIA H100, full GPU, non-MIG",
        "image_io_mode": mode,
        "checkpoint_id": render.PROFILE["artifacts"][mode]["checkpoint_id"],
        "artifact_manifest_sha256": MANIFEST_SHA256,
        "pod_uid": f"11111111-1111-4111-8111-{index:012d}",
        "pod_spec_sha256": f"{index}" * 64,
        "semantic_request_count": 2,
        "semantic_response_sha256": ["c" * 64, "d" * 64],
        "worker_receipt": {"status": "succeeded", "duration_ms": 50_000 + index * 100},
        "semantic": {
            "status": "PASS",
            "request_count": 2,
            "passed_case_count": 2,
            "failed_case_count": 0,
            "total_elapsed_seconds": 1.5 + index / 10,
            "cases": [
                {
                    "status": "PASS",
                    "ok": True,
                    "http_status": 200,
                    "run_id": f"run-{index}-semantic-{offset + 1}",
                    "request_sha256": request_sha256,
                    "response_sha256": response_sha256,
                    "invariant": {
                        "random_seed": seed,
                        "fixture_sha256": render.PROFILE["semantic_profile"]["fixture_sha256"],
                        "backbone": {
                            "residue_count": 67 + offset,
                            "complete_backbone_residue_count": 67 + offset,
                            "ca_count": 67 + offset,
                            "adjacent_ca_pair_count": 65 + offset,
                        },
                    },
                }
                for offset, (seed, request_sha256, response_sha256) in enumerate(
                    zip(
                        render.PROFILE["semantic_profile"]["request_seeds"],
                        render.PROFILE["semantic_profile"]["request_body_sha256"],
                        ("c" * 64, "d" * 64),
                        strict=True,
                    )
                )
            ],
        },
        "demand_to_two_semantic_seconds": 65.0 + index,
    }


class RFdiffusionSemanticTests(unittest.TestCase):
    def test_requests_are_exactly_two_distinct_seeded_oracles(self) -> None:
        fixture = (MODULE_DIR / "fixtures/1UBQ.pdb").read_bytes()
        probes = validator.build_probes(("semantic-a", "semantic-b"), fixture)
        self.assertEqual(2, len(probes))
        self.assertEqual([2370, 2371], [item.random_seed for item in probes])
        self.assertEqual([15, 15], [item.payload["diffusion_steps"] for item in probes])
        self.assertEqual(
            render.PROFILE["semantic_profile"]["request_body_sha256"],
            [item.expected_request_sha256 for item in probes],
        )
        self.assertNotEqual(probes[0].random_seed, probes[1].random_seed)
        with self.assertRaises(validator.SetupFailure):
            validator.build_probes(("only-one",), fixture)
        with self.assertRaises(validator.SetupFailure):
            validator.build_probes(("same", "same"), fixture)
        with self.assertRaises(validator.SetupFailure):
            validator.build_probes(("a", "b"), fixture + b"drift")

    def test_accepts_retained_response_shape(self) -> None:
        fixture = (MODULE_DIR / "fixtures/1UBQ.pdb").read_bytes()
        for index, probe in enumerate(validator.build_probes(("valid-a", "valid-b"), fixture)):
            invariant = validator.validate_response(response_for(probe), probe)
            self.assertEqual(probe.random_seed, invariant["random_seed"])
            self.assertEqual(67, invariant["backbone"]["residue_count"])
            self.assertEqual(67, invariant["backbone"]["complete_backbone_residue_count"])
            self.assertEqual(67, invariant["backbone"]["ca_count"])
            self.assertGreaterEqual(invariant["backbone"]["adjacent_ca_pair_count"], 15)

    def test_rejects_nonsemantic_or_shape_drift(self) -> None:
        fixture = (MODULE_DIR / "fixtures/1UBQ.pdb").read_bytes()
        probe = validator.build_probes(("reject-a", "reject-b"), fixture)[0]
        mutations = [
            lambda value: value.update(output_pdb=generated_pdb(60)),
            lambda value: value.update(output_pdb=generated_pdb(72)),
            lambda value: value.update(output_pdb="ATOM short"),
            lambda value: value.update(error="failed"),
            lambda value: value.update(elapsed_ms=float("nan")),
            lambda value: value.update(elapsed_ms=-1),
            lambda value: value.pop("output_pdb"),
        ]
        for mutate in mutations:
            value = response_for(probe)
            mutate(value)
            with self.assertRaises(validator.SemanticFailure):
                validator.validate_response(value, probe)

    def test_readiness_accepts_only_reviewed_shapes(self) -> None:
        self.assertTrue(validator.readiness_is_ready(b"true"))
        self.assertTrue(validator.readiness_is_ready(b'{"status":"ready"}'))
        for body in (b"false", b'{"status":"loading"}', b"ready", b"{}"):
            self.assertFalse(validator.readiness_is_ready(body))


class RFdiffusionRenderAndBindingTests(unittest.TestCase):
    def test_target_probe_and_worker_are_production_shaped(self) -> None:
        run = render.validate_run(run_config())
        approved = render.validate_contract(contract())
        target_documents = render.render_target(run, approved)
        self.assertEqual([], render.lint_documents(target_documents))
        target = next(item for item in target_documents if item["kind"] == "Pod")
        target_container = target["spec"]["containers"][0]
        self.assertEqual(render.NIM_IMAGE, target_container["image"])
        self.assertEqual(render.PROFILE["pod_profile"]["requests"], target_container["resources"]["requests"])
        self.assertEqual(render.PROFILE["pod_profile"]["limits"], target_container["resources"]["limits"])
        self.assertNotIn("nodeName", target["spec"])
        self.assertEqual([{"name": "nvcrio-cred"}], target["spec"]["imagePullSecrets"])
        self.assertEqual(
            render.PROFILE["model"]["cache_path"],
            next(item["mountPath"] for item in target_container["volumeMounts"] if item["name"] == "nim-cache"),
        )
        services = [item for item in target_documents if item["kind"] == "Service"]
        self.assertEqual(2, len(services))
        self.assertTrue(all(item["spec"]["type"] == "ClusterIP" for item in services))

        binding, _ = bind_target.build_binding(
            live_target(), run, approved, "2026-08-18T06:00:02Z"
        )
        probe_documents = render.render_probe(run, approved, binding)
        worker_documents = render.render_restore(run, approved, binding)
        self.assertEqual([], render.lint_documents(probe_documents))
        self.assertEqual([], render.lint_documents(worker_documents))
        probe = next(item for item in probe_documents if item["kind"] == "Job")
        probe_container = probe["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(2, probe_container["args"].count("--run-id"))
        self.assertFalse(render._contains_gpu(probe_container["resources"]))
        self.assertIn(f"http://rfd-canary-{run['run_id']}:8000", probe_container["args"])
        self.assertIn("--fixture", probe_container["args"])
        self.assertIn("/validator/1UBQ.pdb", probe_container["args"])
        probe_config = next(item for item in probe_documents if item["kind"] == "ConfigMap")
        self.assertEqual(
            validator.FIXTURE_SHA256,
            hashlib.sha256(probe_config["data"]["1UBQ.pdb"].encode("ascii")).hexdigest(),
        )
        worker = next(item for item in worker_documents if item["kind"] == "Job")
        worker_container = worker["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(render.WORKER_GATE["worker_image"], worker_container["image"])
        self.assertFalse(render._contains_gpu(worker_container["resources"]))
        self.assertTrue(worker_container["securityContext"]["privileged"])

    def test_live_binding_preserves_original_podspec_digest(self) -> None:
        pod = live_target()
        run = render.validate_run(run_config())
        approved = render.validate_contract(contract())
        binding, patch = bind_target.build_binding(
            pod, run, approved, "2026-08-18T06:00:02Z"
        )
        expected = bind_target.base_bind.pod_spec_sha256(pod["spec"])
        self.assertEqual(expected, binding["pod_spec_sha256"])
        self.assertEqual(render.NIM_IMAGE, binding["image_id"])
        self.assertEqual(render.TARGET_NODE, binding["node"])
        self.assertEqual(
            "/kubepods.slice/kubepods-pod11111111_1111_4111_8111_111111111111.slice/"
            + "cri-containerd-" + "a" * 64 + ".scope",
            binding["cgroup"],
        )
        self.assertEqual(POD_UID, patch[0]["value"])
        self.assertEqual(expected, patch[1]["value"])

    def test_binding_rejects_image_and_node_drift(self) -> None:
        run = render.validate_run(run_config())
        approved = render.validate_contract(contract())
        wrong_image = live_target()
        wrong_image["spec"]["containers"][0]["image"] = "example.test/rfdiffusion@sha256:" + "0" * 64
        with self.assertRaisesRegex(bind_target.base_bind.BindingError, "pinned RFdiffusion image"):
            bind_target.build_binding(wrong_image, run, approved, "2026-08-18T06:00:02Z")
        wrong_node = live_target()
        wrong_node["spec"]["nodeName"] = "different-node"
        with self.assertRaisesRegex(bind_target.base_bind.BindingError, "pinned H100"):
            bind_target.build_binding(wrong_node, run, approved, "2026-08-18T06:00:02Z")

    def test_run_config_binds_mode_to_checkpoint(self) -> None:
        render.validate_run(run_config("direct"))
        render.validate_run(run_config("buffered"))
        mismatch = run_config("direct")
        mismatch["checkpoint_id"] = render.PROFILE["artifacts"]["buffered"]["checkpoint_id"]
        with self.assertRaises(render.RenderError):
            render.validate_run(mismatch)
        mismatch = run_config("direct")
        mismatch["target_node"] = "different-node"
        with self.assertRaises(render.RenderError):
            render.validate_run(mismatch)


class RFdiffusionCaptureAndArtifactTests(unittest.TestCase):
    def test_capture_renderers_pin_native_inputs(self) -> None:
        storage = render_capture.render_storage()
        self.assertEqual(2, len(storage))
        self.assertEqual(
            {render.PROFILE["storage"]["artifact_pvc"], render.PROFILE["storage"]["cache_pvc"]},
            {item["metadata"]["name"] for item in storage},
        )
        donor_documents = render_capture.render_donor("h100-r1")
        render_capture.validate_documents(donor_documents)
        donor = next(item for item in donor_documents if item["kind"] == "Job")
        donor_config = next(item for item in donor_documents if item["kind"] == "ConfigMap")
        container = donor["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(render.NIM_IMAGE, container["image"])
        self.assertEqual(2, container["args"][0].count("--run-id"))
        self.assertIn("--fixture /validator/1UBQ.pdb", container["args"][0])
        cache_verifier = donor["spec"]["template"]["spec"]["initContainers"][0]
        self.assertFalse(render._contains_gpu(cache_verifier["resources"]))
        self.assertEqual(
            cache_verifier["resources"]["requests"],
            cache_verifier["resources"]["limits"],
        )
        self.assertIn("--cache-only", cache_verifier["args"])
        self.assertIn(
            render.PROFILE["retained_evidence"]["cache_tree_sha256"],
            cache_verifier["args"],
        )
        self.assertEqual(
            validator.FIXTURE_SHA256,
            hashlib.sha256(donor_config["data"]["1UBQ.pdb"].encode("ascii")).hexdigest(),
        )
        self.assertNotIn("nodeName", donor["spec"]["template"]["spec"])
        agent = render_capture.render_agent("h100-r1")[0]
        self.assertEqual(render.WORKER_GATE["worker_image"], agent["spec"]["containers"][0]["image"])
        content = render_capture.render_content(
            "h100-r1", "rfd-donor-h100-r1-abcde", POD_UID
        )[0]
        self.assertEqual(POD_UID, content["spec"]["source"]["podRef"]["uid"])
        self.assertEqual([render.CONTAINER_NAME], content["spec"]["source"]["podRef"]["containers"])
        holder_documents = render_capture.render_holder(
            "h100-r1", "direct", MANIFEST_SHA256, 92, 23_364_237_452
        )
        render_capture.validate_documents(holder_documents)
        holder = next(item for item in holder_documents if item["kind"] == "Pod")
        self.assertEqual(
            render.PROFILE["retained_evidence"]["cache_tree_sha256"],
            holder["metadata"]["annotations"]["archvteams.nebius.ai/cache-tree-sha256"],
        )
        holder_args = holder["spec"]["containers"][0]["args"]
        self.assertIn("--cache-tree-sha256", holder_args)
        self.assertIn(render.PROFILE["retained_evidence"]["cache_tree_sha256"], holder_args)

    def _create_direct_artifact(self, root: Path) -> tuple[Path, str, int, int]:
        artifact = root / artifact_variant.SOURCE_ID / "versions" / "1"
        artifact.mkdir(parents=True)
        manifest = (
            f"checkpointId: {artifact_variant.SOURCE_ID}\n"
            "spec:\n"
            "  containers:\n"
            "    - name: rfdiffusion\n"
            "      criu:\n"
            "        imageIoMode: direct\n"
        ).encode("ascii")
        (artifact / "manifest.yaml").write_bytes(manifest)
        (artifact / "rootfs-diff.tar").write_bytes(b"rootfs")
        (artifact / "pages-1.img").write_bytes(b"pages" * 100)
        members, total = artifact_variant.inventory(artifact)
        return artifact, hashlib.sha256(manifest).hexdigest(), len(members), total

    def test_buffered_variant_hardlinks_payload_and_changes_only_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source, manifest_sha256, count, total = self._create_direct_artifact(root)
            result = artifact_variant.build_variant(root, manifest_sha256, count, total)
            destination = root / artifact_variant.DESTINATION_ID / "versions" / "1"
            self.assertEqual("PASS", result["status"])
            self.assertEqual("buffered", result["image_io_mode"])
            self.assertIn(b"imageIoMode: buffered", (destination / "manifest.yaml").read_bytes())
            self.assertNotIn(b"imageIoMode: direct", (destination / "manifest.yaml").read_bytes())
            for name in ("rootfs-diff.tar", "pages-1.img"):
                self.assertEqual((source / name).stat().st_ino, (destination / name).stat().st_ino)
            with self.assertRaises(artifact_variant.VariantError):
                artifact_variant.build_variant(root, manifest_sha256, count, total)

    def test_prewarm_distinguishes_direct_metadata_from_buffered_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            direct, direct_sha, direct_count, direct_total = self._create_direct_artifact(root)
            direct_result = prewarm_artifact.verify_and_prewarm(
                direct, direct_sha, direct_count, direct_total, "direct"
            )
            variant = artifact_variant.build_variant(
                root, direct_sha, direct_count, direct_total
            )
            buffered = root / artifact_variant.DESTINATION_ID / "versions" / "1"
            buffered_members, buffered_total = artifact_variant.inventory(buffered)
            buffered_result = prewarm_artifact.verify_and_prewarm(
                buffered,
                variant["manifest_sha256"],
                len(buffered_members),
                buffered_total,
                "buffered",
            )
            self.assertFalse(direct_result["payload_read"])
            self.assertTrue(buffered_result["payload_read"])

    def test_holder_verifies_the_exact_recursive_cache_tree(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cache = root / "cache"
            required = cache / render.PROFILE["retained_evidence"]["critical_cache_file"]
            required.parent.mkdir(parents=True)
            required.write_bytes(b"igso-cache")
            extra = cache / "models/model.bin"
            extra.parent.mkdir(parents=True)
            extra.write_bytes(b"weights")
            members = []
            for path in sorted(item for item in cache.rglob("*") if item.is_file()):
                relative = path.relative_to(cache).as_posix()
                payload = path.read_bytes()
                members.append((relative, len(payload), hashlib.sha256(payload).hexdigest()))
            tree = hashlib.sha256()
            for relative, size, digest in members:
                tree.update(f"{relative}\0{size}\0{digest}\n".encode())
            result = prewarm_artifact.verify_cache(
                cache,
                tree.hexdigest(),
                len(members),
                sum(size for _, size, _ in members),
                render.PROFILE["retained_evidence"]["critical_cache_file"],
            )
            self.assertTrue(result["payload_read"])
            self.assertEqual("PASS", result["status"])
            with self.assertRaises(prewarm_artifact.PrewarmError):
                prewarm_artifact.verify_cache(
                    cache,
                    "0" * 64,
                    len(members),
                    sum(size for _, size, _ in members),
                    render.PROFILE["retained_evidence"]["critical_cache_file"],
                )


class RFdiffusionAggregateAndProvenanceTests(unittest.TestCase):
    def test_n3_aggregate_requires_three_matched_semantic_passes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = []
            for index in range(1, 4):
                path = root / f"trial-{index}.json"
                path.write_text(json.dumps(trial_summary(index)), encoding="utf-8")
                paths.append(path)
            result = aggregate_results.aggregate(paths, "direct")
            self.assertEqual("PASS", result["status"])
            self.assertEqual(3, result["trial_count"])
            self.assertEqual(6, result["semantic_pass_count"])
            self.assertEqual(67.0, result["demand_to_two_semantic_seconds"]["median"])
            self.assertEqual(50.2, result["worker_restore_seconds"]["median"])

            drifted = json.loads(paths[2].read_text())
            drifted["semantic"]["cases"][1]["request_sha256"] = "0" * 64
            paths[2].write_text(json.dumps(drifted), encoding="utf-8")
            with self.assertRaises(aggregate_results.AggregateError):
                aggregate_results.aggregate(paths, "direct")

    def test_worker_gate_matches_checked_in_provenance_and_is_not_release_ready(self) -> None:
        gate = render.WORKER_GATE
        provenance = (MODULE_DIR / gate["provenance_path"]).resolve()
        self.assertTrue(provenance.is_file())
        self.assertEqual(
            gate["provenance_sha256"], hashlib.sha256(provenance.read_bytes()).hexdigest()
        )
        self.assertTrue(gate["performance_validation_ready"])
        self.assertFalse(gate["release_ready"])
        self.assertEqual(
            gate["tool_bundle_manifest_sha256"], contract()["tool_bundle"]["content_sha256"]
        )

    def test_runner_pins_contract_and_validator_bytes(self) -> None:
        runner = (MODULE_DIR / "run_one_provisioned_trial.sh").read_text(encoding="utf-8")
        contract_sha256 = hashlib.sha256(
            (MODULE_DIR / "restore-interface.performance.json").read_bytes()
        ).hexdigest()
        validator_sha256 = hashlib.sha256(
            (MODULE_DIR / "validate_rfdiffusion.py").read_bytes()
        ).hexdigest()
        self.assertIn(f'expected_contract_sha256="{contract_sha256}"', runner)
        self.assertIn(f'expected_validator_sha256="{validator_sha256}"', runner)
        self.assertEqual(validator_sha256, contract()["validator_sha256"])

    def test_profile_preserves_retained_evidence_and_defers_new_manifests(self) -> None:
        profile = render.PROFILE
        self.assertEqual(23_364_237_452, profile["retained_evidence"]["legacy_checkpoint_regular_file_bytes"])
        self.assertEqual(24.593, profile["retained_evidence"]["legacy_buffered_n3_median_seconds"])
        self.assertEqual(
            "18f827dcb8c2f8ffbd27f2b4f396fcb9d5df07b492965764a5ecd5f1d57a9e4e",
            profile["retained_evidence"]["cache_tree_sha256"],
        )
        self.assertEqual(1, profile["hardware"]["gpu_count"])
        self.assertFalse(profile["hardware"]["mig_allowed"])
        self.assertIsNone(profile["artifacts"]["direct"]["manifest_sha256"])
        self.assertIsNone(profile["artifacts"]["buffered"]["manifest_sha256"])
        prior = json.loads((MODULE_DIR / "prior-evidence.json").read_text())
        self.assertFalse(prior["production_native_qualified"])
        self.assertFalse(prior["durable_artifacts"]["checkpoint"]["eligible_as_native_artifact"])


if __name__ == "__main__":
    unittest.main()
