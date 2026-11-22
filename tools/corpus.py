#!/usr/bin/env python3
"""structcorpus command-line tool (Python 3.9+, standard library only).

Subcommands:
  validate   Check repository rules (DDR-0001), metadata (ADR-0002), and case
             records (DDR-0002, DDR-0003, SecDR-0001).
  canon      Print a JSON file in canonical form (JCS over the ADR-0002 subset).
  hydrate    Generate recipe inputs into an output root outside the checkout.
  verify     Re-check a hydrated root's inputs, manifest, and recipe digests.
  aggregate  Regenerate manifests/cases.jsonl from the per-format case shards
             (DDR-0014); validate only checks it and never writes.

Full JSON Schema validation runs separately in CI with an external validator;
the checks here are the admission gate a consumer can run with python3 alone.

  list       Recipes and committed cases by tier, with counts, bytes, and hazards.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import events as event_notation  # noqa: E402

MAX_FIXTURE_BYTES = 256 * 1024
MAX_PAYLOAD_BYTES = 32 * 1024 * 1024
MAX_PATH_CHARS = 200
BYTE_EXACT_TREES = ("fixtures", "expected")
BYTE_EXACT_ATTRS = "-text -filter -ident -working-tree-encoding"
MAX_SAFE_INT = 2**53 - 1
FORBIDDEN_DIRS = {"unknown", "pending", "quarantine", "staging", "intake"}

COMPONENT_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
RESERVED_STEMS = (
    {"con", "prn", "aux", "nul"} | {"com%d" % i for i in range(1, 10)} | {"lpt%d" % i for i in range(1, 10)}
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


def _check_subset(value):
    """Enforce the ADR-0002 metadata subset on a decoded value."""
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, int):
        if not -MAX_SAFE_INT <= value <= MAX_SAFE_INT:
            raise ValueError("integer outside the interoperable range: %d" % value)
    elif isinstance(value, str):
        try:
            value.encode("utf-8")
        except UnicodeEncodeError:
            raise ValueError("string contains a lone surrogate") from None
    elif isinstance(value, list):
        for item in value:
            _check_subset(item)
    elif isinstance(value, dict):
        for key, item in value.items():
            _check_subset(key)
            _check_subset(item)
    else:
        raise ValueError("value outside the metadata subset: %s" % type(value).__name__)


def load_json_strict(data):
    """Parse JSON bytes into the ADR-0002 metadata subset.

    Rejects duplicate keys, floating-point and non-finite numbers, integers
    outside +/-(2**53 - 1), and lone surrogates (raw or escaped).
    """

    def bad_constant(name):
        raise ValueError("non-standard JSON constant: %s" % name)

    value = json.loads(
        data.decode("utf-8"),
        object_pairs_hook=_reject_duplicates,
        parse_constant=bad_constant,
    )
    _check_subset(value)
    return value


_SHORT_ESCAPES = {0x08: "\\b", 0x09: "\\t", 0x0A: "\\n", 0x0C: "\\f", 0x0D: "\\r", 0x22: '\\"', 0x5C: "\\\\"}


def _jcs_string(text):
    out = ['"']
    for ch in text:
        code = ord(ch)
        if code in _SHORT_ESCAPES:
            out.append(_SHORT_ESCAPES[code])
        elif code < 0x20:
            out.append("\\u%04x" % code)
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _utf16_key(name):
    return name.encode("utf-16-be")


def canonical_json(value):
    """Serialize a metadata-subset value as RFC 8785 (JCS) text (ADR-0002).

    The walk uses an explicit stack. A success value nested to the configured
    depth ceiling is deeper than the default call limit. The text is JCS either way.
    """
    chunks = []
    stack = [("val", value)]
    while stack:
        kind, item = stack.pop()
        if kind == "lit":
            chunks.append(item)
            continue
        if item is None:
            chunks.append("null")
        elif item is True:
            chunks.append("true")
        elif item is False:
            chunks.append("false")
        elif isinstance(item, int):
            if not -MAX_SAFE_INT <= item <= MAX_SAFE_INT:
                raise ValueError("integer outside the interoperable range: %d" % item)
            chunks.append(str(item))
        elif isinstance(item, str):
            item.encode("utf-8")  # raises on lone surrogates
            chunks.append(_jcs_string(item))
        elif isinstance(item, list):
            chunks.append("[")
            if not item:
                chunks.append("]")
                continue
            stack.append(("lit", "]"))
            for index in range(len(item) - 1, 0, -1):
                stack.append(("val", item[index]))
                stack.append(("lit", ","))
            stack.append(("val", item[0]))
        elif isinstance(item, dict):
            names = sorted(item, key=_utf16_key)
            chunks.append("{")
            if not names:
                chunks.append("}")
                continue
            stack.append(("lit", "}"))
            for index in range(len(names) - 1, 0, -1):
                name = names[index]
                stack.append(("val", item[name]))
                stack.append(("lit", _jcs_string(name) + ":"))
                stack.append(("lit", ","))
            name = names[0]
            stack.append(("val", item[name]))
            stack.append(("lit", _jcs_string(name) + ":"))
        else:
            raise ValueError("value outside the metadata subset: %s" % type(item).__name__)
    return "".join(chunks)


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
        if "/%s/** %s" % (tree, BYTE_EXACT_ATTRS) not in attrs:
            errors.append(".gitattributes: /%s/** must set %s" % (tree, BYTE_EXACT_ATTRS))
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
    errors.extend(check_invisible_text(root))
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


# Characters that are invisible or reinterpret text, never allowed raw in reviewed text:
# C0 controls other than TAB, LF, and CR, DEL, C1 controls, U+2028/U+2029, bidi controls,
# zero-width characters, and the BOM. Metadata writes them as JSON \u escapes.
INVISIBLE_RE = re.compile(
    "[\\x00-\\x08\\x0b\\x0c\\x0e-\\x1f\\x7f-\\x9f\\u061c\\u200b-\\u200f\\u2028-\\u202e\\u2060\\u2066-\\u2069\\ufeff]"
)
TEXT_TREES = ("docs", "generators", "manifests", "recipes", "schemas", "tests", "tools", ".github")
TEXT_FILES = ("README.md", "AGENTS.md", "Makefile", ".gitattributes", ".gitignore")


def check_invisible_text(root):
    """Reviewed text outside the byte-exact trees holds no raw invisible characters."""
    errors = []
    paths = [os.path.join(root, f) for f in TEXT_FILES]
    for tree in TEXT_TREES:
        top = os.path.join(root, tree)
        if os.path.isdir(top):
            paths.extend(_walk_files(top))
    for path in paths:
        if not os.path.isfile(path) or "__pycache__" in os.path.relpath(path, root).split(os.sep):
            continue
        rel = os.path.relpath(path, root).replace(os.sep, "/")
        with open(path, "rb") as fh:
            data = fh.read()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue  # not text
        for lineno, line in enumerate(text.split("\n"), 1):
            m = INVISIBLE_RE.search(line)
            if m:
                errors.append("%s:%d: raw U+%04X; write it as an escape" % (rel, lineno, ord(m.group(0))))
                break
    return errors


CASE_REQUIRED = (
    "schema_version",
    "id",
    "revision",
    "format",
    "dialect",
    "category",
    "classifiers",
    "provenance",
    "input",
    "expectations",
    "execution",
    "review",
)
SUPPORTED = {
    "case": "case/v1",
    "profile": "profile/v1",
    "span": "span-convention/v1",
    "upstreams": "upstreams-lock/v1",
    "recipe": "recipe/v1",
    "hydrated": "hydrated/v1",
    "formats": "formats/v1",
}
TIER_CAPS = {"smoke": 16 * 1024 * 1024, "conformance": 128 * 1024 * 1024, "stress": 256 * 1024 * 1024}
TIER_ORDER = ("smoke", "conformance", "stress")
HYDRATE_MARKER = ".structcorpus-hydrated.json"
EVENT_RE = re.compile(r"^[+=-][A-Z]{3}( .*)?$")
# The pinned notation escapes exactly these five control characters (as \0, \b,
# \t, \n, \r) and the backslash; every other character, including BEL, VT, FF,
# ESC, and DEL, appears in event text as itself.
EVENT_ESCAPED_RAW_RE = re.compile(r"[\x00\x08\x09\x0a\x0d]")
ERROR_PHASES = {"input", "syntax", "resolution", "structure", "limit", "typed"}
LIMIT_FIELDS = (
    "max_input_bytes",
    "max_depth",
    "max_nodes",
    "max_expanded_nodes",
    "max_alias_events",
    "max_owned_bytes",
    "max_scalar_bytes",
    "max_key_bytes",
    "max_mapping_entries",
    "max_documents",
    "max_output_bytes",
    "max_warnings",
)
TYPED_TARGETS = {
    "u8",
    "u16",
    "u32",
    "u64",
    "u128",
    "i8",
    "i16",
    "i32",
    "i64",
    "i128",
    "f32",
    "f64",
    "bool",
    "string",
    "option-bool",
}


def _read_json(root, rel, errors):
    try:
        with open(os.path.join(root, rel), "rb") as fh:
            return load_json_strict(fh.read())
    except (OSError, ValueError) as exc:
        errors.append("%s: %s" % (rel, exc))
        return None


def _load_registry(root, top_rel, kind, errors):
    """Load versioned records from <top_rel>/<id>.r<N>.json (a directory declared in the format registry)."""
    out = {}
    top = os.path.join(root, *top_rel.split("/"))
    if not os.path.isdir(top):
        errors.append("%s: declared registry directory is missing" % top_rel)
        return out
    for name in sorted(os.listdir(top)):
        rel = "%s/%s" % (top_rel, name)
        doc = _read_json(root, rel, errors)
        if not isinstance(doc, dict):
            continue
        if doc.get("schema_version") != SUPPORTED[kind]:
            errors.append("%s: unsupported schema_version %r" % (rel, doc.get("schema_version")))
            continue
        expected = "%s.r%s.json" % (doc.get("id"), doc.get("revision"))
        if name != expected:
            errors.append("%s: file name must be %s" % (rel, expected))
            continue
        out[(doc["id"], doc["revision"])] = doc
    return out


# ---- format registry (DDR-0014) ------------------------------------------------

FORMATS_REL = "manifests/formats.json"
AGGREGATE_REL = "manifests/cases.jsonl"
FORMAT_ID_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
DIALECT_RE = re.compile(r"^[a-z0-9][a-z0-9.-]{0,63}$")
EXTENSION_RE = re.compile(r"^\.[a-z0-9]{1,15}$")
# Each inventory a format may declare, and the one repository path it may use.
INVENTORY_PATHS = {
    "cases": "manifests/{0}/cases.jsonl",
    "profiles": "manifests/{0}/profiles",
    "span_conventions": "manifests/{0}/span-conventions",
    "upstreams": "manifests/{0}/upstreams.lock.json",
    "fixtures": "fixtures/{0}",
    "recipes": "recipes/{0}",
    "generators": "generators/{0}",
}
INVENTORY_FILES = ("cases", "upstreams")
FORMAT_MEMBERS = ("status", "dialects", "generated_input_extension") + tuple(INVENTORY_PATHS)
# Formats this tool implements: the dialects its format-specific checks support, the
# inventories the format must declare, and the suffix of its hydrated generated inputs.
# A registry entry for any other format is refused, even when it says active.
IMPLEMENTED_FORMATS = {
    "yaml": {
        "dialects": ("yaml-1.2.2",),
        "inventories": tuple(INVENTORY_PATHS),
        "generated_input_extension": ".yaml",
    },
}


def _registry_path_problem(root, rel, kind, fmt):
    """Why a declared registry path is unusable, or None."""
    if not isinstance(rel, str):
        return "path must be a string"
    parts = rel.split("/")
    if (
        rel.startswith("/")
        or "\\" in rel
        or ":" in rel
        or any(p in ("", ".", "..") for p in parts)
        or path_problems(rel)
    ):
        return "%r is not a normalized repository-relative path" % rel
    if rel == AGGREGATE_REL:
        return "%s is the root aggregate and cannot also be a format shard" % rel
    if rel == FORMATS_REL:
        return "%s is the format registry itself" % rel
    current = root
    for part in parts:
        current = os.path.join(current, part)
        if os.path.islink(current):
            return "%s is a symbolic link" % os.path.relpath(current, root).replace(os.sep, "/")
    if not _inside(current, root):
        return "%s resolves outside the repository" % rel
    if kind in INVENTORY_FILES and not os.path.isfile(current):
        return "%s is missing (expected a file)" % rel
    if kind not in INVENTORY_FILES and not os.path.isdir(current):
        return "%s is missing (expected a directory)" % rel
    expected = INVENTORY_PATHS[kind].format(fmt)
    if rel != expected:
        return "must be %s, not %s" % (expected, rel)
    return None


def load_formats(root, errors):
    """Read and check the format registry. Returns {format: entry} for usable, implemented formats.

    Every problem is appended to errors; an entry with any problem is left out of the result.
    """
    doc = _read_json(root, FORMATS_REL, errors)
    if doc is None:
        return {}
    if not isinstance(doc, dict):
        errors.append("%s: registry is not an object" % FORMATS_REL)
        return {}
    unknown = sorted(set(doc) - {"schema_version", "formats"})
    if unknown:
        errors.append("%s: unknown member(s) %s" % (FORMATS_REL, ", ".join(unknown)))
    if doc.get("schema_version") != SUPPORTED["formats"]:
        errors.append("%s: unsupported schema_version %r" % (FORMATS_REL, doc.get("schema_version")))
        return {}
    formats = doc.get("formats")
    if not isinstance(formats, dict) or not formats:
        errors.append("%s: formats must be a non-empty object" % FORMATS_REL)
        return {}
    usable = {}
    owners = []
    for fmt in sorted(formats):
        entry = formats[fmt]
        where = "%s: %s" % (FORMATS_REL, fmt)
        before = len(errors)
        if not isinstance(fmt, str) or not FORMAT_ID_RE.match(fmt):
            errors.append("%s: invalid format id" % where)
            continue
        if not isinstance(entry, dict):
            errors.append("%s: entry is not an object" % where)
            continue
        unknown = sorted(set(entry) - set(FORMAT_MEMBERS))
        if unknown:
            errors.append("%s: unknown member(s) %s" % (where, ", ".join(unknown)))
        if entry.get("status") != "active":
            errors.append('%s: status must be "active", not %r' % (where, entry.get("status")))
        dialects = entry.get("dialects")
        if (
            not isinstance(dialects, list)
            or not dialects
            or not all(isinstance(d, str) and DIALECT_RE.match(d) for d in dialects)
            or len(set(dialects)) != len(dialects)
        ):
            errors.append("%s: dialects must be a non-empty list of distinct dialect names" % where)
            dialects = []
        if "cases" not in entry and "recipes" not in entry:
            errors.append("%s: declares neither cases nor recipes" % where)
        if ("recipes" in entry) != ("generators" in entry):
            errors.append("%s: recipes and generators are declared together" % where)
        if ("recipes" in entry) != ("generated_input_extension" in entry):
            errors.append("%s: generated_input_extension is declared exactly when recipes are" % where)
        if "fixtures" in entry and "cases" not in entry:
            errors.append("%s: fixtures are declared only with cases" % where)
        ext = entry.get("generated_input_extension")
        if ext is not None and not (isinstance(ext, str) and EXTENSION_RE.match(ext)):
            errors.append("%s: generated_input_extension %r is not a suffix like .ext" % (where, ext))
        for kind in INVENTORY_PATHS:
            if kind not in entry:
                continue
            problem = _registry_path_problem(root, entry[kind], kind, fmt)
            if problem:
                errors.append("%s.%s: %s" % (where, kind, problem))
            if isinstance(entry[kind], str):
                owners.append((entry[kind], fmt, kind))
        impl = IMPLEMENTED_FORMATS.get(fmt)
        if impl is None:
            errors.append("%s: format is not implemented by this tool; an active entry does not enable it" % where)
        else:
            for d in dialects:
                if d not in impl["dialects"]:
                    errors.append("%s: dialect %r is not implemented for %s" % (where, d, fmt))
            missing = [k for k in impl["inventories"] if k not in entry]
            if missing:
                errors.append("%s: must declare %s" % (where, ", ".join(missing)))
            if ext is not None and ext != impl["generated_input_extension"]:
                errors.append(
                    "%s: generated_input_extension must be %r for %s" % (where, impl["generated_input_extension"], fmt)
                )
        if len(errors) == before:
            usable[fmt] = entry
    for i, (a, fa, ka) in enumerate(owners):
        for b, fb, kb in owners[i + 1 :]:
            if a == b or a.startswith(b + "/") or b.startswith(a + "/"):
                errors.append("%s: %s.%s (%s) overlaps %s.%s (%s)" % (FORMATS_REL, fa, ka, a, fb, kb, b))
                usable.pop(fa, None)
                usable.pop(fb, None)
    return usable


def check_layout(root):
    """The registry is valid, and every format directory and manifest path is one it declares."""
    errors = []
    formats = load_formats(root, errors)
    for tree, kind in (("fixtures", "fixtures"), ("recipes", "recipes"), ("generators", "generators")):
        top = os.path.join(root, tree)
        if not os.path.isdir(top):
            continue
        for name in sorted(os.listdir(top)):
            rel = "%s/%s" % (tree, name)
            if name not in formats or formats[name].get(kind) != rel:
                errors.append("%s: not a %s directory declared by an active format in %s" % (rel, kind, FORMATS_REL))
    top = os.path.join(root, "manifests")
    names = sorted(os.listdir(top)) if os.path.isdir(top) else []
    for name in names:
        rel = "manifests/" + name
        if rel in (FORMATS_REL, AGGREGATE_REL):
            continue
        full = os.path.join(top, name)
        if name not in formats or os.path.islink(full) or not os.path.isdir(full):
            errors.append("%s: not a format directory declared by an active format in %s" % (rel, FORMATS_REL))
            continue
        declared = {formats[name][k] for k in INVENTORY_PATHS if k in formats[name]}
        for child in sorted(os.listdir(full)):
            if "%s/%s" % (rel, child) not in declared:
                errors.append("%s/%s: not declared by %s for %s" % (rel, child, FORMATS_REL, name))
    if not os.path.isfile(os.path.join(root, *AGGREGATE_REL.split("/"))) or os.path.islink(
        os.path.join(root, *AGGREGATE_REL.split("/"))
    ):
        errors.append("%s: aggregate is missing; run `python3 tools/corpus.py aggregate`" % AGGREGATE_REL)
    for fmt in sorted(formats):
        for kind in INVENTORY_PATHS:
            rel = formats[fmt].get(kind)
            if rel is None or kind in INVENTORY_FILES:
                continue
            if not [n for n in os.listdir(os.path.join(root, *rel.split("/"))) if n != "__pycache__"]:
                errors.append("%s: %s declares %s, but it is empty" % (rel, fmt, kind))
    return errors


def _read_shard(root, rel, errors):
    """A case shard's bytes. A non-empty shard of LF-terminated lines; returns None if unusable."""
    try:
        with open(os.path.join(root, *rel.split("/")), "rb") as fh:
            data = fh.read()
    except OSError as exc:
        errors.append("%s: %s" % (rel, exc))
        return None
    if not data.strip():
        errors.append("%s: case shard has no records" % rel)
        return None
    if not data.endswith(b"\n") or b"\r" in data:
        errors.append("%s: case shard lines must each end with LF" % rel)
        return None
    return data


def build_aggregate(root, formats, errors):
    """The root static-case aggregate: each format's shard bytes, in sorted format-id order."""
    chunks = []
    for fmt in sorted(formats):
        rel = formats[fmt].get("cases")
        if rel is None:
            continue
        data = _read_shard(root, rel, errors)
        if data is not None:
            chunks.append(data)
    return b"".join(chunks)


def check_aggregate(root, formats):
    """The committed aggregate must equal the regenerated one byte for byte."""
    errors = []
    expected = build_aggregate(root, formats, errors)
    if errors:
        return errors
    path = os.path.join(root, *AGGREGATE_REL.split("/"))
    if os.path.islink(path) or not os.path.isfile(path):
        return ["%s: aggregate is missing; run `python3 tools/corpus.py aggregate`" % AGGREGATE_REL]
    with open(path, "rb") as fh:
        actual = fh.read()
    if actual != expected:
        got, want = actual.split(b"\n"), expected.split(b"\n")
        line = next((i for i, (g, w) in enumerate(zip(got, want), 1) if g != w), min(len(got), len(want)))
        counts = (actual.count(b"\n"), expected.count(b"\n"), line)
        errors.append(
            "%s: stale aggregate: %d lines, the format shards give %d; first difference at line %d; "
            "run `python3 tools/corpus.py aggregate`" % ((AGGREGATE_REL,) + counts)
        )
    return errors


def static_cases(root, formats, errors):
    """Yield (format, where, record) for every static case line in every shard, in aggregate order."""
    for fmt in sorted(formats):
        rel = formats[fmt].get("cases")
        if rel is None:
            continue
        data = _read_shard(root, rel, errors)
        if data is None:
            continue
        for lineno, line in enumerate(data.split(b"\n"), 1):
            if not line.strip():
                continue
            where = "%s:%d" % (rel, lineno)
            try:
                rec = load_json_strict(line)
            except ValueError as exc:
                errors.append("%s: %s" % (where, exc))
                continue
            yield fmt, where, rec


def generated_input_rel(formats, rec):
    """Path of a generated case's input inside a hydrated root, from its id and its format's suffix."""
    prefix, local = rec["id"].rsplit(".", 1)
    return "/".join(("inputs", rec["format"], prefix, local + formats[rec["format"]]["generated_input_extension"]))


def check_case(root, rec, profiles, spans, errors, where):
    if not isinstance(rec, dict):
        errors.append("%s: case is not an object" % where)
        return
    if rec.get("schema_version") != SUPPORTED["case"]:
        errors.append("%s: unsupported schema_version %r" % (where, rec.get("schema_version")))
        return
    missing = [k for k in CASE_REQUIRED if k not in rec]
    if missing:
        errors.append("%s: missing %s" % (where, ", ".join(missing)))
        return
    cls = rec["classifiers"] if isinstance(rec["classifiers"], dict) else {}
    if cls.get("sensitivity") != "0-public" or cls.get("access-tier") != "public":
        errors.append("%s: classifiers must be exactly sensitivity=0-public, access-tier=public (SecDR-0001)" % where)
    prov = rec["provenance"] if isinstance(rec["provenance"], dict) else {}
    if prov.get("origin") not in ("synthetic", "public-source") or not prov.get("license"):
        errors.append("%s: provenance needs origin synthetic|public-source and a license (SecDR-0001)" % where)
    elif prov.get("origin") == "public-source" and not prov.get("upstream"):
        errors.append("%s: public-source provenance needs an upstream reference" % where)
    inp = rec["input"] if isinstance(rec["input"], dict) else {}
    if ("path" in inp) == ("recipe" in inp):
        errors.append("%s: input needs exactly one of path or recipe" % where)
    elif "path" in inp:
        rel = inp["path"]
        if not isinstance(rel, str) or not rel.startswith("fixtures/%s/" % rec.get("format")) or path_problems(rel):
            errors.append("%s: unsafe or misplaced input path %r" % (where, rel))
        else:
            full = os.path.join(root, *rel.split("/"))
            if os.path.islink(full) or not os.path.isfile(full):
                errors.append("%s: input %s is missing" % (where, rel))
            else:
                with open(full, "rb") as fh:
                    data = fh.read()
                if hashlib.sha256(data).hexdigest() != inp.get("sha256") or len(data) != inp.get("bytes"):
                    errors.append("%s: input %s does not match recorded sha256/bytes" % (where, rel))
    exp = rec["expectations"] if isinstance(rec["expectations"], dict) else {}
    if not exp:
        errors.append("%s: no expectations" % where)
    events = exp.get("events")
    event_list = None
    if events is not None:
        notation = events.get("notation")
        if notation not in event_notation.NOTATIONS:
            errors.append("%s: unknown event notation %r" % (where, notation))
        if events.get("status") == "valid":
            event_list = events.get("events")
            if not isinstance(event_list, list) or not all(
                isinstance(e, str) and EVENT_RE.match(e) for e in event_list
            ):
                errors.append("%s: valid events need an event list in the declared notation" % where)
                event_list = None
            elif notation == event_notation.YTS and any(EVENT_ESCAPED_RAW_RE.search(e) for e in event_list):
                errors.append(
                    "%s: event text contains a raw NUL, BS, TAB, LF, or CR; the notation escapes these" % where
                )
            elif notation == event_notation.SCE1:
                # New-notation grammar is strict; historical legacy validation is unchanged.
                for i, e in enumerate(event_list):
                    try:
                        event_notation.parse(e, notation)
                    except event_notation.NotationError as exc:
                        errors.append("%s: event %d: %s" % (where, i, exc))
                        break
        elif events.get("status") == "invalid":
            if "events" in events:
                errors.append("%s: invalid input must not list events" % where)
        else:
            errors.append("%s: events.status must be valid or invalid" % where)
    for v in exp.get("value", []):
        key = (v.get("profile"), v.get("profile_revision"))
        if key not in profiles:
            errors.append("%s: unknown profile %s r%s" % (where, key[0], key[1]))
        err = v.get("error")
        if err is not None and err.get("phase") not in ERROR_PHASES:
            errors.append("%s: unknown error phase %r" % (where, err.get("phase")))
        if err is not None:
            check_limit_error(err, profiles.get(key), errors, where)
    for t in exp.get("typed", []):
        if (t.get("profile"), t.get("profile_revision")) not in profiles:
            errors.append("%s: unknown profile %s r%s" % (where, t.get("profile"), t.get("profile_revision")))
        if t.get("target") not in TYPED_TARGETS:
            errors.append("%s: unknown typed target %r" % (where, t.get("target")))
        if ("result" in t) == ("error" in t):
            errors.append("%s: a typed entry needs exactly one of result or error" % where)
        elif "error" in t and t["error"].get("phase") not in ERROR_PHASES:
            errors.append("%s: unknown error phase %r" % (where, t["error"].get("phase")))
        path = t.get("path")
        if not isinstance(path, list) or not all(
            isinstance(p, str) or (isinstance(p, int) and not isinstance(p, bool) and p >= 0) for p in path
        ):
            errors.append("%s: typed path must list mapping keys and sequence indexes" % where)
    loc = exp.get("locations")
    if loc is not None:
        conv = spans.get((loc.get("convention"), loc.get("convention_revision")))
        if conv is None:
            errors.append(
                "%s: unknown span convention %s r%s" % (where, loc.get("convention"), loc.get("convention_revision"))
            )
        elif event_list is None:
            errors.append("%s: locations need a valid event list" % where)
        else:
            size = inp.get("bytes", 0)
            for s in loc.get("spans", []):
                i = s.get("event_index")
                if not isinstance(i, int) or not 0 <= i < len(event_list):
                    errors.append("%s: span event_index %r out of range" % (where, i))
                    continue
                if event_list[i][:4] not in conv.get("defined_events", []):
                    errors.append(
                        "%s: %s spans are undefined in %s r%d"
                        % (where, event_list[i][:4], conv["id"], conv["revision"])
                    )
                if not 0 <= s.get("start", -1) <= s.get("end", -1) <= size:
                    errors.append("%s: span [%r, %r) outside input" % (where, s.get("start"), s.get("end")))
    nodes = exp.get("node_locations")
    if nodes is not None:
        check_node_locations(nodes, exp.get("value", []), inp.get("bytes", 0), spans, errors, where)
    review = rec["review"] if isinstance(rec["review"], dict) else {}
    if review.get("status") == "reviewed" and (
        not review.get("reviewer") or review.get("reviewer") == review.get("author")
    ):
        errors.append("%s: a reviewed case needs a reviewer distinct from its author" % where)


def check_limit_error(err, profile, errors, where):
    """A limit error names a Limits field; a configured value must equal the profile's (DDR-0009)."""
    if err.get("phase") != "limit":
        if "configured" in err:
            errors.append("%s: configured is only for limit errors" % where)
        return
    if err.get("limit") not in LIMIT_FIELDS:
        errors.append("%s: limit %r is not a Limits field" % (where, err.get("limit")))
        return
    if "configured" not in err:
        return
    limits = (profile or {}).get("limits")
    if limits is None:
        errors.append("%s: configured needs a profile with explicit limits" % where)
    elif err["configured"] != limits.get(err["limit"]):
        errors.append(
            "%s: configured %r does not match the profile's %s = %r"
            % (where, err["configured"], err["limit"], limits.get(err["limit"]))
        )


def select_node(root, path):
    """Follow a node path (DDR-0008) into a yaml-value/1 tree. Returns the node or None."""
    node = root
    if not isinstance(path, list):
        return None
    for step in path:
        if not isinstance(node, dict) or not isinstance(step, dict) or len(step) != 1:
            return None
        ((kind, arg),) = step.items()
        if kind == "inner":
            if arg is not True:
                return None
            node = node.get("inner")  # absent unless the node is tagged
        elif kind in ("key", "value"):
            entries = node.get("entries") if node.get("t") == "map" else None
            if not isinstance(arg, int) or isinstance(arg, bool) or entries is None or not 0 <= arg < len(entries):
                return None
            entry = entries[arg]
            if not isinstance(entry, list) or len(entry) != 2:
                return None
            node = entry[0 if kind == "key" else 1]
        elif kind == "item":
            items = node.get("items") if node.get("t") == "seq" else None
            if not isinstance(arg, int) or isinstance(arg, bool) or items is None or not 0 <= arg < len(items):
                return None
            node = items[arg]
        else:
            return None
    return node if isinstance(node, dict) else None  # a leaf that is not a node


def check_node_locations(nodes, values, size, spans, errors, where):
    """Node spans name a profile's value tree and a node convention (DDR-0008)."""
    conv = spans.get((nodes.get("convention"), nodes.get("convention_revision")))
    if conv is None or conv.get("selects") != "value-node":
        errors.append(
            "%s: unknown node convention %s r%s" % (where, nodes.get("convention"), nodes.get("convention_revision"))
        )
        return
    bound = [
        v
        for v in values
        if (v.get("profile"), v.get("profile_revision")) == (nodes.get("profile"), nodes.get("profile_revision"))
    ]
    if len(bound) != 1 or "documents" not in bound[0]:
        errors.append("%s: node locations need a value expectation with documents under the same profile" % where)
        return
    documents = bound[0]["documents"]
    for s in nodes.get("spans", []):
        d = s.get("document")
        if not isinstance(d, int) or isinstance(d, bool) or not 0 <= d < len(documents):
            errors.append("%s: node span document %r out of range" % (where, d))
            continue
        node = select_node(documents[d], s.get("path", []))
        if node is None:
            errors.append(
                "%s: node path %s does not resolve in the value tree" % (where, canonical_json(s.get("path")))
            )
            continue
        if node.get("t") not in conv["defined_nodes"]:
            errors.append(
                "%s: %s node spans are undefined in %s r%d" % (where, node.get("t"), conv["id"], conv["revision"])
            )
        if not 0 <= s.get("start", -1) <= s.get("end", -1) <= size:
            errors.append("%s: node span [%r, %r) outside input" % (where, s.get("start"), s.get("end")))


def check_profile_limits(rel, prof, errors):
    """The cited specification's Options::validate rules, applied to a profile's explicit limits."""
    lim = prof.get("limits")
    if lim is None:
        return
    if not isinstance(lim, dict) or set(lim) != set(LIMIT_FIELDS):
        errors.append("%s: limits must name exactly the specification's %d Limits fields" % (rel, len(LIMIT_FIELDS)))
        return
    bad = [k for k in LIMIT_FIELDS if not isinstance(lim[k], int) or isinstance(lim[k], bool) or lim[k] < 1]
    if bad:
        errors.append("%s: every limit must be an integer >= 1 (%s)" % (rel, ", ".join(bad)))
        return
    if lim["max_depth"] > 255:
        errors.append("%s: max_depth must be <= 255" % rel)
    for k in ("max_scalar_bytes", "max_key_bytes"):
        if lim[k] > lim["max_owned_bytes"]:
            errors.append("%s: %s must be <= max_owned_bytes" % (rel, k))


def load_profiles(root, entry, errors):
    """A format's profile registry; empty when the format declares none."""
    if "profiles" not in entry:
        return {}
    return _load_registry(root, entry["profiles"], "profile", errors)


def check_manifests(root):
    """Every format's profiles, span conventions, upstream lock, and case shard, plus the aggregate."""
    errors = []
    formats = load_formats(root, errors)
    registry_ok = not errors
    seen = {}
    for fmt in sorted(formats):
        entry = formats[fmt]
        profiles = load_profiles(root, entry, errors)
        for (pid, rev), prof in sorted(profiles.items()):
            rel = "%s/%s.r%d.json" % (entry["profiles"], pid, rev)
            check_profile_limits(rel, prof, errors)
            if prof.get("dialect") not in entry["dialects"]:
                errors.append("%s: dialect %r is not declared for %s" % (rel, prof.get("dialect"), fmt))
        spans = _load_registry(root, entry["span_conventions"], "span", errors) if "span_conventions" in entry else {}
        if "upstreams" in entry:
            lock = _read_json(root, entry["upstreams"], errors)
            if isinstance(lock, dict) and lock.get("schema_version") != SUPPORTED["upstreams"]:
                errors.append("%s: unsupported schema_version %r" % (entry["upstreams"], lock.get("schema_version")))
        referenced = set()
        for _fmt, where, rec in static_cases(root, {fmt: entry}, errors):
            cid = rec.get("id") if isinstance(rec, dict) else None
            if not isinstance(cid, str) or not COMPONENT_RE.match(cid) or len(cid) > 100:
                errors.append("%s: invalid case id %r" % (where, cid))
            elif cid in seen:
                errors.append("%s: duplicate case id %s (also %s)" % (where, cid, seen[cid]))
            else:
                seen[cid] = where
            if isinstance(rec, dict) and rec.get("format") != fmt:
                errors.append(
                    "%s (%s): format %r does not match its shard's format %r" % (where, cid, rec.get("format"), fmt)
                )
            elif isinstance(rec, dict) and rec.get("dialect") not in entry["dialects"]:
                errors.append("%s (%s): dialect %r is not declared for %s" % (where, cid, rec.get("dialect"), fmt))
            check_case(root, rec, profiles, spans, errors, "%s (%s)" % (where, cid))
            if isinstance(rec, dict) and isinstance(rec.get("input"), dict) and "path" in rec["input"]:
                referenced.add(rec["input"]["path"])
        if "fixtures" in entry:
            for full in _walk_files(os.path.join(root, *entry["fixtures"].split("/"))):
                frel = os.path.relpath(full, root).replace(os.sep, "/")
                if os.path.basename(frel) in (".gitkeep", "README.md"):
                    continue
                if frel not in referenced:
                    errors.append("%s: fixture not referenced by any case" % frel)
    if registry_ok:
        errors.extend(check_aggregate(root, formats))
    return errors


# ---- recipes, hydration, verification (DDR-0004) -----------------------------


def _load_generator(root, rel):
    path = os.path.join(root, *rel.split("/"))
    spec = importlib.util.spec_from_file_location("structcorpus_gen_" + os.path.basename(rel)[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_recipes(root, errors, formats=None):
    """Recipe records from each registered format's recipe directory, keyed by repository path."""
    if formats is None:
        formats = load_formats(root, errors)
    out = {}
    for fmt in sorted(formats):
        top_rel = formats[fmt].get("recipes")
        if top_rel is None:
            continue
        for name in sorted(os.listdir(os.path.join(root, *top_rel.split("/")))):
            rel = "%s/%s" % (top_rel, name)
            full = os.path.join(root, *rel.split("/"))
            if not name.endswith(".json") or os.path.islink(full) or not os.path.isfile(full):
                errors.append("%s: not a recipe record" % rel)
                continue
            doc = _read_json(root, rel, errors)
            if not isinstance(doc, dict):
                continue
            if doc.get("schema_version") != SUPPORTED["recipe"]:
                errors.append("%s: unsupported schema_version %r" % (rel, doc.get("schema_version")))
                continue
            if doc.get("format") != fmt:
                errors.append(
                    "%s: format %r does not match its recipe directory's format %r" % (rel, doc.get("format"), fmt)
                )
                continue
            if doc.get("dialect") not in formats[fmt]["dialects"]:
                errors.append("%s: dialect %r is not declared for %s" % (rel, doc.get("dialect"), fmt))
                continue
            expected_rel = "%s/%s.r%s.json" % (top_rel, doc.get("id"), doc.get("revision"))
            if rel != expected_rel:
                errors.append("%s: path must be %s" % (rel, expected_rel))
                continue
            out[rel] = doc
    return out


def check_case_namespace(static_ids, recipes):
    """Static and generated case ids share one namespace (DDR-0004, DDR-0014).

    A generated id is <recipe id>.<local id>. Recipe ids are unique, no recipe id is a
    dotted prefix of another, and no static id lies inside a recipe's generated prefix.
    """
    errors = []
    by_id = {}
    for rel in sorted(recipes):
        rid = recipes[rel].get("id")
        if rid in by_id:
            errors.append("%s: recipe id %s is also declared by %s" % (rel, rid, by_id[rid]))
        else:
            by_id[rid] = rel
    ids = sorted(by_id)
    for a in ids:
        for b in ids:
            if b.startswith(a + "."):
                errors.append("%s: recipe ids %s and %s share a generated case-id namespace" % (by_id[b], a, b))
    for cid, where in sorted(static_ids.items()):
        for rid in ids:
            if cid.startswith(rid + "."):
                errors.append(
                    "%s: static case id %s is inside the generated case-id namespace of recipe %s (%s)"
                    % (where, cid, rid, by_id[rid])
                )
    return errors


def check_recipe(root, rel, doc, profiles, errors):
    cls = doc.get("classifiers") if isinstance(doc.get("classifiers"), dict) else {}
    if cls.get("sensitivity") != "0-public" or cls.get("access-tier") != "public":
        errors.append("%s: classifiers must be exactly sensitivity=0-public, access-tier=public (SecDR-0001)" % rel)
    prov = doc.get("provenance") if isinstance(doc.get("provenance"), dict) else {}
    if prov.get("origin") != "synthetic" or not prov.get("license"):
        errors.append("%s: recipes are synthetic with a license (SecDR-0001)" % rel)
    if (doc.get("profile"), doc.get("profile_revision")) not in profiles:
        errors.append("%s: unknown profile %s r%s" % (rel, doc.get("profile"), doc.get("profile_revision")))
    gen = doc.get("generator")
    if (
        not isinstance(gen, str)
        or not gen.startswith("generators/%s/" % doc.get("format"))
        or path_problems(gen)
        or not os.path.isfile(os.path.join(root, *gen.split("/")))
    ):
        errors.append("%s: generator %r is missing or misplaced" % (rel, gen))
    ex = doc.get("execution") if isinstance(doc.get("execution"), dict) else {}
    exp = doc.get("expected") if isinstance(doc.get("expected"), dict) else {}
    cap = TIER_CAPS.get(ex.get("tier"))
    if cap is None or not isinstance(ex.get("max_output_bytes"), int) or ex["max_output_bytes"] > cap:
        errors.append("%s: max_output_bytes must be set and within the %s tier cap" % (rel, ex.get("tier")))
    if (
        not isinstance(exp.get("cases"), int)
        or not isinstance(ex.get("max_cases"), int)
        or exp["cases"] > ex["max_cases"]
    ):
        errors.append("%s: expected.cases must not exceed execution.max_cases" % rel)
    review = doc.get("review") if isinstance(doc.get("review"), dict) else {}
    if review.get("status") == "reviewed" and (
        not review.get("reviewer") or review.get("reviewer") == review.get("author")
    ):
        errors.append("%s: a reviewed recipe needs a reviewer distinct from its author" % rel)
    if ex.get("hazards") and not ex.get("budgets"):
        errors.append("%s: a recipe with hazards must declare per-case budgets (SecDR-0002)" % rel)


class HydrateError(Exception):
    pass


def _inside(path, root):
    path, root = os.path.realpath(path), os.path.realpath(root)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _recipe_cases(root, rel, doc):
    """Yield concrete case records for one recipe, enforcing its declared caps."""
    formats = load_formats(root, [])
    if doc.get("format") not in formats:
        raise HydrateError("%s: format %r is not registered and active" % (rel, doc.get("format")))
    gen = _load_generator(root, doc["generator"])
    profile = load_profiles(root, formats[doc["format"]], []).get((doc["profile"], doc["profile_revision"]))
    for name, value in sorted(doc["parameters"].items()):
        # A generator may receive a profile limit as limit_<field>; it must be the profile's value.
        if name.startswith("limit_"):
            field = name[len("limit_") :]
            limits = (profile or {}).get("limits") or {}
            if field not in LIMIT_FIELDS or limits.get(field) != value:
                raise HydrateError("%s: parameter %s=%r does not match the profile's %s" % (rel, name, value, field))
    cap_cases = doc["execution"]["max_cases"]
    cap_bytes = doc["execution"]["max_output_bytes"]
    total = 0
    seen = set()
    for count, row in enumerate(gen.generate(doc["parameters"]), 1):
        # (local_id, category, text, value, typed[, events]). value None means no value layer;
        # events, when given, is a format-level expectation (DDR-0002) bound to no profile.
        local_id, category, text, expectation, typed = row[:5]
        events = row[5] if len(row) > 5 else None
        if count > cap_cases:
            raise HydrateError("%s: generator exceeded max_cases %d" % (rel, cap_cases))
        if not isinstance(local_id, str) or not COMPONENT_RE.match(local_id) or local_id in seen:
            raise HydrateError("%s: generator produced invalid or repeated id %r" % (rel, local_id))
        seen.add(local_id)
        data = text.encode("utf-8") if isinstance(text, str) else bytes(text)
        cid = "%s.%s" % (doc["id"], local_id)
        bind = {"profile": doc["profile"], "profile_revision": doc["profile_revision"]}
        expectations = {}
        if events is not None:
            expectations["events"] = dict(events, notation="yaml-test-suite")
        if expectation is not None:
            expectations["value"] = [dict(expectation, **bind)]
        if not expectations:
            raise HydrateError("%s: generator produced %s with no expectation" % (rel, local_id))
        if expectation is not None and "error" in expectation:
            problems = []
            check_limit_error(expectation["error"], profile, problems, "%s.%s" % (doc["id"], local_id))
            if problems:
                raise HydrateError("%s: %s" % (rel, "; ".join(problems)))
        if typed:
            expectations["typed"] = [dict(entry, **bind) for entry in typed]
        record = {
            "schema_version": SUPPORTED["case"],
            "id": cid,
            "revision": doc["revision"],
            "format": doc["format"],
            "dialect": doc["dialect"],
            "category": category,
            "classifiers": doc["classifiers"],
            "provenance": doc["provenance"],
            "input": {"recipe": rel, "sha256": hashlib.sha256(data).hexdigest(), "bytes": len(data)},
            "expectations": expectations,
            "execution": _case_execution(doc["execution"]),
            "review": doc["review"],
        }
        line = canonical_json(record).encode("utf-8")
        total += len(data) + len(line) + 1  # input bytes plus its manifest line
        if total > cap_bytes:
            raise HydrateError("%s: generator exceeded max_output_bytes %d" % (rel, cap_bytes))
        yield cid, data, record, line


def _case_execution(ex):
    """A generated case inherits its recipe's tier, hazards, and per-case budgets."""
    out = {"tier": ex["tier"], "hazards": list(ex.get("hazards", []))}
    if ex.get("budgets"):
        out["budgets"] = dict(ex["budgets"])
    return out


def recipe_digest(case_lines):
    """sha256 over the recipe's canonical case lines, each newline-terminated."""
    h = hashlib.sha256()
    for line in case_lines:
        h.update(line)
        h.update(b"\n")
    return "sha256:" + h.hexdigest()


def hydrate(root, out, tier, recipe_filter=None):
    """Write every selected recipe's inputs and manifest into out. Returns a summary dict."""
    errors = []
    formats = load_formats(root, errors)
    recipes = load_recipes(root, errors, formats)
    profiles = {fmt: load_profiles(root, formats[fmt], errors) for fmt in formats}
    for rel, doc in recipes.items():
        check_recipe(root, rel, doc, profiles[doc["format"]], errors)
    static_ids = {rec.get("id") for _f, _w, rec in static_cases(root, formats, errors) if isinstance(rec, dict)}
    if errors:
        raise HydrateError("; ".join(errors))
    if _inside(out, root) or _inside(root, out):
        raise HydrateError("output root must be outside the checkout: %s" % out)
    if os.path.lexists(out):
        raise HydrateError("output root already exists; choose a new path: %s" % out)
    parent = os.path.dirname(os.path.abspath(out)) or "."
    if not os.path.isdir(parent):
        raise HydrateError("parent directory does not exist: %s" % parent)
    allowed = TIER_ORDER[: TIER_ORDER.index(tier) + 1]
    selected = sorted(
        rel
        for rel, doc in recipes.items()
        if doc["execution"]["tier"] in allowed and (recipe_filter is None or doc["id"] in recipe_filter)
    )
    work = tempfile.mkdtemp(prefix=".structcorpus-", dir=parent)
    try:
        summary = _hydrate_into(root, work, recipes, selected, tier, formats, static_ids)
        os.rename(work, out)
    except BaseException:
        _remove_own_tree(work)
        raise
    return summary


def _remove_own_tree(work):
    """Delete a temporary tree this process created; refuse anything else."""
    if not os.path.basename(work).startswith(".structcorpus-") or os.path.islink(work):
        return
    for dirpath, dirnames, filenames in os.walk(work, topdown=False):
        for name in filenames:
            os.unlink(os.path.join(dirpath, name))
        for name in dirnames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full):
                os.unlink(full)
            else:
                os.rmdir(full)
    os.rmdir(work)


def _hydrate_into(root, work, recipes, selected, tier, formats, static_ids):
    budget = TIER_CAPS[tier]
    summary = {"schema_version": SUPPORTED["hydrated"], "tier": tier, "recipes": []}
    written = 0
    generated = set()
    with open(os.path.join(work, "cases.jsonl"), "wb") as manifest:
        for rel in selected:
            doc = recipes[rel]
            lines = []
            in_bytes = 0
            for cid, data, _record, line in _recipe_cases(root, rel, doc):
                if cid in static_ids:
                    raise HydrateError("%s: generated case id %s duplicates a static case" % (rel, cid))
                if cid in generated:
                    raise HydrateError("%s: generated case id %s is produced twice" % (rel, cid))
                generated.add(cid)
                written += len(data) + len(line) + 1  # inputs and manifest both count
                if written > budget:
                    raise HydrateError("aggregate output exceeds the %s cap %d bytes" % (tier, budget))
                dest = os.path.join(work, "inputs", doc["format"], doc["id"])
                os.makedirs(dest, exist_ok=True)
                ext = formats[doc["format"]]["generated_input_extension"]
                with open(os.path.join(dest, cid.split(".")[-1] + ext), "xb") as fh:
                    fh.write(data)
                lines.append(line)
                in_bytes += len(data)
                manifest.write(line + b"\n")
            digest = recipe_digest(lines)
            exp = doc["expected"]
            if (len(lines), in_bytes, digest) != (exp["cases"], exp["input_bytes"], exp["digest"]):
                raise HydrateError(
                    "%s: output does not match recorded expected counts/digest "
                    "(got cases=%d input_bytes=%d %s)" % (rel, len(lines), in_bytes, digest)
                )
            summary["recipes"].append({"recipe": rel, "cases": len(lines), "input_bytes": in_bytes, "digest": digest})
    summary["output_bytes"] = written
    with open(os.path.join(work, HYDRATE_MARKER), "wb") as fh:
        fh.write(canonical_json(summary).encode("utf-8"))
    return summary


def verify(root, out):
    """Recheck a hydrated root against its manifest and the recipes' expected digests."""
    errors = []
    marker = os.path.join(out, HYDRATE_MARKER)
    if not os.path.isfile(marker):
        return ["%s: not a completed hydration (missing %s)" % (out, HYDRATE_MARKER)]
    with open(marker, "rb") as fh:
        summary = load_json_strict(fh.read())
    if summary.get("schema_version") != SUPPORTED["hydrated"]:
        return ["%s: unsupported schema_version %r" % (marker, summary.get("schema_version"))]
    formats = load_formats(root, errors)
    recipes = load_recipes(root, errors, formats)
    by_recipe = {}
    with open(os.path.join(out, "cases.jsonl"), "rb") as fh:
        for line in fh.read().split(b"\n"):
            if not line:
                continue
            rec = load_json_strict(line)
            if canonical_json(rec).encode("utf-8") != line:
                errors.append("%s: manifest line is not canonical" % rec.get("id"))
            rel = rec["input"]["recipe"]
            by_recipe.setdefault(rel, []).append(line)
            doc = recipes.get(rel)
            if rec.get("format") not in formats or (doc is not None and doc["format"] != rec["format"]):
                errors.append("%s: format %r is not its recipe's registered format" % (rec["id"], rec.get("format")))
                continue
            path = os.path.join(out, *generated_input_rel(formats, rec).split("/"))
            try:
                with open(path, "rb") as f:
                    data = f.read()
            except OSError:
                errors.append("%s: input missing" % rec["id"])
                continue
            if hashlib.sha256(data).hexdigest() != rec["input"]["sha256"] or len(data) != rec["input"]["bytes"]:
                errors.append("%s: input does not match manifest sha256/bytes" % rec["id"])
    # The marker is part of the untrusted output: it may only agree with the
    # manifest, never decide what gets checked. Every recipe present in the
    # manifest is verified against the checkout's recorded digest.
    listed = summary.get("recipes")
    listed_rels = (
        [e.get("recipe") for e in listed]
        if isinstance(listed, list) and all(isinstance(e, dict) for e in listed)
        else None
    )
    if listed_rels is None or sorted(listed_rels) != sorted(by_recipe) or len(set(listed_rels)) != len(listed_rels):
        errors.append("marker recipe list does not match the recipes in the manifest")
    if not by_recipe:
        errors.append("manifest contains no cases")
    for rel in sorted(by_recipe):
        doc = recipes.get(rel)
        if doc is None:
            errors.append("%s: recipe not present in this checkout" % rel)
            continue
        exp = doc["expected"]
        if len(by_recipe[rel]) != exp["cases"] or recipe_digest(by_recipe[rel]) != exp["digest"]:
            errors.append("%s: hydrated cases do not match the recipe's expected digest" % rel)
    return errors


def cmd_hydrate(args):
    try:
        summary = hydrate(args.root, args.output, args.tier, set(args.recipe) if args.recipe else None)
    except HydrateError as exc:
        print("error: %s" % exc, file=sys.stderr)
        return 1
    for r in summary["recipes"]:
        print("%s: %d cases, %d input bytes, %s" % (r["recipe"], r["cases"], r["input_bytes"], r["digest"]))
    print("hydrate: ok (%s)" % args.output)
    return 0


def cmd_verify(args):
    errors = verify(args.root_dir, args.root)
    for err in errors:
        print("error: " + err, file=sys.stderr)
    if errors:
        return 1
    print("verify: ok")
    return 0


def list_entries(root, tier, show_budgets=False):
    """Recipes and committed cases selected by tier, as plain dicts (stable order)."""
    allowed = TIER_ORDER[: TIER_ORDER.index(tier) + 1]
    errors = []
    rows = []
    formats = load_formats(root, errors)
    for rel, doc in sorted(load_recipes(root, errors, formats).items()):
        ex = doc["execution"]
        if ex["tier"] not in allowed:
            continue
        row = {
            "kind": "recipe",
            "name": rel,
            "tier": ex["tier"],
            "profile": "%s r%d" % (doc["profile"], doc["profile_revision"]),
            "cases": doc["expected"]["cases"],
            "input_bytes": doc["expected"]["input_bytes"],
            "hazards": list(ex.get("hazards", [])),
            "budgets": dict(ex.get("budgets", {})),
            "max_output_bytes": ex["max_output_bytes"],
        }
        if show_budgets:
            row["output_bytes"] = sum(len(d) + len(line) + 1 for _, d, _r, line in _recipe_cases(root, rel, doc))
        rows.append(row)
    for _fmt, _where, rec in static_cases(root, formats, errors):
        ex = rec["execution"]
        if ex["tier"] not in allowed:
            continue
        rows.append(
            {
                "kind": "case",
                "name": rec["id"],
                "tier": ex["tier"],
                "profile": ",".join(
                    sorted(
                        {"%s r%d" % (v["profile"], v["profile_revision"]) for v in rec["expectations"].get("value", [])}
                    )
                )
                or "-",
                "cases": 1,
                "input_bytes": rec["input"]["bytes"],
                "hazards": list(ex.get("hazards", [])),
                "budgets": dict(ex.get("budgets", {})),
            }
        )
    return rows


def cmd_list(args):
    rows = list_entries(args.root, args.tier, args.show_budgets)
    if args.json:
        sys.stdout.write(canonical_json({"tier": args.tier, "entries": rows}) + "\n")
        return 0
    for r in rows:
        extra = ""
        if args.show_budgets and r["kind"] == "recipe":
            extra = "  output %d/%d" % (r["output_bytes"], r["max_output_bytes"])
        hz = ",".join(r["hazards"]) or "-"
        print(
            "%-6s %-11s %7d cases %10d bytes  hazards=%s%s  %s"
            % (r["kind"], r["tier"], r["cases"], r["input_bytes"], hz, extra, r["name"])
        )
    cases = sum(r["cases"] for r in rows)
    print("list: %d entries, %d cases (tier %s and below)" % (len(rows), cases, args.tier))
    if args.show_budgets:
        out = sum(r.get("output_bytes", 0) for r in rows if r["kind"] == "recipe")
        print("list: generated output %d of %d bytes (%s tier cap)" % (out, TIER_CAPS[args.tier], args.tier))
    return 0


def cmd_canon(args):
    with open(args.file, "rb") as fh:
        value = load_json_strict(fh.read())
    sys.stdout.buffer.write(canonical_json(value).encode("utf-8"))
    return 0


def check_recipes(root):
    """Every format's recipes and generators, and the shared static and generated case-id namespace."""
    errors = []
    formats = load_formats(root, errors)
    recipes = load_recipes(root, errors, formats)
    for fmt in sorted(formats):
        entry = formats[fmt]
        if "recipes" not in entry:
            continue
        profiles = load_profiles(root, entry, errors)
        used = set()
        for rel, doc in sorted(recipes.items()):
            if doc["format"] == fmt:
                check_recipe(root, rel, doc, profiles, errors)
                used.add(doc.get("generator"))
        for full in _walk_files(os.path.join(root, *entry["generators"].split("/"))):
            grel = os.path.relpath(full, root).replace(os.sep, "/")
            if "__pycache__" not in grel.split("/") and grel not in used:
                errors.append("%s: generator not referenced by any recipe" % grel)
    static_ids = {}
    for _fmt, where, rec in static_cases(root, formats, []):
        if isinstance(rec, dict) and isinstance(rec.get("id"), str):
            static_ids.setdefault(rec["id"], where)
    errors.extend(check_case_namespace(static_ids, recipes))
    return errors


def check_all(root):
    """Every `validate` check, each distinct problem reported once."""
    errors = check_repository(root) + check_layout(root) + check_manifests(root) + check_recipes(root)
    return list(dict.fromkeys(errors))


def write_aggregate(root):
    """Regenerate the static-case aggregate from the format shards. Returns (errors, records, changed)."""
    errors = []
    formats = load_formats(root, errors)
    data = build_aggregate(root, formats, errors) if not errors else b""
    if errors:
        return errors, 0, False
    path = os.path.join(root, *AGGREGATE_REL.split("/"))
    if os.path.islink(path):
        return ["%s: is a symbolic link" % AGGREGATE_REL], 0, False
    records = sum(1 for line in data.split(b"\n") if line.strip())
    if os.path.isfile(path):
        with open(path, "rb") as fh:
            if fh.read() == data:
                return [], records, False
    mode = (os.stat(path).st_mode & 0o777) if os.path.isfile(path) else 0o644
    fd, tmp = tempfile.mkstemp(prefix=".cases-", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return [], records, True


def cmd_aggregate(args):
    errors, records, changed = write_aggregate(args.root)
    for err in errors:
        print("error: " + err, file=sys.stderr)
    if errors:
        return 1
    print("aggregate: %s %s (%d records)" % (AGGREGATE_REL, "written" if changed else "unchanged", records))
    return 0


def cmd_validate(args):
    errors = check_all(args.root)
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
    p_agg = sub.add_parser("aggregate", help="regenerate manifests/cases.jsonl from the format case shards")
    p_agg.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    p_agg.set_defaults(func=cmd_aggregate)
    p_canon = sub.add_parser("canon", help="print a JSON file in canonical form")
    p_canon.add_argument("file")
    p_canon.set_defaults(func=cmd_canon)
    p_hyd = sub.add_parser("hydrate", help="generate recipe inputs outside the checkout")
    p_hyd.add_argument("--tier", choices=TIER_ORDER, default="smoke")
    p_hyd.add_argument("--output", required=True, help="new directory outside the checkout")
    p_hyd.add_argument("--recipe", action="append", help="limit to a recipe id (repeatable)")
    p_hyd.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    p_hyd.set_defaults(func=cmd_hydrate)
    p_ver = sub.add_parser("verify", help="re-check a hydrated output root")
    p_ver.add_argument("--root", required=True, help="hydrated output root")
    p_ver.add_argument("--repo", dest="root_dir", default=ROOT, help=argparse.SUPPRESS)
    p_ver.set_defaults(func=cmd_verify)
    p_list = sub.add_parser("list", help="list recipes and cases by tier")
    p_list.add_argument("--tier", choices=TIER_ORDER, default="conformance")
    p_list.add_argument("--show-budgets", action="store_true", help="also generate recipes to report output bytes")
    p_list.add_argument("--json", action="store_true", help="canonical JSON output")
    p_list.add_argument("--root", default=ROOT, help=argparse.SUPPRESS)
    p_list.set_defaults(func=cmd_list)
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        parser.print_help(sys.stderr)
        return 2
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
