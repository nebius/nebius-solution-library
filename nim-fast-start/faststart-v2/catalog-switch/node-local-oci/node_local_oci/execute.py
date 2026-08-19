"""Real subprocess execution of controller-pinned binaries.

There is exactly one way this package runs an external program: resolve the
binary from the controller-signed admission policy, verify the bytes on disk
hash to the pinned sha256 at call time, and ``subprocess.run`` the absolute
real path with ``shell=False``.  There is no transport abstraction, no fake
executor class, and no CLI flag that changes how commands run; the only way
to alter behaviour is to present a differently *signed* policy, which is the
controller's authority, not the agent's or the benchmark client's.

Every execution is returned as an ``Execution`` record (argv, rc, stdout,
stderr, monotonic start/end) so receipts always carry what actually ran.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

from .errors import Refusal, require


@dataclass(frozen=True)
class Execution:
    binary: str
    resolved_path: str
    binary_sha256: str
    argv: tuple[str, ...]
    returncode: int
    stdout: str
    stderr: str
    started_monotonic_ns: int
    ended_monotonic_ns: int

    def receipt_data(self) -> dict:
        return {
            "binary": self.binary,
            "resolved_path": self.resolved_path,
            "binary_sha256": self.binary_sha256,
            "argv": list(self.argv),
            "returncode": self.returncode,
            "stdout_sha256": hashlib.sha256(self.stdout.encode("utf-8")).hexdigest(),
            "stderr_sha256": hashlib.sha256(self.stderr.encode("utf-8")).hexdigest(),
            "started_monotonic_ns": self.started_monotonic_ns,
            "ended_monotonic_ns": self.ended_monotonic_ns,
        }


def _sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with open(path, "rb") as handle:
        while True:
            chunk = handle.read(1 << 20)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


class PinnedBinaries:
    """Binaries admitted by the controller policy, hash-verified at every call."""

    def __init__(self, policy: dict) -> None:
        self._pins = policy["binaries"]

    def resolve(self, name: str) -> tuple[str, str]:
        require(name in self._pins, "execute.unpinned-binary",
                f"binary {name!r} is not pinned by the admitted policy")
        pin = self._pins[name]
        path = Path(pin["path"])
        require(path.is_absolute(), "execute.binary-relative", f"{path}")
        real = path.resolve(strict=False)
        require(real.is_file(), "execute.binary-missing", f"{real} is not a file")
        require(os.access(real, os.X_OK), "execute.binary-not-executable", f"{real}")
        digest = _sha256_file(real)
        require(digest == pin["sha256"], "execute.binary-drift",
                f"{name}: on-disk sha256 {digest} != pinned {pin['sha256']}")
        return str(real), digest

    def run(self, name: str, args: list[str], *, timeout_s: float) -> Execution:
        resolved, digest = self.resolve(name)
        for arg in args:
            require(isinstance(arg, str), "execute.argv-type", "argv entries must be str")
        argv = [resolved, *args]
        started = time.monotonic_ns()
        try:
            completed = subprocess.run(
                argv, capture_output=True, text=True, timeout=timeout_s,
                shell=False, check=False,
            )
        except subprocess.TimeoutExpired as error:
            raise Refusal("execute.timeout",
                          f"{name} exceeded {timeout_s}s: {argv}") from error
        except OSError as error:
            raise Refusal("execute.spawn", f"{name}: {error}") from error
        ended = time.monotonic_ns()
        return Execution(
            binary=name,
            resolved_path=resolved,
            binary_sha256=digest,
            argv=tuple(argv),
            returncode=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            started_monotonic_ns=started,
            ended_monotonic_ns=ended,
        )
