#!/usr/bin/env bash
# Starts Image to GIF inside the Nix environment from shell.nix.
# Any image paths given as arguments are added to the list.
set -euo pipefail
DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
CMD="exec python3 $(printf '%q' "$DIR/image_to_gif.py")"
for arg in "$@"; do
  CMD+=" $(printf '%q' "$arg")"
done
exec nix-shell "$DIR/shell.nix" --run "$CMD"
