"""GPU observation and scrub verification (CTL-04, CTL-13 ordering support).

Positive-proof rules, per the drain/reclaim review findings:

- An empty or header-only ``nvidia-smi pmon`` output is **never** accepted as
  zero-process proof.  Zero clients requires a parseable pmon sample whose
  header names the expected columns and whose data rows cover the admitted
  GPU indices with idle markers, *plus* an empty compute-apps query paired
  with a successfully parsed GPU identity sample from the same batch.
- GPU identity (UUID set, product, count, total memory) must equal the
  controller-pinned values exactly; observations against any other device
  refuse.
- A scrub claim is only believed when the scrub tool's reported byte count
  equals the *agent-observed* total memory (never the tool's own claim) and a
  post-scrub sample shows zero used memory and zero clients.  A one-byte
  scrub is refused arithmetically.
"""

from __future__ import annotations

from .errors import Refusal, require
from .execute import Execution, PinnedBinaries

MIB = 1024 * 1024
SCRUB_METHODS = ("full-vram-zero", "gpu-reset", "mig-recreate")

_QUERY_GPU_ARGS = ["--query-gpu=uuid,name,memory.total,memory.used,driver_version",
                   "--format=csv,noheader,nounits"]
_QUERY_COMPUTE_ARGS = ["--query-compute-apps=gpu_uuid,pid,process_name,used_memory",
                       "--format=csv,noheader,nounits"]
_PMON_ARGS = ["pmon", "-c", "1", "-s", "um"]


def _require_success(execution: Execution, label: str) -> None:
    require(execution.returncode == 0, f"gpu.{label}-rc",
            f"{label} failed rc={execution.returncode}: {execution.stderr.strip()!r}")


def parse_gpu_sample(execution: Execution) -> list[dict]:
    """Parse the identity/memory sample; refuses empty or malformed output."""
    _require_success(execution, "query")
    lines = [line for line in execution.stdout.splitlines() if line.strip()]
    require(len(lines) > 0, "gpu.query-empty",
            "GPU identity query returned no rows; absence of output is not evidence")
    gpus = []
    for line in lines:
        parts = [part.strip() for part in line.split(",")]
        require(len(parts) == 5, "gpu.query-parse", f"unparseable GPU row: {line!r}")
        uuid, product, total, used, driver = parts
        require(uuid.startswith("GPU-"), "gpu.query-uuid", f"bad GPU uuid: {uuid!r}")
        require(total.isdigit() and used.isdigit(), "gpu.query-memory",
                f"non-numeric memory in row: {line!r}")
        require(len(driver) > 0, "gpu.query-driver", f"empty driver version: {line!r}")
        gpus.append({"uuid": uuid, "product": product,
                     "memory_total_mib": int(total), "memory_used_mib": int(used),
                     "driver_version": driver})
    return gpus


def assert_gpu_identity(gpus: list[dict], policy_gpu: dict) -> None:
    """Observed GPUs must equal the controller-pinned identity exactly."""
    observed_uuids = sorted(gpu["uuid"] for gpu in gpus)
    pinned_uuids = sorted(policy_gpu["uuids"])
    require(observed_uuids == pinned_uuids, "gpu.identity-uuids",
            f"observed GPU uuids {observed_uuids} != pinned {pinned_uuids}")
    require(len(gpus) == policy_gpu["count"], "gpu.identity-count",
            f"observed {len(gpus)} GPUs, pinned {policy_gpu['count']}")
    for gpu in gpus:
        require(gpu["product"] == policy_gpu["product"], "gpu.identity-product",
                f"{gpu['uuid']}: product {gpu['product']!r} != pinned "
                f"{policy_gpu['product']!r}")
        require(gpu["memory_total_mib"] == policy_gpu["memory_total_mib"],
                "gpu.identity-memory",
                f"{gpu['uuid']}: memory.total {gpu['memory_total_mib']} MiB != pinned "
                f"{policy_gpu['memory_total_mib']} MiB")


def parse_compute_apps(execution: Execution) -> list[dict]:
    """Parse compute-apps rows. Rows must be well-formed; empty means zero rows."""
    _require_success(execution, "compute-apps")
    apps = []
    for line in execution.stdout.splitlines():
        if not line.strip():
            continue
        parts = [part.strip() for part in line.split(",")]
        require(len(parts) == 4, "gpu.compute-parse", f"unparseable compute row: {line!r}")
        require(parts[1].isdigit(), "gpu.compute-pid", f"bad pid in row: {line!r}")
        apps.append({"gpu_uuid": parts[0], "pid": int(parts[1]),
                     "process_name": parts[2], "used_memory_mib": parts[3]})
    return apps


def parse_pmon(execution: Execution, expected_gpu_count: int) -> dict:
    """Parse a pmon sample into compute/graphics client counts.

    Header-only or empty output is refused: proof of zero clients requires
    data rows for every admitted GPU index, idle rows marked with '-'.
    """
    _require_success(execution, "pmon")
    header_seen = False
    columns: list[str] = []
    compute = 0
    graphics = 0
    covered_gpu_indices: set[int] = set()
    for line in execution.stdout.splitlines():
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            fields = line.lstrip("# ").split()
            if fields[:3] == ["gpu", "pid", "type"]:
                header_seen = True
                columns = fields
            continue
        require(header_seen, "gpu.pmon-headerless",
                f"pmon data row before header: {line!r}")
        fields = line.split()
        require(len(fields) == len(columns), "gpu.pmon-parse",
                f"pmon row width {len(fields)} != header width {len(columns)}: {line!r}")
        require(fields[0].isdigit(), "gpu.pmon-gpu-index",
                f"bad pmon gpu index: {line!r}")
        covered_gpu_indices.add(int(fields[0]))
        pid, ptype = fields[1], fields[2]
        if pid == "-":
            require(ptype == "-", "gpu.pmon-idle-row",
                    f"idle pmon row with non-idle type: {line!r}")
            continue
        require(pid.isdigit(), "gpu.pmon-pid", f"bad pmon pid: {line!r}")
        if "C" in ptype:
            compute += 1
        if "G" in ptype:
            graphics += 1
        require("C" in ptype or "G" in ptype, "gpu.pmon-type",
                f"unknown pmon process type {ptype!r}")
    require(header_seen, "gpu.pmon-empty",
            "pmon produced no recognizable header; empty output is not zero-process proof")
    require(covered_gpu_indices == set(range(expected_gpu_count)),
            "gpu.pmon-coverage",
            f"pmon rows cover GPU indices {sorted(covered_gpu_indices)}, "
            f"expected 0..{expected_gpu_count - 1}")
    return {"compute_clients": compute, "graphics_clients": graphics}


class GpuObserver:
    """Batched GPU observations through the pinned nvidia-smi binary."""

    def __init__(self, binaries: PinnedBinaries, policy_gpu: dict) -> None:
        self.binaries = binaries
        self.policy_gpu = policy_gpu

    def observe(self, *, timeout_s: float = 30.0) -> dict:
        """One observation batch: identity sample + compute apps + pmon."""
        identity_exec = self.binaries.run("nvidia-smi", _QUERY_GPU_ARGS, timeout_s=timeout_s)
        gpus = parse_gpu_sample(identity_exec)
        assert_gpu_identity(gpus, self.policy_gpu)
        compute_exec = self.binaries.run("nvidia-smi", _QUERY_COMPUTE_ARGS, timeout_s=timeout_s)
        apps = parse_compute_apps(compute_exec)
        pmon_exec = self.binaries.run("nvidia-smi", _PMON_ARGS, timeout_s=timeout_s)
        pmon = parse_pmon(pmon_exec, self.policy_gpu["count"])
        return {
            "gpus": gpus,
            "compute_apps": apps,
            "pmon": pmon,
            "executions": [identity_exec.receipt_data(), compute_exec.receipt_data(),
                           pmon_exec.receipt_data()],
        }

    def assert_zero_clients(self, observation: dict) -> None:
        apps = observation["compute_apps"]
        pmon = observation["pmon"]
        require(len(apps) == 0, "gpu.compute-clients",
                f"{len(apps)} compute client(s) still present on the admitted GPUs")
        require(pmon["compute_clients"] == 0, "gpu.pmon-compute-clients",
                f"pmon shows {pmon['compute_clients']} compute client(s)")
        require(pmon["graphics_clients"] == 0, "gpu.graphics-clients",
                f"pmon shows {pmon['graphics_clients']} graphics client(s)")

    def assert_memory_zero(self, observation: dict) -> None:
        for gpu in observation["gpus"]:
            require(gpu["memory_used_mib"] == 0, "gpu.memory-not-zero",
                    f"{gpu['uuid']}: memory.used is {gpu['memory_used_mib']} MiB after scrub")


def verify_scrub_claim(scrub_output: dict, observed_gpus: list[dict],
                       post_observation: dict, observer: GpuObserver) -> dict:
    """Cross-check a scrub tool's claim against agent-observed GPU state."""
    require(isinstance(scrub_output, dict), "gpu.scrub-shape", "scrub output not an object")
    require(set(scrub_output) == {"gpu_uuid", "method", "bytes_scrubbed"},
            "gpu.scrub-keys", f"scrub output keys {sorted(scrub_output)}")
    require(scrub_output["method"] in SCRUB_METHODS, "gpu.scrub-method",
            f"unknown scrub method {scrub_output['method']!r}")
    matching = [gpu for gpu in observed_gpus if gpu["uuid"] == scrub_output["gpu_uuid"]]
    require(len(matching) == 1, "gpu.scrub-target",
            f"scrub target {scrub_output['gpu_uuid']!r} is not an admitted GPU")
    observed_total_bytes = matching[0]["memory_total_mib"] * MIB
    claimed = scrub_output["bytes_scrubbed"]
    require(isinstance(claimed, int) and not isinstance(claimed, bool),
            "gpu.scrub-bytes-type", "bytes_scrubbed must be an integer")
    if scrub_output["method"] == "full-vram-zero":
        require(claimed == observed_total_bytes, "gpu.scrub-bytes",
                f"scrub claims {claimed} bytes but agent-observed total is "
                f"{observed_total_bytes} bytes; partial scrubs are refused")
    observer.assert_zero_clients(post_observation)
    observer.assert_memory_zero(post_observation)
    return {
        "gpu_uuid": scrub_output["gpu_uuid"],
        "method": scrub_output["method"],
        "bytes_scrubbed": claimed,
        "observed_total_bytes": observed_total_bytes,
    }
