# Release Checklist

Checklist for structcorpus releases. structcorpus v0.x releases are source-only
signed Git tags: no binaries, archives, checksums, or package-manager
artifacts are published.

## Pre-Release

### Version Planning

- [ ] All planned changes merged to `main` and tested
- [ ] Breaking changes documented
- [ ] Version number decided (semantic versioning: MAJOR.MINOR.PATCH)

### Code Quality

- [ ] Non-mutating gate passing: `make check`
- [ ] Pre-push gate passing: `make prepush`
- [ ] Release tooling suites passing (throwaway keys only; needs gpg, git,
      python3, jq, make, and Decernor via `STRUCTCORPUS_DECERNOR_BIN`):
      `make release-tooling-test`
- [ ] Committed public pin agrees with both fingerprint anchors:
      `make release-anchors-check`
- [ ] Public-surface scan with the catalog passing for the release pull
      request: `make pr-final` (needs `LIMENSAFE_CATALOG_PATH` and
      `STRUCTCORPUS_SURFACE_PR_TEXT`)
- [ ] Sensitive local data reviewed against the
      [3 Leaps Sensitive Local Data Policy](https://github.com/3leaps/oss-policies/blob/main/SENSITIVE-LOCAL-DATA.md);
      none is stored inside the repository tree relying only on `.gitignore`.

### Documentation

- [ ] `README.md` reviewed and updated
- [ ] `python3 tools/corpus.py --help` text accurate
- [ ] `docs/coverage.md` matches the shipped cases and recipes
- [ ] `CHANGELOG.md` has a dated `## [<version>] - YYYY-MM-DD` section with
      the release entries

### Dependencies

- [ ] Corpus tools still use only the Python 3.9+ standard library
      ([ADR-0002](docs/decisions/ADR-0002-python-stdlib-tooling.md))

## Release Preparation

### Version Updates

- [ ] Update `VERSION`
- [ ] Sync the changelog compare links: `make sync-changelog-links`
- [ ] Changelog matches `VERSION`: `make release-guard-release-surfaces`
- [ ] Version sanity check:
      `STRUCTCORPUS_RELEASE_TAG=v<version> make release-guard-signing-tag`

### Git Hygiene

- [ ] Release preparation merged to `main`; local checkout is on `main` and
      matches `origin/main`
- [ ] `git status` clean
- [ ] Every commit carries the attribution trailers

## Release Execution

### Signing Inputs

The tag is signed by `3 Leaps Infosec Team <infosec@3leaps.net>` with the
pinned signing subkey. Public trust material is committed:
`config/release/tagger-identity.txt`, `config/release/signing-subkey.txt`,
`docs/security/release-signing-keys.asc`, and
`keys/expected-fingerprints.{txt,ndjson}`. See
[docs/security/README.md](docs/security/README.md).

Set in the shell, never in the repository:

| Variable                             | Purpose                                                                                  |
| ------------------------------------ | ---------------------------------------------------------------------------------------- |
| `STRUCTCORPUS_RELEASE_TAG`             | Release tag `v<version>`; must match `VERSION`                                           |
| `STRUCTCORPUS_DECERNOR_BIN`            | Absolute path to `decernor` 0.1.8 or newer                                               |
| `STRUCTCORPUS_TAG_MESSAGE_DIR`         | Absolute directory outside the repository whose last component is the tag                |
| `STRUCTCORPUS_TAGGER_NAME`             | Tagger name; must match `config/release/tagger-identity.txt`                             |
| `STRUCTCORPUS_TAGGER_EMAIL`            | Tagger email; must match `config/release/tagger-identity.txt`                            |
| `STRUCTCORPUS_GPG_SIGNING_FINGERPRINT` | Approved primary fingerprint (40 uppercase hex)                                          |
| `STRUCTCORPUS_PGP_KEY_ID`              | Signing subkey selector `<subkey>!` matching `config/release/signing-subkey.txt`         |
| `STRUCTCORPUS_GPG_HOMEDIR`             | Dedicated `0700` GnuPG home outside the repository; never the default GnuPG home         |
| `LIMENSAFE_CATALOG_PATH`             | Public-surface catalog file outside the repository; required by `make release-preflight` |

Optional inputs (unset means the default shown):

| Variable                           | Default       | Purpose and constraints                                                                                                                                                                                 |
| ---------------------------------- | ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `STRUCTCORPUS_APPROVED_ENV_LOADER`   | unset         | Maintainer shell file sourced by the tag targets before their guards run. When set it must be an absolute, readable regular file (not a symlink) outside the repository, and it must exit successfully. |
| `STRUCTCORPUS_REQUIRE_TAG`           | `0`           | `1` makes `make release-guard-tag-version` require `STRUCTCORPUS_RELEASE_TAG` instead of defaulting to `v<VERSION>`.                                                                                      |
| `STRUCTCORPUS_LIMENSAFE_BIN`         | `limensafe`   | Absolute path to the public-surface scanner when it is not on `PATH`.                                                                                                                                   |
| `STRUCTCORPUS_SURFACE_SCOPE`         | `pr`          | `release` scans every commit message in history; the pull-request and release targets set it themselves.                                                                                                |
| `STRUCTCORPUS_SURFACE_BASE`          | `origin/main` | Base commit for the pull-request commit-message scan.                                                                                                                                                   |
| `STRUCTCORPUS_SURFACE_PR_TEXT`       | unset         | Non-empty file holding the pull-request title and body to scan.                                                                                                                                         |
| `STRUCTCORPUS_SURFACE_SCAN_REQUIRED` | `0`           | `1` fails instead of skipping when `LIMENSAFE_CATALOG_PATH` is unset; `make pr-final` and the release targets set it themselves.                                                                        |

Must stay unset: `STRUCTCORPUS_SURFACE_RELEASE_BASE` (the release scan refuses
any override of its base), `STRUCTCORPUS_TEST_FAIL_ANCHOR_INSTALL` (a
fault-injection hook used only by the tooling tests), and
`STRUCTCORPUS_SURFACE_BASELINE_ONLY` and `STRUCTCORPUS_SURFACE_BRANCH_NAME` (set
only by the CI baseline scan).

The tag comes only from `STRUCTCORPUS_RELEASE_TAG`. The version guard and the
tag targets refuse to start while the generic `RELEASE_TAG` is set, even to an
empty value, so `unset RELEASE_TAG` first.

### Tagging (maintainer machine)

- [ ] Remote tag-protection ruleset and immutable-releases setting:
      `make release-github-preflight` (needs a GitHub token with repository
      admin access, which can read the ruleset's bypass list)
- [ ] Pre-tag gate on the merged `main` commit (committed anchor verification,
      `make surface-scan-release`, changelog and compare links, GitHub
      preflight, content-check, dates check, clean-clone test outside the home
      directory, and `make check`): `make release-preflight`
- [ ] Prepare and review the external tag message:
      `make release-prepare-tag-message`
- [ ] Create and verify the local signed tag: `make release-tag`
- [ ] Verify the local tag against the committed pin: `make release-verify-tag`
- [ ] Publish and verify the tag (local signature against the committed pin,
      remote object, GitHub `valid`): `make release-push-tag`. The push reports
      the tag ruleset but does not enforce it; `make release-preflight` does,
      so rerun it if anything changed since.
- [ ] Re-verify the published tag from a clean checkout:
      `make release-verify-published-tag` (and
      `make release-verify-remote-tag` to compare local and remote objects)

### Public Pin Maintenance

Only when the release signing key changes. Each target refuses to overwrite
existing material; replacing a pin or anchor is a reviewed change that deletes
the old file first.

- [ ] Export the approved public key to an absent pin: `make release-export-pin`
- [ ] Validate the existing pin (read-only): `make release-validate-pin`
- [ ] Derive absent fingerprint anchors from the validated pin:
      `make release-insert-anchors`

## Post-Release

- [ ] Consumers pin the tag together with its commit, content hashes, and
      profile revisions
- [ ] Monitor GitHub issues for release-related bugs

## Notes

- Never skip tests, hooks, or review to speed up a release.
- Signing and tag publication are maintainer actions.
