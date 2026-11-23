---
Record: PDR-0003
Title: Signed-tag releases and their verification gates
Status: Proposed
Date: 2026-11-23
Owner: devlead (drafting); acceptance by the maintainer
---

# PDR-0003: Signed-tag releases and their verification gates

## Context

Consumers pin a corpus release together with its content hashes and profile
revision ([ADR-0001](ADR-0001-engine-neutral-corpus-scope.md)), and releases
arrive in stages ([PDR-0001](PDR-0001-staged-releases.md)). structcorpus
publishes no binaries, archives, or packages. A release is a signed annotated
Git tag, so a pin is only as trustworthy as that tag's provenance and the gates
that ran before and after it.

This record adopts the tag-only subset of 3leaps/crucible
[PDR-0008](https://github.com/3leaps/crucible/blob/0bada725dc07bda098764b1f4ac9c56f43ba18cd/docs/decisions/PDR-0008-release-public-identity-in-tree.md)
(release public identity committed in the tree). It also states the limits of
each gate, so later readers do not take a gate to prove more than it does. The
step-by-step procedure is in [RELEASE_CHECKLIST.md](../../RELEASE_CHECKLIST.md).
Verification instructions for consumers are in
[docs/security/README.md](../security/README.md).

## Decision

1. **Release identity is committed, and read from the tagged commit.** The
   public key pin (`docs/security/release-signing-keys.asc`), the signing
   subkey selector and tagger identity (`config/release/`), and the
   fingerprint anchors (`keys/expected-fingerprints.{txt,ndjson}`) are
   committed files. Tag verification reads them as inert blobs from the
   tagged commit, never from the working tree or an environment override.
   Anchors are derived and checked by one designated checker, Decernor 0.1.8
   or newer. It is bound by an absolute path in the ceremony and by a
   committed archive digest in CI (`config/release/decernor-ci-sha256.txt`).

2. **The release tag is an explicit input.** Every maintainer ceremony
   entrypoint (preflight, message preparation, tagging, push, and the local,
   remote and published-tag verifiers) and every tag-consuming `make` target
   takes the tag only from `STRUCTCORPUS_RELEASE_TAG`. Nothing is derived from
   `VERSION`. The generic `RELEASE_TAG` is refused whenever it is set, from the
   environment, the `make` command line, or a makefile, and even when it is
   empty. The check runs before any loader, fetch, message, GitHub call, or
   tag operation (`scripts/release-guard-tag-input.sh`). Two interfaces take
   the tag another way: the CI check reads it from the push event (decision
   4), and the advisory `scripts/release-inspect-tag-ruleset.sh` takes it as an
   argument from the guarded ceremony scripts.

3. **The pre-tag gate runs on the merged main commit** (`make
   release-preflight`). It checks:
   - a clean checkout at `origin/main`;
   - the changelog and its compare links;
   - the committed anchors;
   - the repository's tag ruleset and immutable-releases setting;
   - committed-file content;
   - the release-scope public-surface scan;
   - dates;
   - the unit tests from a clean clone outside the home directory;
   - `make check`.

   The unit tests run through `scripts/run-unit-tests.py`, which keeps
   `unittest` semantics but fails a vacuous run. The run must start at least
   one test invocation that does not end as a whole-test skip, discovery must
   report no errors, and `unittest` must report success. Subtest, class, and module
   skips neither count nor cancel an invocation. A test method that is itself
   a generator, an async generator, or (outside `IsolatedAsyncioTestCase`) a
   coroutine is refused, because `unittest` would report it passed without
   running its body. That method is looked up statically, so no property or
   descriptor is invoked.

4. **Every published tag is re-checked in CI and bound to its push event**
   (`.github/workflows/tag-verify.yml`, `scripts/release-ci-verify-tag.sh`).
   The checkout is the event commit. Before anything is installed, the push
   event's `after` value must be an annotated tag object, the fetched tag must
   be exactly that object and peel to the checked-out commit, and GitHub's ref
   must agree. `github.sha` may be either the peeled commit or that same tag
   object. If the event names only a commit, the run fails rather than accept
   whatever tag object the ref holds by then. The checker is then installed
   from its pinned digest, the tag is verified against the identity in its
   own commit, GitHub must report that object verified, and the ref is
   re-read last. A passing run is consistency evidence. The maintainer's
   signature is the release authorization.

5. **The first tag run is the evidence for the event shape.** GitHub's push
   payload documentation describes `after` as a commit. Reported runs for
   annotated-tag pushes show it carrying the tag object. The first release's
   workflow run settles which applies here. Version tags are immutable by
   project policy, so if that run fails because the event did not name the tag
   object, the tag is not moved or re-signed and stays unverified by CI. The
   binding is corrected in a reviewed change, and the next patch version is
   tagged.

6. **Repository settings back the tag.** A tag ruleset restricts creating,
   updating, and deleting `refs/tags/v*` to organization administrators, which
   is the GitHub control for these tags because no GitHub Release is
   published. Immutable releases are also enabled; that lock applies only to a
   published GitHub Release. `make release-github-preflight` checks both,
   including the ruleset's bypass list, before tagging.

7. **No public-surface scan configuration is kept in the repository.** The
   scan builds its baseline configuration in a temporary directory at run
   time. The release-scope scan in `make release-preflight` requires a
   maintainer catalog, supplied from outside the repository; the generated
   baseline alone does not satisfy it. CI runs the built-in baseline only.

## Consequences

- Changes to release tooling, the tag workflow, or the files in decisions 1
  and 6 are reviewed against this record.
- **Limit of the unit-test gate:** it detects accidental vacuity in the run
  that `unittest` reports, such as nothing discovered or everything skipped.
  It does not show that a test asserts anything useful; that is a review
  question. Test functions reached through other adapters
  (`functools.partial` or `partialmethod`, callable objects, properties,
  custom descriptors) are outside its deferred-body check.
- **Limit of the tag workflow:** it runs the workflow and checker from the
  tagged commit, so it shows that the tag, the identity committed with it, and
  GitHub agree. It does not replace independently establishing the expected
  signing key (docs/security/README.md).
- A failed first-run event binding costs a patch version, not a moved tag
  (decision 5).

## Alternatives considered

- **Fall back to binding the commit when the event names only a commit.**
  Rejected. It would accept a different tag object on the same commit.
- **Instrument test methods to prove that each test body ran.** Rejected.
  Wrapping or replacing test methods changes how `unittest` runs them (for
  example, whether asynchronous tests are awaited), and each refinement opened
  another composed-adapter case. Counting the invocations `unittest` reports,
  plus review, is the chosen boundary.
- **Keep the scan configuration in the repository.** Rejected in favour of
  generating it at run time (decision 7).
