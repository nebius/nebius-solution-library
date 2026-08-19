#!/usr/bin/env python3
"""Modal app template: run an unmodified NVIDIA NIM behind its own HTTP API.

STATUS: UNVALIDATED. This template cannot be deployed or tested until the
user provides Modal workspace credentials (see COMPATIBILITY_PREFLIGHT.md,
gate G0). It is committed so the compatibility smoke (gate G1) starts from a
reviewed artifact. Offline tests only check that this file parses.

Design rules enforced here:
- The NIM image is pinned by digest and launched via its own entrypoint,
  unmodified — the workload is never rewritten for a faster number.
- No request-specific work happens before T0; warm behavior comes only from
  the declared per-cohort autoscaler configuration set at deploy time.
- Interior phase timestamps come from container-side logs with explicit
  provenance; the client harness owns T0 and the completion boundary.
"""

from __future__ import annotations

import os
import subprocess

import modal

# --- per-cohort configuration (edited per EXPERIMENT_PLAN.md mode matrix) ---
PILOT = os.environ.get("PILOT", "of2")
MODE = os.environ.get("MODE", "m0")
APP_NAME = f"mlspec-catswitch-{PILOT}-{MODE}"
# Digest placeholder is filled from `docker buildx imagetools inspect` output
# at gate G1 and recorded in the run's event JSONL (`image_ref`).
NIM_IMAGE_REF = os.environ.get(
    "NIM_IMAGE_REF",
    "nvcr.io/nim/deepmind/openfold2:2.5.0@sha256:REPLACE_AT_G1",
)
NIM_PORT = 8000
GPU = os.environ.get("MODAL_GPU", "A100-80GB!")
REGION = os.environ.get("MODAL_REGION", "eu")

app = modal.App(APP_NAME)

nim_image = modal.Image.from_registry(
    NIM_IMAGE_REF,
    secret=modal.Secret.from_name("mlspec-catswitch-ngc"),
    # add_python is decided at G1: only if the NIM image's own python cannot
    # host the Modal client runtime; recorded either way.
)

weights_volume = modal.Volume.from_name(
    f"mlspec-catswitch-{PILOT}-cache", create_if_missing=True
)


@app.cls(
    image=nim_image,
    gpu=GPU,
    region=REGION,
    volumes={"/opt/nim/.cache": weights_volume},
    secrets=[modal.Secret.from_name("mlspec-catswitch-ngc")],
    timeout=1800,
    retries=0,  # retries are measured, not hidden: the client owns attempts
    enable_memory_snapshot=False,  # toggled per mode M1/M2 only
    max_containers=2,
    min_containers=0,  # M3 sets 1 at deploy time
    scaledown_window=60,
)
class NimServer:
    @modal.web_server(NIM_PORT, startup_timeout=1800)
    def serve(self) -> None:
        # Launch the image's own entrypoint verbatim. The exact command is
        # read from the image config at G1 and asserted here so any deviation
        # from the OCI-defined ENTRYPOINT/CMD is explicit evidence.
        entrypoint = os.environ.get("NIM_ENTRYPOINT", "/opt/nim/start_server.sh")
        subprocess.Popen(  # noqa: S603 - the pinned NIM's own start command
            [entrypoint],
            env={**os.environ, "NIM_SERVED_PORT": str(NIM_PORT)},
        )
