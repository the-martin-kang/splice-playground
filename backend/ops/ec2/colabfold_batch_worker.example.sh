#!/usr/bin/env bash
set -euo pipefail

# Adjust the conda.sh path for your DLAMI if needed.
if [ -f "$HOME/miniforge3/etc/profile.d/conda.sh" ]; then
  source "$HOME/miniforge3/etc/profile.d/conda.sh"
elif [ -f /opt/conda/etc/profile.d/conda.sh ]; then
  source /opt/conda/etc/profile.d/conda.sh
elif [ -f "$HOME/anaconda3/etc/profile.d/conda.sh" ]; then
  source "$HOME/anaconda3/etc/profile.d/conda.sh"
else
  echo "conda.sh not found" >&2
  exit 1
fi

conda run -n colabfold colabfold_batch "$@"
