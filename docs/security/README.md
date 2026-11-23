# Release verification

structcorpus releases are GPG-signed annotated Git tags. Releases are
source-only: no binaries, checksum manifests, or package-manager artifacts are
published, so there is no artifact signature to verify.

Establish the expected GPG primary and exact signing subkey through an
independently trusted maintainer channel before accepting a downloaded public
key. A key distributed beside a signature is not independent authentication.

The public pin is [`release-signing-keys.asc`](release-signing-keys.asc), and
the exact signing subkey is
[`config/release/signing-subkey.txt`](../../config/release/signing-subkey.txt).
The tagger identity is
[`config/release/tagger-identity.txt`](../../config/release/tagger-identity.txt).
Tag verification extracts these from the verified tagged commit as inert
blobs, not from the current checkout.

The text and NDJSON anchors in [`keys/`](../../keys/) record the pinned
primary under Decernor's `openpgp-fingerprint-v1` scheme. Check the pin against
both anchors with Decernor 0.1.8 or newer:

```bash
make release-anchors-check
```

The check re-derives the primary fingerprint record from the pin with
`decernor fingerprint --class public --kind gpg --gpg-role primary` and
requires both anchor files to match it exactly.

Tag verification (`scripts/verify-pinned-tag.sh`, `make release-verify-tag`)
uses an isolated keyring and requires the exact signing subkey and the
committed tagger identity. GitHub Verified with reason `valid` is an
additional check (`make release-verify-published-tag`). Tags created before
the pin was committed are not verified by it and are not re-signed.

On every pushed `v*` tag, the read-only workflow
[`tag-verify.yml`](../../.github/workflows/tag-verify.yml) installs Decernor
from the archive digest committed in
[`config/release/decernor-ci-sha256.txt`](../../config/release/decernor-ci-sha256.txt),
checks the pin against both anchors, verifies the tag signature against the
pinned signing subkey and tagger identity read from the tagged commit, and
requires GitHub to report the tag verified. A passing run is consistency
evidence, not release authorization: the maintainer's signature on the tag is
the authorization, and the expected primary still has to be established
independently as described above.
