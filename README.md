# Assessment CSV Splitter

A standalone command-line tool that losslessly turns six combined assessment exports into a uniform patient and assessment folder tree.

The tool accepts either a ZIP archive or a directory. It validates the six expected source roles, preserves every original CSV basename, partitions rows using `PIN` and `Assessment Name`/`AssessmentName`, creates all six CSVs in every discovered assessment folder, and independently audits the result before publishing it.

No patient data is included in this repository or its releases.

## Download

Download the executable for your operating system from the [latest GitHub release](../../releases/latest):

- `assessment-csv-splitter-windows-x86_64.exe`
- `assessment-csv-splitter-linux-x86_64`
- `assessment-csv-splitter-macos`

Each release also includes `SHA256SUMS.txt`.

## Quick start

The destination must not already exist. This prevents accidental overwrites.

### Windows PowerShell

```powershell
.\assessment-csv-splitter-windows-x86_64.exe `
  "C:\Path\To\combined-exports.zip" `
  "C:\Path\To\split-output"
```

### Linux

```bash
chmod +x assessment-csv-splitter-linux-x86_64
./assessment-csv-splitter-linux-x86_64 \
  "/path/to/combined-exports.zip" \
  "/path/to/split-output"
```

### macOS

```bash
chmod +x assessment-csv-splitter-macos
./assessment-csv-splitter-macos \
  "/path/to/combined-exports.zip" \
  "/path/to/split-output"
```

macOS may require approving an unsigned downloaded executable in **System Settings > Privacy & Security**.

## Dry run

Validate the input and preview aggregate counts without writing files:

```bash
assessment-csv-splitter INPUT_PATH OUTPUT_PATH --dry-run
```

For scripts and automation, request JSON:

```bash
assessment-csv-splitter INPUT_PATH OUTPUT_PATH --dry-run --json
assessment-csv-splitter INPUT_PATH OUTPUT_PATH --json
```

The normal successful exit code is `0`. Input or destination validation failures return `2`. A failed post-write audit returns `3` and the destination is not published.

## Required input

The input path must be either:

- a directory containing exactly six CSV files, searched recursively, or
- a ZIP containing exactly six CSV members, searched recursively without extraction.

Timestamp or export prefixes are allowed. Each basename must end with exactly one required role:

1. `Registration Data.csv`
2. `Narrow Structure Registration Data.csv`
3. `Assessment Data.csv`
4. `Narrow Structure Assessment Data.csv`
5. `Assessment Scores.csv`
6. `Narrow Structure Assessment Scores.csv`

Every source must contain exactly one normalized `PIN` column and exactly one normalized `Assessment Name` or `AssessmentName` column. Header normalization ignores capitalization, spaces, punctuation, and underscores.

Source encodings supported by the parser are UTF-8 with or without a BOM and Windows-1252. Outputs are deterministic UTF-8 CSVs with LF line endings.

## Output structure

For every unique `(PIN, assessment)` pair found anywhere across the six files, the tool creates:

```text
OUTPUT_PATH/
├── PATIENT_ID/
│   └── ASSESSMENT_NAME/
│       ├── original Registration Data.csv
│       ├── original Narrow Structure Registration Data.csv
│       ├── original Assessment Data.csv
│       ├── original Narrow Structure Assessment Data.csv
│       ├── original Assessment Scores.csv
│       └── original Narrow Structure Assessment Scores.csv
└── .split-audit/
    ├── AUDIT.json
    ├── AUDIT.md
    ├── MANIFEST.csv
    ├── SOURCE_INVENTORY.json
    └── SUMMARY.json
```

If one source has no rows for a discovered patient/assessment pair, its corresponding output is intentionally header-only. This keeps every assessment folder structurally uniform.

No CSV is written directly inside a patient folder.

## Safety and correctness guarantees

- Refuses to overwrite an existing destination.
- Builds in a private staging directory and atomically publishes only after all audits pass.
- Rejects blank routing keys, path traversal, unsafe Windows names, path separators, and filesystem-equivalent Unicode/case collisions.
- Rejects symlinked source CSVs and unsafe, encrypted, or symlink ZIP members.
- Enforces a 512 MiB per-source and 2 GiB aggregate uncompressed source limit.
- Preserves source row order within every partition, including intentional duplicate rows.
- Reopens the input independently after generation and compares every output header, row, cell, order, route, and path.
- Verifies every manifest path, source hash, output hash, row count, header width, role, and routing component.
- Records a deterministic data-tree SHA-256 in the audit report.
- Removes the staging directory and leaves the destination absent if validation or auditing fails.

The detailed algorithm and invariants are documented in [`docs/ALGORITHM.md`](docs/ALGORITHM.md).

## Python installation

The release executables do not require Python. Developers can install the package directly:

```bash
python -m pip install .
assessment-csv-splitter --version
```

## Development

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
ruff check src tests scripts
mypy src
pytest
```

Build a local executable:

```bash
pyinstaller --clean --noconfirm --onefile \
  --name assessment-csv-splitter \
  scripts/pyinstaller_entry.py
python scripts/smoke_test_binary.py dist/assessment-csv-splitter
```

## License

MIT. See [`LICENSE`](LICENSE).
