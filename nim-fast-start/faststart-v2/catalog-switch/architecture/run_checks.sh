#!/usr/bin/env bash
set -euo pipefail

architecture_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
faststart_root="$(cd "${architecture_dir}/../.." && pwd)"
cd "${faststart_root}"

export PYTHONDONTWRITEBYTECODE=1

python3 catalog-switch/architecture/validate_architecture.py
python3 catalog-switch/architecture/validate_evidence_index.py
python3 catalog-switch/architecture/capacity_budget.py \
  --arrival-rate-p95 0.5 --occupancy-p95 20 \
  --preemptible-failover-slots 2
python3 -m unittest discover -v catalog-switch/architecture/tests
python3 -m unittest discover -v performance/request_slo/tests
python3 -m unittest discover -v catalog/tests
python3 catalog-switch/security-reliability/validate_threat_model.py
python3 -m unittest discover -v catalog-switch/security-reliability/tests
python3 -m unittest discover -v resource-broker/tests
PYTHONPATH=node-local-runtime python3 -m unittest discover -v \
  -s node-local-runtime/tests -t node-local-runtime
python3 -m unittest discover -v performance/k8s_baseline/tests
python3 -m unittest discover -v catalog-sim/tests
python3 -m unittest discover -v performance/storage_cache_matrix/tests
python3 -m unittest discover -v catalog-switch/cerebrium-comparator/tests
python3 -m unittest discover -v -s modal-pilot/harness -t modal-pilot
