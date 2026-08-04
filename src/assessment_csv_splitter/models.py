from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SplitResult:
    status: str
    source_file_count: int
    source_row_count: int
    patient_count: int
    patient_assessment_count: int
    output_csv_count: int
    header_only_count: int


@dataclass(frozen=True, slots=True)
class AuditResult:
    status: str
    errors: tuple[str, ...]
    source_row_count: int
    output_row_count: int
    expected_output_csv_count: int
    actual_output_csv_count: int
    checked_output_csv_count: int
    header_mismatch_count: int
    row_content_or_order_mismatch_count: int
    routing_mismatch_count: int
    missing_path_count: int
    extra_path_count: int


@dataclass(frozen=True, slots=True)
class ManifestAuditResult:
    status: str
    errors: tuple[str, ...]
    manifest_row_count: int
    data_csv_count: int
    output_hash_mismatch_count: int
    path_mismatch_count: int
    metadata_mismatch_count: int
