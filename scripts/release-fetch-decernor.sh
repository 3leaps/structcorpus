#!/usr/bin/env bash
# release-fetch-decernor.sh - Install the digest-pinned designated checker (CI)
#
# Downloads the decernor archive for one platform, requires its SHA-256 to
# equal the single matching line in config/release/decernor-ci-sha256.txt
# (PDR-0008 §2.5), extracts only the binary, and checks its identity and
# minimum version (release-decernor.sh). The pinned digest is the trust root; the
# version floor is not a substitute for it.
#
# Usage: release-fetch-decernor.sh OS_ARCH DEST_DIR
#   OS_ARCH is e.g. linux_amd64 or darwin_arm64. DEST_DIR must be an existing,
#   empty directory. Prints the absolute path of the installed binary, for
#   STRUCTCORPUS_DECERNOR_BIN.

set -euo pipefail

die() {
  echo "error: $*" >&2
  exit 1
}

[[ $# -eq 2 ]] || die "usage: release-fetch-decernor.sh OS_ARCH DEST_DIR"
platform="$1"
dest="$2"
[[ "$platform" =~ ^[a-z0-9]+_[a-z0-9]+$ ]] || die "invalid platform '$platform'"
[[ -d "$dest" && ! -L "$dest" ]] || die "destination $dest must exist"
[[ -z "$(ls -A "$dest")" ]] || die "destination $dest must be empty"
dest="$(cd "$dest" && pwd -P)"

root="$(git rev-parse --show-toplevel)"
pins="$root/config/release/decernor-ci-sha256.txt"
[[ -f "$pins" && ! -L "$pins" ]] || die "missing $pins"

matches="$(awk -v suffix="_${platform}.tar.gz" 'substr($2, length($2) - length(suffix) + 1) == suffix' "$pins")"
[[ -n "$matches" && "$matches" != *$'\n'* ]] || die "expected exactly one pinned archive for $platform"
read -r digest archive <<<"$matches"
[[ "$digest" =~ ^[0-9a-f]{64}$ ]] || die "malformed digest for $archive"
[[ "$archive" =~ ^decernor_((0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*))_${platform}\.tar\.gz$ ]] ||
  die "malformed archive name '$archive'"
version="${BASH_REMATCH[1]}"

curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location \
  "https://github.com/3leaps/decernor/releases/download/v${version}/${archive}" \
  --output "$dest/$archive"
if command -v sha256sum >/dev/null 2>&1; then
  actual="$(sha256sum "$dest/$archive" | awk '{print $1}')"
else
  actual="$(shasum -a 256 "$dest/$archive" | awk '{print $1}')"
fi
[[ "$actual" == "$digest" ]] || die "$archive digest $actual does not match the pinned $digest"

tar -xzf "$dest/$archive" -C "$dest" decernor
rm -f "$dest/$archive"
[[ -f "$dest/decernor" && ! -L "$dest/decernor" ]] || die "archive did not yield a regular decernor binary"
chmod 755 "$dest/decernor"

# shellcheck source=scripts/release-decernor.sh
source "$root/scripts/release-decernor.sh"
STRUCTCORPUS_DECERNOR_BIN="$dest/decernor" resolve_release_decernor ceremony ||
  die "installed decernor failed the identity and version check"
"$dest/decernor" version | grep -Fqx "decernor ${version}" || die "installed decernor does not report ${version}"
printf '%s\n' "$dest/decernor"
