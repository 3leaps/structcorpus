# Coverage

Release stages are defined in
[PDR-0001](decisions/PDR-0001-staged-releases.md).

| Area | Status |
| --- | --- |
| Repository rules validator (names, sizes, byte-exact attributes, strict JSON) | Implemented |
| Case, profile, span-convention, and upstream-lock schemas (DDR-0003) | Implemented |
| Canonical JSON (JCS subset) serializer | Implemented |
| Example cases: one per expectation layer, all `provisional` | Implemented (8) |
| YAML scalar resolution and duplicate-key truth generator | Planned, 0.1 |
| YAML hand-checked goldens and wire cases | Planned, 0.1 |
| YAML adversarial families and bounded recipes | Planned, 0.2 |
| Minimal bounded hydrate / verify for the truth generator | Planned, 0.1 |
| `list`, recipe ladders, containment runner, stress tier | Planned, 0.2 |
| yaml-test-suite import, Windows/Linux parity matrix | Planned, 0.3 |
| Binding lifetime and streaming input surfaces | Unsupported until a consumer exposes them |
| JSON, XML | Reserved |
