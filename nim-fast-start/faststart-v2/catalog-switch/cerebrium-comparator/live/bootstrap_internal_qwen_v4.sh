#!/usr/bin/env bash
set -euo pipefail

readonly lease_id='catswitch-qwen3-h100-scout-v4-20260819'
readonly marker='CATSWITCH_QWEN3_H100_V4_OK'
readonly image='vllm/vllm-openai@sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d'
readonly image_digest='sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d'

# shellcheck disable=SC2317
on_error() {
  local rc=$?
  echo "CATSWITCH_BOOTSTRAP_V4_FAILED rc=${rc}" >/dev/console
  exit "${rc}"
}

exec > >(tee -a /var/log/catswitch-bootstrap-v4.log | logger -t catswitch-bootstrap-v4 -s 2>/dev/console) 2>&1
trap on_error ERR

# The image must already provide the container/GPU runtime. The v4 network
# contract intentionally has no TCP/80 package-install exception.
for binary in docker nvidia-smi python3 systemctl ss; do
  command -v "${binary}" >/dev/null 2>&1 || {
    echo "required preinstalled binary is missing: ${binary}" >&2
    exit 1
  }
done
systemctl enable --now docker
docker info --format '{{json .Runtimes}}' | grep -q 'nvidia'

install -d -m 0755 /opt/catswitch /var/lib/catswitch/model /var/lib/catswitch/evidence /run/catswitch
test -s /run/catswitch/bearer-token
test "$(stat -c '%a' /run/catswitch/bearer-token)" = '600'

gpu_proof="$({ nvidia-smi --query-gpu=uuid,name --format=csv,noheader,nounits; } | python3 -c '
import base64, json, re, sys
rows=[]
for line in sys.stdin:
    fields=[item.strip() for item in line.strip().split(",", 1)]
    if len(fields)==2 and fields[0]: rows.append(fields)
if len(rows) != 1: raise SystemExit("observed GPU count is not exactly one")
uuid, name = rows[0]
if not re.fullmatch(r"NVIDIA H100(?: |$).*", name): raise SystemExit("observed GPU is not H100")
if not re.fullmatch(r"GPU-[A-Za-z0-9-]{8,}", uuid): raise SystemExit("observed GPU UUID is invalid")
raw=json.dumps({"count":1,"names":[name],"uuids":[uuid]},sort_keys=True,separators=(",",":")).encode()
print(base64.urlsafe_b64encode(raw).decode().rstrip("="))
')"
echo "CATSWITCH_GPU_PROOF_B64=${gpu_proof}" | tee /dev/console

docker pull "${image}"
repo_digests="$(docker image inspect "${image}" --format '{{json .RepoDigests}}')"
case "${repo_digests}" in
  *"@${image_digest}"*) ;;
  *) echo 'pulled image does not advertise the frozen manifest digest' >&2; exit 1 ;;
esac

docker run --rm \
  -v /var/lib/catswitch/model:/model \
  --entrypoint python3 \
  "${image}" \
  -c 'from huggingface_hub import snapshot_download; snapshot_download(repo_id="Qwen/Qwen3-8B", revision="b968826d9c46dd6066d109eabc6255188de91218", local_dir="/model")'

python3 - <<'PY'
import hashlib
import json
from pathlib import Path

root = Path('/var/lib/catswitch/model')
observed = {
    'repository_bytes': sum(
        path.stat().st_size
        for path in root.rglob('*')
        if path.is_file() and '.cache' not in path.parts
    ),
    'tokenizer_sha256': hashlib.sha256((root / 'tokenizer.json').read_bytes()).hexdigest(),
    'chat_template_sha256': hashlib.sha256(
        json.loads((root / 'tokenizer_config.json').read_text())['chat_template'].encode()
    ).hexdigest(),
}
expected = {
    'repository_bytes': 16397461266,
    'tokenizer_sha256': 'aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4',
    'chat_template_sha256': 'a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8',
}
if observed != expected:
    raise SystemExit(f'artifact identity mismatch: {observed!r}')
PY

vllm_version="$(docker run --rm --entrypoint python3 "${image}" -c 'import vllm; print(vllm.__version__)')"
python3 - "${vllm_version}" <<'PY'
import re
import sys
match = re.match(r'^(\d+)\.(\d+)\.(\d+)', sys.argv[1])
if not match or tuple(map(int, match.groups())) < (0, 23, 0):
    raise SystemExit(f'vLLM version is below 0.23.0: {sys.argv[1]}')
PY

python3 - "${image_digest}" "${vllm_version}" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

root = Path('/var/lib/catswitch/model')
rows = [line.strip() for line in subprocess.check_output(
    ['nvidia-smi', '--query-gpu=uuid,name,memory.total,driver_version', '--format=csv,noheader,nounits'],
    text=True,
).splitlines() if line.strip()]
proof = {
    'schema': 'catalog-switch-internal-qwen-bootstrap-proof/v4',
    'observed_at': datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
    'model_id': 'Qwen/Qwen3-8B',
    'model_revision': 'b968826d9c46dd6066d109eabc6255188de91218',
    'repository_bytes': sum(path.stat().st_size for path in root.rglob('*') if path.is_file() and '.cache' not in path.parts),
    'tokenizer_sha256': hashlib.sha256((root / 'tokenizer.json').read_bytes()).hexdigest(),
    'chat_template_sha256': hashlib.sha256(json.loads((root / 'tokenizer_config.json').read_text())['chat_template'].encode()).hexdigest(),
    'image_digest': sys.argv[1],
    'vllm_version': sys.argv[2],
    'checkpointing': False,
    'prefix_cache': False,
    'mtp': False,
    'observed_gpu_count': len(rows),
    'observed_gpu_rows_sha256': hashlib.sha256('\n'.join(rows).encode()).hexdigest(),
}
temporary = Path('/var/lib/catswitch/bootstrap-proof.json.tmp')
temporary.write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
os.chmod(temporary, 0o600)
os.replace(temporary, '/var/lib/catswitch/bootstrap-proof.json')
PY

cat >/etc/systemd/system/catalog-switch-qwen-scout-v4.service <<'UNIT'
[Unit]
Description=Catalog-switch authenticated two-request Qwen qualification server
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/catswitch/internal_scout_server_v4.py
Restart=on-failure
RestartSec=5
NoNewPrivileges=true
ProtectSystem=strict
ReadWritePaths=/var/lib/catswitch /run/catswitch
PrivateTmp=true

[Install]
WantedBy=multi-user.target
UNIT
systemctl daemon-reload
systemctl enable --now catalog-switch-qwen-scout-v4.service
for _ in $(seq 1 60); do
  if ss -lnt | grep -q ':8080 '; then
    echo "${marker} lease=${lease_id}" | tee /dev/console
    exit 0
  fi
  sleep 1
done
echo 'authenticated qualification service did not bind port 8080' >&2
exit 1
