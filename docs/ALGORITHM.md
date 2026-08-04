# Algorithm and invariants

## Source discovery

The input is a directory or ZIP. CSVs are discovered recursively and non-CSV files are ignored. Exactly six CSVs must remain. Basenames may have arbitrary prefixes, but each must map uniquely to one of the six required suffix roles.

ZIP members are read directly without extraction. Absolute paths, parent traversal, backslash paths, encryption, and symlink members are rejected.

## Parsing

Each source is decoded as UTF-8 with BOM handling, UTF-8, or Windows-1252. Standard CSV quoting is honored, including embedded delimiters and newlines. Every row must have the same width as its source header.

Headers are normalized by case-folding and retaining only alphanumeric characters. Each source must have exactly one normalized `pin` header and exactly one normalized `assessmentname` header.

Routing values are preserved exactly. Blank values and values unsafe as portable filesystem components are rejected rather than modified.

## Partition plan

For source `s`, rows are grouped in encounter order:

```text
groups[s][(PIN, assessment)] = ordered rows from s with that pair
```

The global pair set is the union across all six sources:

```text
pairs = union(groups[s].keys() for every source s)
```

For every pair and every source, one output path is planned:

```text
PIN / assessment / original_source_basename
```

If a source has no rows for the pair, the output contains only that source's header.

Therefore:

```text
output CSV count = unique patient/assessment pairs × 6
```

## Staged write

The destination must not exist. A private temporary directory is created beside it, ensuring the final rename stays on one filesystem. All data CSVs and audit artifacts are written into staging.

CSV output is deterministic UTF-8 with LF line endings. Source basenames and all cell values are preserved.

## Independent data audit

The verifier reopens and reparses the input instead of trusting writer state. It reconstructs the complete expected path map and checks:

- missing and extra paths,
- exact header equality,
- exact ordered row-list equality,
- output row totals,
- patient and assessment routing values encoded by each path,
- the required three-component data path shape.

Exact ordered row-list equality also verifies duplicate-row multiplicity.

## Manifest audit

The manifest verifier reopens the input, output CSVs, and generated manifest. It checks:

- manifest schema,
- path set and uniqueness,
- source basename and role,
- patient and assessment path metadata,
- source SHA-256,
- output SHA-256,
- row count,
- header width,
- header-only status.

A deterministic tree hash frames each relative path and file digest, preventing ambiguous concatenation.

## Commit or rollback

The staging directory is atomically renamed to the requested destination only when the writer check, independent data audit, and manifest audit all pass. Any exception removes staging and leaves the destination absent.
