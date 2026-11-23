#!/usr/bin/env bash
# SPDX-License-Identifier: MIT OR Apache-2.0
# Install the checksum-pinned limensafe release binary for CI.
# Usage: install-limensafe.sh DIR   (prints the installed path)
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
pin="$root/config/release/limensafe-ci-sha256.txt"
dir="${1:?usage: install-limensafe.sh DIR}"

# The pin names the file limensafe-vX.Y.Z-<os>-<arch>.
read -r _ name <"$pin"
[[ "$name" =~ ^limensafe-(v[0-9]+\.[0-9]+\.[0-9]+)-([a-z0-9]+-[a-z0-9]+)$ ]] || {
  echo "error: unexpected limensafe pin: $name" >&2
  exit 1
}
version="${BASH_REMATCH[1]}"
platform="${BASH_REMATCH[2]}"

mkdir -p "$dir"
curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
  "https://github.com/fulmenhq/limensafe/releases/download/${version}/limensafe-${platform}" \
  --output "$dir/$name"
(cd "$dir" && sha256sum --check --status "$pin") || {
  echo "error: limensafe download does not match the pinned checksum" >&2
  exit 1
}
chmod +x "$dir/$name"
printf '%s\n' "$dir/$name"
