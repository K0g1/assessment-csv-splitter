from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict
from pathlib import Path

from . import __version__
from .core import inspect_dataset, split_dataset


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="assessment-csv-splitter",
        description=(
            "Losslessly split six combined assessment CSV exports into "
            "patient/assessment folder trees and audit every output."
        ),
    )
    parser.add_argument("input_path", type=Path, help="Directory or ZIP containing six CSVs")
    parser.add_argument("output_path", type=Path, help="New destination directory")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and report the planned split without writing files",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print the aggregate result as JSON",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    arguments = parser.parse_args(argv)
    try:
        if arguments.dry_run:
            result = inspect_dataset(arguments.input_path, arguments.output_path)
        else:
            result = split_dataset(arguments.input_path, arguments.output_path)
    except (FileExistsError, OSError, UnicodeError, ValueError) as error:
        if arguments.json_output:
            print(json.dumps({"status": "ERROR", "error": str(error)}), file=sys.stderr)
        else:
            print(f"error: {error}", file=sys.stderr)
        return 2
    except RuntimeError as error:
        if arguments.json_output:
            print(json.dumps({"status": "AUDIT_FAILED", "error": str(error)}), file=sys.stderr)
        else:
            print(f"audit failed: {error}", file=sys.stderr)
        return 3

    payload = asdict(result)
    payload["output_directory"] = str(arguments.output_path)
    payload["audit_directory"] = str(arguments.output_path / ".split-audit")
    if arguments.json_output:
        print(json.dumps(payload, sort_keys=True))
    else:
        if arguments.dry_run:
            print("Validation passed. No files were written.")
        else:
            print("Split complete and independently verified.")
        print(f"Source CSV files: {result.source_file_count}")
        print(f"Source data rows: {result.source_row_count}")
        print(f"Patient folders: {result.patient_count}")
        print(f"Patient/assessment folders: {result.patient_assessment_count}")
        print(f"Output CSV files: {result.output_csv_count}")
        print(f"Intentional header-only CSV files: {result.header_only_count}")
        print(f"Output: {arguments.output_path}")
        print(f"Audit: {arguments.output_path / '.split-audit'}")
    return 0
