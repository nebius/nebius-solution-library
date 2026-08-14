#!/usr/bin/env bash

set -euo pipefail

if [[ $# -lt 1 || $# -gt 2 ]]; then
  echo "Usage: $0 POD [CONTAINER]" >&2
  exit 2
fi

POD=$1
CONTAINER=${2:-}
NAMESPACE=${NAMESPACE:-nim-fast-start}

kubectl_args=(-n "${NAMESPACE}")
if [[ -n "${CONTAINER}" ]]; then
  kubectl_args+=(-c "${CONTAINER}")
fi

pod_json=$(kubectl -n "${NAMESPACE}" get pod "${POD}" -o json)
runtime_json=$(kubectl "${kubectl_args[@]}" exec "${POD}" -- sh -lc '
  set -eu
  python3 - <<"PY"
import importlib.metadata
import json
import subprocess

def run(command):
    result = subprocess.run(command, shell=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return result.stdout.strip()

package_prefixes = ("cuda", "nim", "openfold", "tensorrt", "torch", "triton", "vllm", "criu")
packages = []
for distribution in importlib.metadata.distributions():
    name = distribution.metadata["Name"]
    if name.lower().startswith(package_prefixes):
        packages.append(f"{name}=={distribution.version}")
packages.sort()
print(json.dumps({
    "kernel": run("uname -r"),
    "glibc": run("ldd --version | head -1"),
    "processes": run("ps -eo pid,ppid,state,rss,vsz,comm,args"),
    "packages": packages,
    "gpu": run("nvidia-smi --query-gpu=name,uuid,driver_version,memory.total,memory.used --format=csv,noheader"),
    "cuda": run("nvcc --version | tail -1"),
    "cuda_checkpoint": run("command -v cuda-checkpoint || true"),
    "criu": run("command -v criu || true"),
    "models": run("curl -fsS http://127.0.0.1:8000/v1/models || true"),
}))
PY
')

jq -n \
  --argjson pod "${pod_json}" \
  --argjson runtime "${runtime_json}" \
  '{
    pod: {
      name: $pod.metadata.name,
      uid: $pod.metadata.uid,
      namespace: $pod.metadata.namespace,
      node: $pod.spec.nodeName,
      image: $pod.status.containerStatuses[0].image,
      image_id: $pod.status.containerStatuses[0].imageID,
      container_id: $pod.status.containerStatuses[0].containerID
    },
    runtime: $runtime
  }'
