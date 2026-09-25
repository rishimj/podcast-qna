#!/usr/bin/env bash
# Download the public benchmark datasets into data/benchmarks/ (gitignored).
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/benchmarks
cd data/benchmarks

for name in scifact nfcorpus; do
  if [ ! -d "$name" ]; then
    curl -sSL -o "$name.zip" "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets/$name.zip"
    unzip -q "$name.zip" && rm "$name.zip"
  fi
done

if [ ! -f qmsum_test.jsonl ]; then
  curl -sSL -o qmsum_test.jsonl https://raw.githubusercontent.com/Yale-LILY/QMSum/main/data/ALL/jsonl/test.jsonl
fi

echo "Datasets ready in data/benchmarks/"
