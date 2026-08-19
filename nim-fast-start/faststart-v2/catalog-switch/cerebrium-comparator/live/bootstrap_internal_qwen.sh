#!/usr/bin/env bash
set -euo pipefail

readonly marker='CATSWITCH_QWEN3_H100_OK'
readonly image='vllm/vllm-openai@sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d'
readonly image_digest='sha256:7c2c59db86a9a64138c5c675b98e3e05b7f37a34a344d4aa461b1529ed60262d'

# shellcheck disable=SC2317  # invoked indirectly by the ERR trap
on_error() {
  local rc=$?
  echo "CATSWITCH_BOOTSTRAP_FAILED rc=${rc}" >/dev/console
  exit "${rc}"
}

exec > >(tee -a /var/log/catswitch-bootstrap.log | logger -t catswitch-bootstrap -s 2>/dev/console) 2>&1
trap on_error ERR

export DEBIAN_FRONTEND=noninteractive
if ! command -v docker >/dev/null 2>&1; then
  apt-get update
  apt-get install -y --no-install-recommends docker.io nvidia-container-toolkit ca-certificates
fi
systemctl enable --now docker
if command -v nvidia-ctk >/dev/null 2>&1; then
  nvidia-ctk runtime configure --runtime=docker
  systemctl restart docker
fi

install -d -m 0755 /var/lib/catswitch/model /var/lib/catswitch/evidence /run/catswitch
nvidia-smi --query-gpu=uuid,name,memory.total,driver_version --format=csv,noheader
docker info --format '{{json .Runtimes}}'
docker pull "${image}"
actual_image_id="$(docker image inspect "${image}" --format '{{.Id}}')"
repo_digests="$(docker image inspect "${image}" --format '{{json .RepoDigests}}')"
case "${repo_digests}" in
  *"@${image_digest}"*) ;;
  *) echo "pulled image does not advertise frozen manifest digest" >&2; exit 1 ;;
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
repo_bytes = sum(
    path.stat().st_size
    for path in root.rglob('*')
    if path.is_file() and '.cache' not in path.parts
)
tokenizer_sha = hashlib.sha256((root / 'tokenizer.json').read_bytes()).hexdigest()
config = json.loads((root / 'tokenizer_config.json').read_text())
chat_sha = hashlib.sha256(config['chat_template'].encode()).hexdigest()
expected = {
    'repository_bytes': 16397461266,
    'tokenizer_sha256': 'aeb13307a71acd8fe81861d94ad54ab689df773318809eed3cbe794b4492dae4',
    'chat_template_sha256': 'a55ee1b1660128b7098723e0abcd92caa0788061051c62d51cbe87d9cf1974d8',
}
observed = {
    'repository_bytes': repo_bytes,
    'tokenizer_sha256': tokenizer_sha,
    'chat_template_sha256': chat_sha,
}
if observed != expected:
    raise SystemExit(f'artifact identity mismatch: {observed!r}')
PY

vllm_version="$(docker run --rm --entrypoint python3 "${image}" -c 'import vllm; print(vllm.__version__)')"
python3 - "${vllm_version}" <<'PY'
import sys

raw = sys.argv[1].split('+', 1)[0].split('rc', 1)[0]
parts = tuple(int(part) for part in raw.split('.')[:3])
if parts < (0, 23, 0):
    raise SystemExit(f'vLLM version is below 0.23.0: {sys.argv[1]}')
PY

python3 - "${actual_image_id}" "${image_digest}" "${vllm_version}" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

root = Path('/var/lib/catswitch/model')
proof = {
    'schema': 'catalog-switch-internal-qwen-bootstrap-proof/v1',
    'observed_at': datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S.%fZ'),
    'model_id': 'Qwen/Qwen3-8B',
    'model_revision': 'b968826d9c46dd6066d109eabc6255188de91218',
    'repository_bytes': sum(
        path.stat().st_size
        for path in root.rglob('*')
        if path.is_file() and '.cache' not in path.parts
    ),
    'tokenizer_sha256': hashlib.sha256((root / 'tokenizer.json').read_bytes()).hexdigest(),
    'chat_template_sha256': hashlib.sha256(
        json.loads((root / 'tokenizer_config.json').read_text())['chat_template'].encode()
    ).hexdigest(),
    'image_config_digest': sys.argv[1],
    'image_digest': sys.argv[2],
    'vllm_version': sys.argv[3],
    'checkpointing': False,
    'prefix_cache': False,
    'mtp': False,
    'gpu_csv': subprocess.check_output(
        [
            'nvidia-smi',
            '--query-gpu=uuid,name,memory.total,driver_version',
            '--format=csv,noheader,nounits',
        ],
        text=True,
    ).strip(),
}
temporary = Path('/var/lib/catswitch/bootstrap-proof.json.tmp')
temporary.write_text(json.dumps(proof, indent=2, sort_keys=True) + '\n')
os.replace(temporary, '/var/lib/catswitch/bootstrap-proof.json')
PY

cat >/etc/systemd/system/catalog-switch-qwen-scout.service <<'UNIT'
[Unit]
Description=Catalog-switch authenticated Qwen process-cold scout
After=docker.service network-online.target
Requires=docker.service

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/catswitch/internal_scout_server.py
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
systemctl enable --now catalog-switch-qwen-scout.service
for _ in $(seq 1 60); do
  if ss -lnt | grep -q ':8080 '; then
    echo "${marker} lease=catswitch-qwen3-h100-scout-20260819" | tee /dev/console
    exit 0
  fi
  sleep 1
done
echo 'authenticated scout service did not bind port 8080' >&2
exit 1
