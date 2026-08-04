# Changelog

All notable changes are documented here.

## 1.0.0 - 2026-08-04

- Accept directory and ZIP inputs containing the six expected export roles.
- Partition every source by `PIN` and assessment name.
- Create a uniform six-file set for every patient/assessment pair.
- Preserve headers, cells, duplicate rows, and within-partition row order.
- Add staged output, cross-platform path validation, dry-run mode, and JSON output.
- Add independent data-tree and manifest audits with deterministic hashes.
- Add native Windows, Linux, and macOS standalone release builds.
