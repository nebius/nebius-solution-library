#!/usr/bin/env bash
set -euo pipefail

readonly source_dir="${1:?usage: prepare_upstream.sh SOURCE_DIR}"
readonly expected_commit="03014943323e78feb5bd672ef08b72caea0918ac"
patch_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
readonly patch_root
readonly patch_file="${patch_root}/build/public-source.patch"

if [[ ! -d "${source_dir}/.git" ]]; then
  mkdir -p "$(dirname "${source_dir}")"
  git clone --branch v1.4.0 --depth 1 https://github.com/ai-dynamo/dynamo.git "${source_dir}"
fi

actual_commit="$(git -C "${source_dir}" rev-parse HEAD)"
if [[ "${actual_commit}" != "${expected_commit}" ]]; then
  echo "unexpected Dynamo source commit: ${actual_commit}" >&2
  echo "expected: ${expected_commit}" >&2
  exit 1
fi

if git -C "${source_dir}" apply --unidiff-zero --reverse --check \
  "${patch_file}" >/dev/null 2>&1; then
  echo "public-source patch already applied"
else
  git -C "${source_dir}" apply --unidiff-zero --check "${patch_file}"
  git -C "${source_dir}" apply --unidiff-zero "${patch_file}"
fi

git -C "${source_dir}" diff --check
echo "prepared Dynamo v1.4.0 at ${actual_commit}"
