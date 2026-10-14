# Schema negative controls

Each file here must **fail** validation against the schema named by its
first dot-separated component (`case.*.json` → `schemas/case.v1.schema.json`).
`tools/schema-check.sh` fails if any control passes, or if no controls exist.
