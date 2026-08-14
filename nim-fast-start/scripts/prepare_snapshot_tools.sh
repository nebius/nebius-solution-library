#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
ROOT_DIR=$(cd "${SCRIPT_DIR}/.." && pwd)
DYNAMO_REF=${DYNAMO_REF:-f7f37be174d252590c4b56e25ff4262dd82466fd}
DYNAMO_DIR=${DYNAMO_DIR:-${ROOT_DIR}/.cache/dynamo}
TOOLS_DIR=${TOOLS_DIR:-${ROOT_DIR}/.tools}
GO_IMAGE=${GO_IMAGE:-golang:1.26.3}
HELM_STATE_DIR=${HELM_STATE_DIR:-${ROOT_DIR}/.cache/helm}
GO_STATE_DIR=${GO_STATE_DIR:-${ROOT_DIR}/.cache/go}

mkdir -p "$(dirname "${DYNAMO_DIR}")" "${TOOLS_DIR}" \
  "${HELM_STATE_DIR}/config" "${HELM_STATE_DIR}/cache" "${HELM_STATE_DIR}/data" \
  "${GO_STATE_DIR}/build" "${GO_STATE_DIR}/modules"

if [[ ! -d "${DYNAMO_DIR}/.git" ]]; then
  git clone --filter=blob:none --no-checkout https://github.com/ai-dynamo/dynamo.git "${DYNAMO_DIR}"
fi

git -C "${DYNAMO_DIR}" fetch --depth 1 origin "${DYNAMO_REF}"
git -C "${DYNAMO_DIR}" checkout --detach "${DYNAMO_REF}"

resolved_ref=$(git -C "${DYNAMO_DIR}" rev-parse HEAD)
if [[ "${resolved_ref}" != "${DYNAMO_REF}" ]]; then
  echo "Dynamo checkout mismatch: expected ${DYNAMO_REF}, got ${resolved_ref}" >&2
  exit 1
fi

export HELM_CONFIG_HOME="${HELM_STATE_DIR}/config"
export HELM_CACHE_HOME="${HELM_STATE_DIR}/cache"
export HELM_DATA_HOME="${HELM_STATE_DIR}/data"
helm repo add nats https://nats-io.github.io/k8s/helm/charts/ --force-update >/dev/null
helm repo add bitnami https://charts.bitnami.com/bitnami --force-update >/dev/null
helm dependency build "${DYNAMO_DIR}/deploy/helm/charts/platform"

host_uid=$(id -u)
host_gid=$(id -g)
docker run --rm \
  -e HOST_UID="${host_uid}" \
  -e HOST_GID="${host_gid}" \
  -v "${DYNAMO_DIR}:/src" \
  -v "${TOOLS_DIR}:/out" \
  -v "${GO_STATE_DIR}/build:/root/.cache/go-build" \
  -v "${GO_STATE_DIR}/modules:/go/pkg/mod" \
  -w /src/deploy/snapshot \
  "${GO_IMAGE}" \
  sh -c 'go build -buildvcs=false -trimpath -o /out/snapshotctl ./cmd/snapshotctl && chown "$HOST_UID:$HOST_GID" /out/snapshotctl'

"${TOOLS_DIR}/snapshotctl" --help >/dev/null
printf 'Dynamo ref: %s\nsnapshotctl: %s\n' "${resolved_ref}" "${TOOLS_DIR}/snapshotctl"
