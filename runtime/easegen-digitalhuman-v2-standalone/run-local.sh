#!/usr/bin/env bash
set -euo pipefail

standalone_root="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
engine_root="${EASEGEN_DH_ENGINE_ROOT:-}"
if [[ "${1:-}" == "--engine-root" ]]; then
  engine_root="${2:-}"
  shift 2
fi
if [[ -z "${engine_root}" || ! -d "${engine_root}" ]]; then
  echo "A valid --engine-root or EASEGEN_DH_ENGINE_ROOT is required" >&2
  exit 2
fi

venv_root="${EASEGEN_DH_VENV:-/root/easegen-dh-venv}"
python_executable="${EASEGEN_DH_PYTHON:-${venv_root}/bin/python}"
if [[ ! -x "${python_executable}" ]]; then
  echo "Digital-human Python is not executable: ${python_executable}" >&2
  exit 2
fi

nvidia_root="${venv_root}/lib/python3.8/site-packages/nvidia"
if [[ -d "${nvidia_root}" ]]; then
  cuda_library_path="$(find "${nvidia_root}" -type d -name lib -print | paste -sd: -)"
  if [[ -n "${cuda_library_path}" ]]; then
    export LD_LIBRARY_PATH="${cuda_library_path}:${LD_LIBRARY_PATH:-}"
  fi
fi

export PYTHONPATH="${standalone_root}:${engine_root}:${PYTHONPATH:-}"
cd "${engine_root}"
exec "${python_executable}" "${standalone_root}/run.py" "$@"
