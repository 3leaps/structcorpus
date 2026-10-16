"""Resource ladders: limit boundaries and hazardous size ladders (Python 3.9+ stdlib).

Expected values follow the published yamlprims specification revision 1.3,
sections 5.4 and 6, with the limits of the recipe's profile:
https://github.com/3leaps/yamlprims/blob/spec-v1.3/docs/spec/yamlprims-spec.md

Sets (the recipe's "set" parameter):
  boundaries  for max_alias_events, max_expanded_nodes, max_mapping_entries,
              and max_nodes: inputs whose measure is one below, equal to, and
              one above the limit; only the last fails, naming that limit and
              its configured value. Every other limit is checked to hold.
  alias-fanout, nested-fanout, many-keys, late-failure, depth
              geometric stress ladders with format-level events. Expectations are recorded only where
              YAML or the profile decides them (DDR-0002); time and memory are
              measured by the runner, never expected.

Accounting here is an independent model of section 5.4 and 6: the root and
every key, value, item, and alias copy is a node; an alias event copies its
anchor's node count into both the node and the expanded-node counters and is
checked before the copy. Inputs are kept to plain scalars and untagged
collections so the model needs no weight terms beyond counting.

Each yielded case is (local_id, category, yaml_text, expectation, typed).
"""

LIMIT_NAMES = ("max_alias_events", "max_expanded_nodes", "max_mapping_entries", "max_nodes")


def S(v):
    return {"t": "str", "v": v}


def INT(n):
    return {"t": "int", "v": str(n)}


def SEQ(items):
    return {"t": "seq", "items": list(items)}


def MAP(pairs):
    return {"t": "map", "entries": [[k, v] for k, v in pairs]}


def nodes(v):
    if v["t"] == "seq":
        return 1 + sum(nodes(i) for i in v["items"])
    if v["t"] == "map":
        return 1 + sum(nodes(k) + nodes(x) for k, x in v["entries"])
    return 1


class Doc:
    """A root flow sequence of anchored definitions and aliases, with its section 6 counters."""

    def __init__(self):
        self.parts = []  # YAML text of each root item
        self.items = []  # its expected value
        self.anchors = {}  # name -> value (for copy counts)
        self.alias_events = 0
        self.expanded = 0
        self.entries = 0  # largest mapping's entry count

    def define(self, name, text, value):
        self.parts.append("&%s %s" % (name, text))
        self.items.append(value)
        self.anchors[name] = value
        if value["t"] == "map":
            self.entries = max(self.entries, len(value["entries"]))

    def alias(self, name):
        self.parts.append("*" + name)
        self.items.append(self.anchors[name])
        self.alias_events += 1
        self.expanded += nodes(self.anchors[name])

    def text(self):
        return "[" + ", ".join(self.parts) + "]\n"

    def value(self):
        return SEQ(self.items)

    def measures(self):
        return {
            "max_alias_events": self.alias_events,
            "max_expanded_nodes": self.expanded,
            "max_mapping_entries": self.entries,
            "max_nodes": nodes(self.value()),
        }


def int_seq(n):
    return "[" + ", ".join(str(i) for i in range(n)) + "]", SEQ(INT(i) for i in range(n))


def int_map(n):
    return "{" + ", ".join("k%d: %d" % (i, i) for i in range(n)) + "}", MAP((S("k%d" % i), INT(i)) for i in range(n))


def build(name, target):
    """A document whose measure for `name` is exactly target, staying small on every other counter."""
    d = Doc()
    if name == "max_alias_events":
        d.define("x", "1", INT(1))
        for _ in range(target):
            d.alias("x")
    elif name == "max_expanded_nodes":
        # Three copies of an 11-node sequence give 33; smaller targets drop items from one copy's
        # source, so a second anchor covers the remainder.
        big, rest = divmod(target, 11)
        text, value = int_seq(10)
        d.define("a", text, value)
        for _ in range(big):
            d.alias("a")
        if rest:
            text, value = int_seq(rest - 1)
            d.define("b", text, value)
            d.alias("b")
    elif name == "max_mapping_entries":
        text, value = int_map(target)
        d.parts.append(text)
        d.items.append(value)
        d.entries = target
    elif name == "max_nodes":
        # Each plain item is one node; the root sequence is one more.
        d.parts.extend(str(i) for i in range(target - 1))
        d.items.extend(INT(i) for i in range(target - 1))
    else:
        raise ValueError(name)
    return d


def gen_boundaries(limits):
    for name in LIMIT_NAMES:
        limit = limits[name]
        for delta, label in ((-1, "below"), (0, "at"), (1, "above")):
            d = build(name, limit + delta)
            m = d.measures()
            assert m[name] == limit + delta, (name, m)
            for other in LIMIT_NAMES:
                if other != name:
                    assert m[other] <= limits[other], (name, delta, other, m)
            text = d.text()
            assert len(text.encode()) <= limits["max_input_bytes"]
            if delta <= 0:
                expectation = {"documents": [d.value()]}
            else:
                expectation = {
                    "error": {"phase": "limit", "kind": "limit_exceeded", "limit": name, "configured": limit}
                }
            yield "%s-%s" % (name.replace("_", "-"), label), "resource-limits", text, expectation, None


# ---- stress ladders ------------------------------------------------------------
# Format-level events are written out by construction for these fixed shapes. Values are
# expected only where YAML decides the outcome (a duplicate key, a syntax error); everything
# else about these inputs is resource behavior, measured and never expected.

VALID = "valid"


def events(*body):
    return {"status": VALID, "events": ["+STR", "+DOC"] + list(body) + ["-DOC", "-STR"]}


INVALID = {"status": "invalid"}


def gen_alias_fanout(sizes):
    """One 64-byte scalar aliased N times: alias-event and expansion pressure."""
    scalar = "v" * 64
    for n in sizes:
        text = "a: &x %s\nb: [%s]\n" % (scalar, ", ".join(["*x"] * n))
        ev = events("+MAP", "=VAL :a", "=VAL &x :" + scalar, "=VAL :b", "+SEQ []", *(["=ALI *x"] * n), "-SEQ", "-MAP")
        yield "fanout-%06d" % n, "resource-limits", text, None, ev


def gen_nested_fanout(sizes):
    """Each level aliases the previous one twice: 2^depth copies of the base (exponential expansion)."""
    for depth in sizes:
        lines = ["a0: &a0 [x, x]"]
        body = ["+MAP", "=VAL :a0", "+SEQ [] &a0", "=VAL :x", "=VAL :x", "-SEQ"]
        for i in range(1, depth + 1):
            lines.append("a%d: &a%d [*a%d, *a%d]" % (i, i, i - 1, i - 1))
            body += ["=VAL :a%d" % i, "+SEQ [] &a%d" % i, "=ALI *a%d" % (i - 1), "=ALI *a%d" % (i - 1), "-SEQ"]
        body.append("-MAP")
        yield "nested-%02d" % depth, "resource-limits", "\n".join(lines) + "\n", None, events(*body)


def gen_many_keys(sizes):
    """N keys sharing a 32-byte prefix; and the same mapping with its first key repeated last."""
    prefix = "p" * 32
    for n in sizes:
        keys = ["%s%06d" % (prefix, i) for i in range(n)]
        lines = "".join("%s: %d\n" % (k, i) for i, k in enumerate(keys))
        body = ["+MAP"]
        for i, k in enumerate(keys):
            body += ["=VAL :" + k, "=VAL :%d" % i]
        yield "keys-%06d" % n, "resource-limits", lines, None, events(*(body + ["-MAP"]))
        dup = lines + "%s: dup\n" % keys[0]
        dup_events = events(*(body + ["=VAL :" + keys[0], "=VAL :dup", "-MAP"]))
        yield (
            "keys-%06d-dup-last" % n,
            "resource-limits",
            dup,
            {"error": {"phase": "structure", "kind": "duplicate_key"}},
            dup_events,
        )


def gen_late_failure(sizes):
    """A valid prefix of N entries, then a defect: an unclosed flow sequence, or a duplicate key."""
    for n in sizes:
        body = "".join("k%07d: %d\n" % (i, i) for i in range(n))
        yield "late-%07d-syntax" % n, "resource-limits", body + "z: [\n", {"error": {"phase": "syntax"}}, INVALID
        prefix = ["+MAP"]
        for i in range(n):
            prefix += ["=VAL :k%07d" % i, "=VAL :%d" % i]
        dup = events(*(prefix + ["=VAL :k0000000", "=VAL :x", "-MAP"]))
        yield (
            "late-%07d-dup" % n,
            "resource-limits",
            body + "k0000000: x\n",
            {"error": {"phase": "structure", "kind": "duplicate_key"}},
            dup,
        )


def gen_depth(sizes):
    """N nested flow sequences around one scalar. Format events only: specification 1.3 does not
    define how load depth is counted, so no limit expectation is recorded."""
    for n in sizes:
        text = "[" * n + "x" + "]" * n + "\n"
        ev = events(*(["+SEQ []"] * n + ["=VAL :x"] + ["-SEQ"] * n))
        yield "depth-%04d" % n, "resource-limits", text, None, ev


def generate(parameters):
    kind = parameters["set"]
    if kind == "boundaries":
        limits = {k: parameters[k] for k in LIMIT_NAMES + ("max_input_bytes",)}
        rows = gen_boundaries(limits)
    else:
        sizes = [int(x) for x in parameters["sizes"].split(",")]
        rows = {
            "alias-fanout": gen_alias_fanout,
            "nested-fanout": gen_nested_fanout,
            "many-keys": gen_many_keys,
            "late-failure": gen_late_failure,
            "depth": gen_depth,
        }[kind](sizes)
    for local_id, category, text, expectation, events_expectation in rows:
        if events_expectation is None:
            yield local_id, category, text, expectation, []
        else:
            yield local_id, category, text, expectation, [], events_expectation
