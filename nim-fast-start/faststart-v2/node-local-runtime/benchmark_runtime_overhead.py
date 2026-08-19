#!/usr/bin/env python3
"""Measure the task-owned CPU fixture as direct process and hardened OCI.

This is local runtime-overhead evidence only. It is not a GPU/model latency,
product-SLO result, node-local NVMe result, or external-platform comparator.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import platform
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
FIXTURES = HERE / "fixtures"
INPUT = b'{"value":"catalog-switch-cpu-fixture"}\n'
EXPECTED = [
    "READY",
    '{"model_id":"cpu-fixture-b","model_version":"v1","result":"semantically-valid"}',
]


def command(args: list[str], *, input_bytes: bytes | None = None, timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        args,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
        env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LANG": "C", "LC_ALL": "C"},
    )


def checked(args: list[str], *, input_bytes: bytes | None = None, timeout: int = 120) -> subprocess.CompletedProcess[bytes]:
    result = command(args, input_bytes=input_bytes, timeout=timeout)
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", errors="replace")[-2000:]
        raise RuntimeError(f"command failed ({args[0]}, exit {result.returncode}): {message}")
    return result


def validate(result: subprocess.CompletedProcess[bytes]) -> None:
    if result.returncode != 0:
        raise RuntimeError(f"fixture exited {result.returncode}")
    try:
        lines = result.stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError as exc:
        raise RuntimeError("fixture response is not UTF-8") from exc
    if lines != EXPECTED or result.stderr:
        raise RuntimeError("fixture response failed the exact semantic contract")


def percentile(values: list[float], quantile: float, minimum: int) -> float | None:
    if len(values) < minimum:
        return None
    ordered = sorted(values)
    return ordered[math.ceil(quantile * len(ordered)) - 1]


def summarize(values: list[float]) -> dict[str, Any]:
    return {
        "sample_count": len(values),
        "minimum_ms": min(values),
        "maximum_ms": max(values),
        "p50_ms": percentile(values, 0.50, 2),
        "p95_ms": percentile(values, 0.95, 20),
        "p99_ms": percentile(values, 0.99, 100),
    }


def measured(args: list[str], repetitions: int) -> list[float]:
    values: list[float] = []
    for _ in range(repetitions):
        started = time.monotonic_ns()
        result = command(args, input_bytes=INPUT)
        stopped = time.monotonic_ns()
        validate(result)
        values.append(round((stopped - started) / 1_000_000, 6))
    return values


def oci_flags(name: str) -> list[str]:
    return [
        "--name",
        name,
        "--network=none",
        "--read-only",
        "--cap-drop=ALL",
        "--security-opt=no-new-privileges:true",
        "--pids-limit=32",
        "--memory=32m",
        "--cpus=1",
        "--user=65532:65532",
        "--ipc=none",
        "--tmpfs=/tmp:rw,noexec,nosuid,nodev,size=1048576",
        "--ulimit=core=0",
        "--label",
        "mlsp.catalog-switch.task=catalog-switch-node-local-runtime",
    ]


def verify_oci_profile(inspect: dict[str, Any]) -> dict[str, Any]:
    host = inspect["HostConfig"]
    config = inspect["Config"]
    checks = {
        "non_root_uid": config["User"] == "65532:65532",
        "network_namespace_disabled": host["NetworkMode"] == "none",
        "read_only_rootfs": host["ReadonlyRootfs"] is True,
        "all_capabilities_dropped": "ALL" in (host["CapDrop"] or []),
        "no_new_privileges": "no-new-privileges:true" in (host["SecurityOpt"] or []),
        "not_privileged": host["Privileged"] is False,
        "pid_limit": host["PidsLimit"] == 32,
        "memory_limit": host["Memory"] == 32 * 1024 * 1024,
        "cpu_limit": host["NanoCpus"] == 1_000_000_000,
        "ipc_disabled": host["IpcMode"] == "none",
        "core_dump_disabled": any(
            item.get("Name") == "core" and item.get("Hard") == 0 and item.get("Soft") == 0
            for item in host["Ulimits"] or []
        ),
        "bounded_tmpfs": "/tmp" in (host["Tmpfs"] or {})
        and all(
            token in host["Tmpfs"]["/tmp"]
            for token in ("noexec", "nosuid", "nodev", "size=1048576")
        ),
        "task_label": config["Labels"].get("mlsp.catalog-switch.task")
        == "catalog-switch-node-local-runtime",
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError(f"OCI enforcement inspection failed: {', '.join(failed)}")
    return {"status": "PASS", "checks": checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repetitions", type=int, default=30)
    options = parser.parse_args()
    if not 3 <= options.repetitions <= 200:
        parser.error("--repetitions must be between 3 and 200")
    if options.output.exists() or options.output.is_symlink():
        parser.error("--output must not already exist")
    for binary in ("gcc", "docker"):
        if shutil.which(binary) is None:
            parser.error(f"required local binary is unavailable: {binary}")

    run_id = uuid.uuid4().hex[:12]
    tag = f"mlsp-csw-node-runtime-fixture:{run_id}"
    container_prefix = f"mlsp-csw-node-runtime-{run_id}"
    image_id: str | None = None
    evidence: dict[str, Any] | None = None
    cleanup: dict[str, Any] = {"containers_absent": False, "image_removed": False}
    with tempfile.TemporaryDirectory(prefix="mlsp-csw-node-runtime-build-") as raw:
        build = Path(raw)
        binary = build / "semantic-fixture"
        shutil.copyfile(FIXTURES / "Dockerfile", build / "Dockerfile")
        checked(
            [
                "gcc",
                "-std=c17",
                "-O2",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-pedantic",
                "-static",
                "-s",
                "-o",
                str(binary),
                str(FIXTURES / "semantic_fixture.c"),
            ]
        )
        direct_command = [str(binary)]
        try:
            checked(
                [
                    "docker",
                    "build",
                    "--network=none",
                    "--label",
                    "mlsp.catalog-switch.task=catalog-switch-node-local-runtime",
                    "--tag",
                    tag,
                    str(build),
                ],
                timeout=300,
            )
            image_id = checked(
                ["docker", "image", "inspect", "--format", "{{.Id}}", tag]
            ).stdout.decode().strip()
            profile_name = f"{container_prefix}-profile-probe"
            profile_id = checked(
                ["docker", "create", *oci_flags(profile_name), image_id]
            ).stdout.decode().strip()
            profile_inspect = json.loads(
                checked(["docker", "container", "inspect", profile_id]).stdout
            )[0]
            profile_receipt = verify_oci_profile(profile_inspect)
            checked(["docker", "container", "rm", profile_id])
            direct_values = measured(direct_command, options.repetitions)
            oci_values: list[float] = []
            oci_commands: list[list[str]] = []
            for index in range(options.repetitions):
                name = f"{container_prefix}-{index:03d}"
                oci_command = [
                    "docker",
                    "run",
                    "--rm",
                    *oci_flags(name),
                    "--interactive",
                    image_id,
                ]
                started = time.monotonic_ns()
                result = command(oci_command, input_bytes=INPUT)
                stopped = time.monotonic_ns()
                validate(result)
                oci_values.append(round((stopped - started) / 1_000_000, 6))
                oci_commands.append(oci_command)
            inspect = json.loads(checked(["docker", "image", "inspect", image_id]).stdout)[0]
            evidence = {
                "schema": "catalog-switch-runtime-overhead/v1",
                "classification": "cpu-local-runtime-overhead-not-product-or-gpu-evidence",
                "run_id": run_id,
                "fixture": {
                    "source_sha256": hashlib.sha256((FIXTURES / "semantic_fixture.c").read_bytes()).hexdigest(),
                    "input_sha256": hashlib.sha256(INPUT).hexdigest(),
                    "semantic_contract": EXPECTED,
                },
                "environment": {
                    "kernel": platform.release(),
                    "machine": platform.machine(),
                    "docker_server_version": checked(
                        ["docker", "version", "--format", "{{.Server.Version}}"]
                    ).stdout.decode().strip(),
                    "containerd_version": checked(["containerd", "--version"]).stdout.decode().strip(),
                    "runc_version": checked(["runc", "--version"]).stdout.decode().splitlines()[0],
                    "task_owned_image_id": image_id,
                    "task_owned_image_user": inspect["Config"]["User"],
                    "image_parent": inspect.get("Parent", ""),
                },
                "direct_process": {
                    "command": direct_command,
                    "raw_total_ms": direct_values,
                    "summary": summarize(direct_values),
                },
                "oci_containerd_runc": {
                    "command_template": [
                        value if not value.startswith(container_prefix) else f"{container_prefix}-NNN"
                        for value in oci_commands[0]
                    ],
                    "raw_total_ms": oci_values,
                    "summary": summarize(oci_values),
                    "enforcement_inspection": profile_receipt,
                    "enforced_flags": [
                        "network=none",
                        "read-only",
                        "cap-drop=ALL",
                        "no-new-privileges",
                        "pids-limit=32",
                        "memory=32m",
                        "cpus=1",
                        "uid=65532",
                        "ipc=none",
                        "tmpfs=/tmp:noexec,nosuid,nodev,size=1MiB",
                        "core=0",
                    ],
                },
                "microvm": {
                    "measured": False,
                    "reason": "Firecracker absent and its documented device model does not expose an H100 passthrough path; no proxy timing invented.",
                },
            }
        finally:
            listed = command(
                [
                    "docker",
                    "ps",
                    "--all",
                    "--quiet",
                    "--filter",
                    f"name=^{container_prefix}-",
                ]
            ).stdout.decode().split()
            if listed:
                checked(["docker", "container", "rm", "--force", *listed])
            cleanup["containers_absent"] = not command(
                ["docker", "ps", "--all", "--quiet", "--filter", f"name=^{container_prefix}-"]
            ).stdout.strip()
            if image_id:
                checked(["docker", "image", "rm", tag])
                cleanup["image_removed"] = command(
                    ["docker", "image", "inspect", image_id]
                ).returncode != 0
    if evidence is None:
        raise RuntimeError("runtime-overhead measurement produced no evidence")
    evidence["cleanup"] = cleanup
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(options.output), "cleanup": cleanup}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
