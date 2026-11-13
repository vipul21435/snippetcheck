#!/usr/bin/env bash
# Download the two public datasets used in the README into DIR (default: data/).
# CodeAlpaca-20k: CC BY 4.0. Evol-Instruct-Code-80k-v1: CC BY-NC-SA 4.0.
# The files are not part of this repository.
set -euo pipefail
dir="${1:-data}"
mkdir -p "$dir"
curl -sSL -o "$dir/code_alpaca_20k.json" \
  https://huggingface.co/datasets/sahil2801/CodeAlpaca-20k/resolve/main/code_alpaca_20k.json
curl -sSL -o "$dir/EvolInstruct-Code-80k.json" \
  https://huggingface.co/datasets/nickrosh/Evol-Instruct-Code-80k-v1/resolve/main/EvolInstruct-Code-80k.json
shasum -a 256 "$dir"/*.json
