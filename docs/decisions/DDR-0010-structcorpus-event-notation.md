---
Record: DDR-0010
Title: An opt-in control-escaped event notation, structcorpus-events/1
Status: Proposed
Date: 2026-10-16
Owner: devlead (drafting); acceptance by the maintainer
---

# DDR-0010: An opt-in control-escaped event notation, `structcorpus-events/1`

## Context

The `events` layer uses the yaml-test-suite notation (DDR-0002, DDR-0003).
Its reference producer is the yaml-test-suite runner in libyaml, pinned at tag
0.2.5 (`tests/run-parser-test-suite.c`). That runner:

- prints anchors, aliases, and tags as raw text (`&%s`, `*%s`, `<%s>`);
- escapes scalar values only, and only `\`, NUL, BS, LF, CR, and TAB, as `\\`,
  `\0`, `\b`, `\n`, `\r`, and `\t`;
- prints every other character of a scalar value as itself, including BEL, VT,
  FF, ESC, DEL, the C1 controls (U+0085 among them), and U+2028 and U+2029.

So a valid event string can contain raw control characters. They are hard to
review, editors and terminals can mangle them, and printing a mismatch can
send raw escape sequences to a terminal. The format is also line-based, but
the runner writes VT, FF, NEL, U+2028, and U+2029 raw, and common line splitters
(Python's `str.splitlines`, for one) treat each of those as a line break. The
corpus is unaffected, because it stores each event as a JSON string, but a
consumer reading runner output line by line can split one event into several.
These behaviors were confirmed by running the pinned runner, built from the
0.2.5 release tarball (sha256
`fa240dbf262be053f3898006d502d514936c818e422afdcf33921c63bed9bf2e`). A validator can reject only the five
raw characters the notation escapes; it cannot tell a deliberate raw BEL from
a mistake.

A scalar event's value is a sequence of Unicode scalar values. Invalid UTF-8
and lone surrogates never reach a scalar event; they belong to input fixtures
and `input` errors (DDR-0001, DDR-0002). This record is about how a valid
value is displayed in event text, not about representing invalid input.

## Decision

1. **A second, opt-in notation.** The `events.notation` member may be
   `"yaml-test-suite"` or `"structcorpus-events/1"`. Each record carries
   exactly one authoritative notation. Comparison representations are derived
   from it, never stored alongside it.

2. **Shared event grammar.** Both notations use the same event grammar. One
   event is one string of the form `<kind>[ <field>]*`, with fields in this
   order:

   | Kind | Fields, in order |
   | --- | --- |
   | `+STR`, `-STR`, `-MAP`, `-SEQ` | none |
   | `+DOC` | optional ` ---` (explicit start) |
   | `-DOC` | optional ` ...` (explicit end) |
   | `+MAP`, `+SEQ` | optional ` {}` for a mapping or ` []` for a sequence (flow style), optional ` &<anchor>`, optional ` <` + tag text + `>` |
   | `=VAL` | optional ` &<anchor>`, optional ` <` + tag text + `>`, then ` ` and a one-character style marker (`:` plain, `'` single-quoted, `"` double-quoted, `\|` literal, `>` folded), then the value |
   | `=ALI` | ` *<alias>` |

   An event is parsed into these fields before any escape is decoded. The
   value runs from just after the style marker to the end of the event, so it
   can contain any character in the value's domain, spaces included. A legacy
   string can contain Unicode line separators; splitting it with Unicode-aware
   line splitting is not part of this grammar. The reference renderer rejects
   unknown kinds, extra or missing fields, incorrect field types and unknown
   styles rather than dropping fields or emitting malformed events. This is
   individual-event syntax validation, not validation of stream nesting or
   anchor lifecycle.

3. **Field domains.**
   - **Anchor and alias names:** YAML 1.2.2 `ns-anchor-char` sequences, which
      exclude YAML whitespace, flow indicators, C0 controls, DEL, C1 controls
      other than NEL, surrogates, BOM, U+FFFE and U+FFFF. They are written
      raw in both notations, including literal backslashes. A name containing
      NEL, U+2028 or U+2029, which YAML 1.2.2 permits, cannot be written in
      `structcorpus-events/1`; such an input uses the yaml-test-suite notation.
   - **Tags:** the resolved tag as text between `<` and `>`, raw in both
     notations. Resolution decodes percent escapes, so a resolved tag can
     contain characters its source spelling did not: `!<!a%20b>` resolves to
     `!a b`, which the pinned runner prints as `<!a b>`. A resolved tag
      containing `>` is outside the converter's unambiguous domain. C0/C1
      controls, DEL, U+2028/U+2029 and surrogates are also excluded from its tag
      domain in both notations. Ordinary spaces are unambiguous inside the angle
      brackets and are allowed, as are literal backslashes. The codec adds and
      removes no percent-encoding. These are codec domain restrictions, not a
      claim that the legacy runner never emits other resolved tags.
   - **Values:** any sequence of Unicode scalar values, encoded per the
     notation (item 4).

   An event that is outside these domains cannot be encoded in the
   notation. The codec rejects it with an error; it never produces an
   ambiguous string. A preserved legacy record outside the codec's domain can
   still be valid legacy metadata; conversion of it is unsupported. No codec
   can recover information already lost or ambiguously framed by a producer.

4. **Value escaping in `structcorpus-events/1`.** Every value has exactly one
   spelling:

   | Character | Written as |
   | --- | --- |
   | `\` | `\\` |
   | U+0000, U+0008, U+0009, U+000A, U+000D | `\0`, `\b`, `\t`, `\n`, `\r` |
   | Other C0 controls (U+0001–U+001F), DEL (U+007F), and C1 controls (U+0080–U+009F) | `\x` and exactly two uppercase hex digits of the code point, so U+0085 is `\x85` |
   | U+2028, U+2029 | `\u2028`, `\u2029` |
   | Any other Unicode scalar value | itself, in UTF-8 |

   The short escapes take precedence over `\xHH`. On reading, the codec
   rejects any other spelling: lowercase hex, `\x` for a character with a
   short escape, `\x` above U+009F or for a printable character, `\u` for
   anything but those two, unknown or truncated escapes, a raw character that
   must be escaped, and surrogate code points. The notation has no line
   folding, no continuation, and no Unicode normalization. Escaping the outer
   JSON string is a separate layer.

5. **The yaml-test-suite notation is unchanged.** Its values escape only `\`,
   NUL, BS, TAB, LF, and CR. Its anchors, aliases, and tags are raw. Reading
   it is field-aware too: decoding a value never touches the other fields.

6. **Conversion.** The reference codec (`tools/events.py`) parses an event
   string into fields under its source notation, then encodes those fields in
   the target notation. A conversion that would leave the target's domain
   (item 3) fails. Conversion never changes event count, order, style, anchors,
   tags, or aliases, so `event_index` locations and node selectors keep their
   meaning.

7. **Selection and preservation.**
   - **Existing records, recipes, and digests are unchanged.** No record is
     migrated. Migrating one later means a new revision of that record or
     recipe.
   - **New committed records** use `structcorpus-events/1` when any value
     contains a character the yaml-test-suite notation would leave raw (a C0
     control other than NUL, BS, TAB, LF, and CR, or DEL, a C1 control, U+2028,
     or U+2029), provided every field is in the notation's domain. Otherwise
     they use the yaml-test-suite notation.
   - **Records imported from the yaml-test-suite** keep its notation verbatim,
     even when they contain such characters. That is a stated exception, not a
     claim that imports never contain them.

8. **Validation.** For `structcorpus-events/1`, `validate` parses every event
   and rejects:
   - a raw C0 control, DEL, C1 control, U+2028, or U+2029 anywhere;
   - any noncanonical or unknown escape;
   - a field outside its domain.

   For the yaml-test-suite notation, the existing check stays (no raw NUL, BS,
   TAB, LF, or CR). Repository validation does not impose the reference codec's
   narrower field grammar on historical legacy records or imports. Explicit
   conversion still parses and validates its source within the declared domain.

9. **Consumer contract.** A consumer driver declares which notations it
   reads. An events expectation in a notation it does not read is reported as
   `unsupported`, a result distinct from pass, mismatch, and skipped. It never
   counts toward qualification coverage. Drivers compare supported events as
   parsed fields; an event outside their supported conversion domain is likewise
   reported as unsupported, not as a YAML syntax failure. Drivers print mismatches through an escaped display that
   never writes raw controls to a terminal, in either notation. A consumer pins
   the corpus commit, which pins this notation's definition along with the
   profiles, and records its reader/schema revision and notation capabilities
   with qualification results. Unsupported expectations remain visible in the
   requested inventory; a run cannot claim complete coverage while any remain.

10. **Schema version.** Adding an enum value to `events.notation` does not
    change `case/v1`. A reader that does not know `structcorpus-events/1`
    either fails schema validation or reports the expectation as unsupported
    (item 9); it never treats it as yaml-test-suite text.

## Consequences

- A new case whose values contain raw controls can be reviewed and validated
  strictly.
- The notation is control-escaped, not display-safe: bidirectional formatting,
  zero-width characters, and other invisible text still appear as themselves.
  Diagnostics must escape output for both notations.
- Inputs whose fields fit the legacy codec domain but not the new domain stay
  in the yaml-test-suite notation. If neither domain can encode a new event,
  automatic selection fails; it does not invent a fallback representation.
  Preserved legacy imports remain an explicit exception as described above.
- Until a consumer driver supports the notation, records using it are reported
  as unsupported, not as passing coverage. No committed case uses it yet.
- The codec is tested against exact vectors written by hand, not only round
  trips. Some of them are the pinned runner's own output, captured and written
  out as literals. Those vectors cover:
  - the pinned yaml-test-suite escapes;
  - every escape boundary;
  - NEL and U+2028/U+2029;
  - literal backslashes beside text that looks like an escape;
  - multibyte and supplementary characters;
  - anchors, aliases, tags, and their delimiters;
  - malformed escapes and noncanonical spellings.
