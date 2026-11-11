#!/bin/sh
# Download a GGUF model into ./models (resumable).  Usage: scripts/download_model.sh <url>
set -eu
[ $# -eq 1 ] || { echo "usage: $0 <url-to-.gguf>" >&2; exit 2; }
dest="$(dirname "$0")/../models"
mkdir -p "$dest"
curl -fL -C - --output-dir "$dest" -O "$1"
echo "saved to $dest/$(basename "$1")"
