#!/usr/bin/env bash
# Download tau2-bench (Sierra Research, MIT licence) at the exact commit used for this project.
set -euo pipefail

REPO="https://github.com/sierra-research/tau2-bench.git"
COMMIT="768f3d8fe8528b4f32a5096f9ed008ae50f48ead"
DEST="${1:-data/tau2-bench}"

if [ -d "$DEST/data/tau2/results/final" ]; then
  echo "tau2-bench already present at $DEST"
  exit 0
fi

mkdir -p "$DEST"
git -C "$DEST" init -q
git -C "$DEST" remote add origin "$REPO" 2>/dev/null || true
git -C "$DEST" fetch -q --depth 1 origin "$COMMIT"
git -C "$DEST" checkout -q FETCH_HEAD
echo "tau2-bench $COMMIT -> $DEST"
