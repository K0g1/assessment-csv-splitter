# Assessment CSV Splitter 1.0.0

First production release.

## What it does

- Accepts a directory or ZIP containing the six expected combined CSV exports.
- Splits rows into `PIN / assessment / original CSV basename` folders.
- Creates all six CSVs for every discovered patient/assessment pair.
- Uses intentional header-only files when a source has no rows for a pair.
- Preserves headers, cells, duplicate multiplicity, and within-partition row order.
- Refuses unsafe paths and existing destinations.
- Stages and independently audits the complete result before publishing it.
- Produces JSON, Markdown, manifest, inventory, and summary audit artifacts.

## Release assets

- `assessment-csv-splitter-windows-x86_64.exe`
- `assessment-csv-splitter-linux-x86_64`
- `assessment-csv-splitter-macos`
- `SHA256SUMS.txt`

The executables are built natively and run an end-to-end ZIP smoke test on their corresponding GitHub-hosted operating system before upload.

## Verification evidence

- 28 automated tests pass on Linux.
- Native Windows tests pass, with two expected skips for filesystem operations that Windows itself prohibits without special privileges.
- Ruff, strict mypy, Bandit, and runtime dependency audit pass.
- Clean wheel installation and installed-console smoke test pass.
- Linux and Windows standalone executables pass native smoke testing.
- Full retained-dataset regression: 6 source CSVs, 112,215 rows, 39 patient folders, 47 patient/assessment folders, 282 output CSVs, 18 intentional header-only files, zero patient-root CSVs, and zero byte mismatches against the previously audited reference tree.

No real dataset or patient identifier is included in this repository or release.
