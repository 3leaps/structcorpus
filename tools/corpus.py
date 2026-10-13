#!/usr/bin/env python3
"""structcorpus command-line tool (Python 3.9+, standard library only).

Subcommands:
  validate   Check repository rules (DDR-0001, SecDR-0001). Case-record
             validation is added with the case schemas (DDR-0002).

Hydrate, verify, and list are added with recipes (PDR-0001, stage 0.2).
"""

import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

MAX_FIXTURE_BYTES = 256 * 1024
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024
MAX_PATH_CHARS = 200
BYTE_EXACT_TREES = ("fixtures", "expected")
FORBIDDEN_DIRS = {"unknown", "pending", "quarantine", "staging", "intake"}

COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
RESERVED_STEMS = (
    {"con", "prn", "aux", "nul"}
    | {"com%d" % i for i in range(1, 10)}
    | {"lpt%d" % i for i in range(1, 10)}
)


class DuplicateKeyError(ValueError):
    pass


def _reject_duplicates(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise DuplicateKeyError("duplicate JSON key: %r" % key)
        obj[key] = value
    return obj


def load_json_strict(data):
    """Parse JSON bytes, rejecting duplicate keys and non-finite numbers."""

    def bad_constant(name):
        raise ValueError("non-standard JSON constant: %s" % name)

    return json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_reject_duplicates,
        parse_constant=bad_constant,
    )


def path_problems(rel):
    """Return portability problems for a repository-relative path (DDR-0001)."""
    problems = []
    if len(rel) > MAX_PATH_CHARS:
        problems.append("path longer than %d characters" % MAX_PATH_CHARS)
    for part in rel.split("/"):
        if not COMPONENT_RE.match(part):
            problems.append("component %r is not lowercase [a-z0-9._-]" % part)
        if part.endswith("."):
            problems.append("component %r ends with a dot" % part)
        if part.split(".")[0] in RESERVED_STEMS:
            problems.append("component %r uses a reserved device name" % part)
    return problems


def _walk_files(top):
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames.sort()
        for name in sorted(filenames):
            yield os.path.join(dirpath, name)


def check_repository(root):
    """Return a list of rule violations under root."""
    errors = []
    attrs_path = os.path.join(root, ".gitattributes")
    attrs = ""
    if os.path.exists(attrs_path):
        with open(attrs_path, "rb") as fh:
            attrs = fh.read().decode("utf-8")
    total = 0
    for tree in BYTE_EXACT_TREES:
        if "/%s/** -text" % tree not in attrs:
            errors.append(".gitattributes: /%s/** must be marked -text" % tree)
        top = os.path.join(root, tree)
        if not os.path.isdir(top):
            continue
        for path in _walk_files(top):
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if os.path.basename(rel) in (".gitkeep", "README.md"):
                continue
            for part in rel.split("/")[:-1]:
                if part in FORBIDDEN_DIRS:
                    errors.append("%s: intake/staging directory %r (SecDR-0001)" % (rel, part))
            if os.path.islink(path):
                errors.append("%s: symbolic links are not allowed" % rel)
                continue
            for problem in path_problems(rel):
                errors.append("%s: %s" % (rel, problem))
            size = os.path.getsize(path)
            total += size
            if size > MAX_FIXTURE_BYTES:
                errors.append("%s: %d bytes exceeds %d per file" % (rel, size, MAX_FIXTURE_BYTES))
    if total > MAX_PAYLOAD_BYTES:
        errors.append("committed payload %d bytes exceeds %d" % (total, MAX_PAYLOAD_BYTES))
    for tree in ("manifests", "schemas"):
        top = os.path.join(root, tree)
        if not os.path.isdir(top):
            continue
        for path in _walk_files(top):
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            if not (rel.endswith(".json") or rel.endswith(".jsonl")):
                continue
            with open(path, "rb") as fh:
                data = fh.read()
            chunks = data.splitlines() if rel.endswith(".jsonl") else [data]
            for lineno, chunk in enumerate(chunks, 1):
                if not chunk.strip():
                    continue
                try:
                    load_json_strict(chunk)
                except ValueError as exc:
                    where = "%s:%d" % (rel, lineno) if rel.endswith(".jsonl") else rel
                    errors.append("%s: %s" % (where, exc))
    return errors


def cmd_validate(args):
    errors = check_repository(args.root)
    for err in errors:
        print("error: " + err, file=sys.stderr)
    if errors:
        print("validate: %d error(s)" % len(errors), file=sys.stderr)
        return 1
    print("validate: ok")
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(prog="corpus.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    p_validate = sub.add_parser("validate", help="check repository rules")
    p_validate.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    p_validate.set_defaults(func=cmd_validate)
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
