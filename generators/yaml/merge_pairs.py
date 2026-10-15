"""Inline and aliased merge sources that must load to equal values (Python 3.9+ stdlib).

Expected values follow the published yamlprims specification revision 1.1,
section 5.3, under merge_keys = Apply:
https://github.com/3leaps/yamlprims/blob/spec-v1.1/docs/spec/yamlprims-spec.md

Rule 2 accepts aliased and inline sources alike, and rule 6 charges both the
same way, so each pair differs only in how the source is written:

  alias   b: &b {...}           m: {<<: *b, ...}
  inline  b: {...}              m: {<<: {...}, ...}

Both inputs of a pair have the same expected value. Forms per size:
  first   the directive before an explicit key that shadows a source key
  last    the directive after that explicit key
  seq     a sequence of two overlapping sources; the earlier source wins

Budgets differ between the two forms of a pair and are measured, not expected
(DDR-0002). Each yielded case is (local_id, category, yaml_text, expectation,
typed).
"""

SIZES = [1, 10, 100, 1000]


def S(v):
    return {"t": "str", "v": v}


def INT(n):
    return {"t": "int", "v": str(n)}


def MAP(pairs):
    return {"t": "map", "entries": [[k, v] for k, v in pairs]}


def key(i):
    return "k%04d" % i


def merge(explicit, directive_at, sources):
    """Section 5.3 rules 4 and 5 for one mapping.

    explicit: [(key text, value)] in source order; directive_at: the index in
    that list where the directive sits; sources: [[(key text, value)]] in
    sequence order. Keys here are plain strings, so key equality is text
    equality.
    """
    taken = {k for k, _ in explicit}
    merged = []
    for source in sources:
        for k, v in source:
            if k not in taken:  # explicit keys win; then the earlier source
                taken.add(k)
                merged.append((k, v))
    return explicit[:directive_at] + merged + explicit[directive_at:]


def flow(pairs):
    return "{" + ", ".join("%s: %s" % (k, v) for k, v in pairs) + "}"


def value_of(text):
    """The Core value of the generator's own plain scalars: digits or k/q words."""
    return INT(int(text)) if text.isdigit() else S(text)


def case(size, form):
    """(alias text, inline text, expected document) for one size and form."""
    p = [(key(i), str(i)) for i in range(size)]
    explicit = [(key(0), "own"), ("z", "last")]
    if form == "seq":
        q = [(key(i), "q%d" % i) for i in range(size // 2, size // 2 + size)]
        sources, names = [p, q], ["p", "q"]
        directive_at = 1
    else:
        sources, names = [p], ["p"]
        directive_at = 0 if form == "first" else 2
    defs_alias = "".join("%s: &%s %s\n" % (n, n, flow(s)) for n, s in zip(names, sources))
    defs_inline = "".join("%s: %s\n" % (n, flow(s)) for n, s in zip(names, sources))
    if form == "seq":
        src_alias = "[" + ", ".join("*" + n for n in names) + "]"
        src_inline = "[" + ", ".join(flow(s) for s in sources) + "]"
    else:
        src_alias, src_inline = "*p", flow(p)

    def body(src):
        items = ["%s: %s" % kv for kv in explicit]
        items.insert(directive_at, "<<: " + src)
        return "m: {" + ", ".join(items) + "}\n"

    top = [(S(n), MAP([(S(k), value_of(v)) for k, v in s])) for n, s in zip(names, sources)]
    merged = merge(explicit, directive_at, sources)
    top.append((S("m"), MAP([(S(k), value_of(v)) for k, v in merged])))
    return defs_alias + body(src_alias), defs_inline + body(src_inline), {"documents": [MAP(top)]}


def generate(parameters):
    if parameters.get("ladder") != "1,10,100,1000":
        raise ValueError("unknown ladder %r" % parameters.get("ladder"))
    for size in SIZES:
        for form in ("first", "last", "seq"):
            alias, inline, expectation = case(size, form)
            yield "s%04d-%s-alias" % (size, form), "merge-policy", alias, expectation, []
            yield "s%04d-%s-inline" % (size, form), "merge-policy", inline, expectation, []
