from __future__ import annotations

import hashlib
from pathlib import Path

from .core import ROLE_SUFFIXES, _read_output, _read_sources
from .models import AuditResult, ManifestAuditResult


def verify_dataset(input_path: Path, output_path: Path) -> AuditResult:
    """Independently reopen source and output CSVs and reconcile every partition."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    sources = _read_sources(input_path)
    if len(sources) != 6:
        raise ValueError(f"Expected exactly 6 CSV files, found {len(sources)}")
    if len({source.basename for source in sources}) != 6:
        raise ValueError("CSV basenames must be unique")
    if {source.role for source in sources} != set(ROLE_SUFFIXES):
        raise ValueError("Input must contain exactly one CSV for each required role")

    pairs = sorted({pair for source in sources for pair in source.groups})
    expected: dict[Path, tuple[list[str], list[list[str]], int, int, str, str]] = {}
    for patient, assessment in pairs:
        for source in sources:
            relative = Path(patient) / assessment / source.basename
            expected[relative] = (
                source.header,
                source.groups.get((patient, assessment), []),
                source.pin_index,
                source.assessment_index,
                patient,
                assessment,
            )

    actual_paths = {
        path.relative_to(output_path)
        for path in output_path.rglob("*.csv")
        if ".split-audit" not in path.parts
    }
    expected_paths = set(expected)
    missing_paths = expected_paths - actual_paths
    extra_paths = actual_paths - expected_paths

    header_mismatch_count = 0
    row_mismatch_count = 0
    routing_mismatch_count = 0
    checked_count = 0
    output_row_count = 0
    errors: list[str] = []

    for relative in sorted(expected_paths & actual_paths):
        expected_header, expected_rows, pin_index, assessment_index, patient, assessment = expected[
            relative
        ]
        try:
            actual_header, actual_rows = _read_output(output_path / relative)
        except (OSError, UnicodeError, ValueError):
            errors.append("OUTPUT_READ_ERROR")
            continue
        checked_count += 1
        output_row_count += len(actual_rows)
        if actual_header != expected_header:
            header_mismatch_count += 1
        if actual_rows != expected_rows:
            row_mismatch_count += 1
        if actual_header == expected_header:
            for row in actual_rows:
                if (
                    len(row) <= max(pin_index, assessment_index)
                    or row[pin_index] != patient
                    or row[assessment_index] != assessment
                ):
                    routing_mismatch_count += 1

    if missing_paths:
        errors.append("MISSING_OUTPUT_PATHS")
    if extra_paths:
        errors.append("EXTRA_OUTPUT_PATHS")
    if header_mismatch_count:
        errors.append("HEADER_MISMATCH")
    if row_mismatch_count:
        errors.append("ROW_CONTENT_OR_ORDER_MISMATCH")
    if routing_mismatch_count:
        errors.append("ROUTING_MISMATCH")

    return AuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(sorted(set(errors))),
        source_row_count=sum(len(source.rows) for source in sources),
        output_row_count=output_row_count,
        expected_output_csv_count=len(expected_paths),
        actual_output_csv_count=len(actual_paths),
        checked_output_csv_count=checked_count,
        header_mismatch_count=header_mismatch_count,
        row_content_or_order_mismatch_count=row_mismatch_count,
        routing_mismatch_count=routing_mismatch_count,
        missing_path_count=len(missing_paths),
        extra_path_count=len(extra_paths),
    )


MANIFEST_HEADER = [
    "relative_path",
    "source_basename",
    "role",
    "patient_id",
    "assessment",
    "row_count",
    "header_columns",
    "header_only",
    "source_sha256",
    "output_sha256",
]


def verify_manifest(input_path: Path, output_path: Path) -> ManifestAuditResult:
    """Verify the generated manifest against source metadata and live output bytes."""
    input_path = Path(input_path)
    output_path = Path(output_path)
    sources = _read_sources(input_path)
    sources_by_basename = {source.basename: source for source in sources}
    manifest_path = output_path / ".split-audit" / "MANIFEST.csv"
    manifest_header, manifest_rows = _read_output(manifest_path)

    errors: list[str] = []
    output_hash_mismatch_count = 0
    metadata_mismatch_count = 0
    listed_paths: set[Path] = set()

    if manifest_header != MANIFEST_HEADER:
        errors.append("MANIFEST_HEADER_MISMATCH")

    for row in manifest_rows:
        row_metadata_mismatch = False
        if len(row) != len(MANIFEST_HEADER):
            metadata_mismatch_count += 1
            errors.append("MANIFEST_ROW_WIDTH_MISMATCH")
            continue
        (
            relative_text,
            source_basename,
            role,
            patient,
            assessment,
            row_count_text,
            header_columns_text,
            header_only_text,
            source_sha256,
            output_sha256,
        ) = row
        relative = Path(relative_text)
        if (
            relative.is_absolute()
            or len(relative.parts) != 3
            or any(part in {"", ".", ".."} for part in relative.parts)
        ):
            metadata_mismatch_count += 1
            errors.append("MANIFEST_UNSAFE_PATH")
            continue
        if relative in listed_paths:
            metadata_mismatch_count += 1
            errors.append("MANIFEST_DUPLICATE_PATH")
            continue
        listed_paths.add(relative)

        if relative.parts != (patient, assessment, source_basename):
            row_metadata_mismatch = True
        source = sources_by_basename.get(source_basename)
        if source is None:
            row_metadata_mismatch = True
        else:
            if role != source.role or source_sha256 != source.source_sha256:
                row_metadata_mismatch = True

        output_file = output_path / relative
        if not output_file.is_file():
            continue
        actual_raw = output_file.read_bytes()
        if hashlib.sha256(actual_raw).hexdigest() != output_sha256:
            output_hash_mismatch_count += 1
        try:
            actual_header, actual_rows = _read_output(output_file)
            row_count = int(row_count_text)
            header_columns = int(header_columns_text)
        except (OSError, UnicodeError, ValueError):
            row_metadata_mismatch = True
        else:
            if row_count != len(actual_rows) or header_columns != len(actual_header):
                row_metadata_mismatch = True
            if header_only_text not in {"True", "False"} or (header_only_text == "True") != (
                len(actual_rows) == 0
            ):
                row_metadata_mismatch = True

        if row_metadata_mismatch:
            metadata_mismatch_count += 1

    data_paths = {
        path.relative_to(output_path)
        for path in output_path.rglob("*.csv")
        if ".split-audit" not in path.parts
    }
    path_mismatch_count = len(listed_paths.symmetric_difference(data_paths))
    if path_mismatch_count:
        errors.append("MANIFEST_PATH_SET_MISMATCH")
    if output_hash_mismatch_count:
        errors.append("MANIFEST_OUTPUT_HASH_MISMATCH")
    if metadata_mismatch_count:
        errors.append("MANIFEST_METADATA_MISMATCH")

    return ManifestAuditResult(
        status="PASS" if not errors else "FAIL",
        errors=tuple(sorted(set(errors))),
        manifest_row_count=len(manifest_rows),
        data_csv_count=len(data_paths),
        output_hash_mismatch_count=output_hash_mismatch_count,
        path_mismatch_count=path_mismatch_count,
        metadata_mismatch_count=metadata_mismatch_count,
    )
