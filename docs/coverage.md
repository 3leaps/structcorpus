# Coverage

Release stages are defined in
[PDR-0001](decisions/PDR-0001-staged-releases.md).

| Area | Status |
| --- | --- |
| Repository rules validator (names, sizes, byte-exact attributes, strict JSON) | Implemented |
| Case, profile, span-convention, and upstream-lock schemas (DDR-0003) | Implemented |
| Canonical JSON (JCS subset) serializer | Implemented |
| Example cases: one per expectation layer, all `provisional` | Implemented (8) |
| Scalar resolution, duplicate-key, and numeric truth generator (59,484 generated cases, `yamlprims-core` r1, provisional) | Implemented |
| Typed-conversion expectations (DDR-0005): integer widths, `f32`, `f64`, `bool`, `string`, `option-bool` | Implemented (numbers and booleans r2) |
| Hand-checked boundary goldens, including merge `apply` and `as-key` profiles (125 cases) | Implemented, provisional |
| yamlprims specification 1.1 profiles (`yamlprims-core` r2, stream, merge variants) and span convention `scalar-alias` r2 (DDR-0006) | Implemented |
| Specification 1.1 cases: document cardinality, strict flow indentation, block-scalar span ends (12 cases) | Implemented, provisional |
| Numeric truth and goldens bound to r2 profiles (smoke tier) | Implemented |
| Boolean and collision truth tables bound to r2 profiles | Planned: when the r1 profiles retire (conformance tier budget) |
| Empty-node and collection span conventions | Planned |
| Wire-format goldens for a specific implementation's encoder | Not planned: an implementation's encoded output is its own conformance surface, not engine-neutral corpus material |
| YAML adversarial families and bounded recipes | Planned, 0.2 |
| Bounded hydrate / verify for generated recipes (DDR-0004) | Implemented |
| Containment runner with self-tests (SecDR-0002): bounded execution of a caller-supplied command | Implemented |
| Running hostile YAML cases through a parser driver | Planned, 0.2 (needs the hazardous recipes and a consumer driver) |
| `list`, recipe ladders, stress tier | Planned, 0.2 |
| yaml-test-suite import, Windows/Linux parity matrix | Planned, 0.3 |
| Binding lifetime and streaming input surfaces | Unsupported until a consumer exposes them |
| JSON, XML | Reserved |
