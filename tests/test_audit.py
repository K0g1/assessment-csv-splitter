from __future__ import annotations

import csv
from pathlib import Path

import pytest

from assessment_csv_splitter.audit import verify_dataset, verify_manifest
from assessment_csv_splitter.core import split_dataset
from assessment_csv_splitter.models import AuditResult, ManifestAuditResult


def read_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.reader(handle))


def write_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)


def test_independent_verifier_detects_single_cell_tampering(
    six_csv_directory: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "split"
    split_dataset(six_csv_directory, output)
    target = output / "P001" / "Baseline" / ("2026-08-04 12.34.56 Assessment Data.csv")
    rows = read_rows(target)
    rows[1][-1] = "tampered"
    write_rows(target, rows)

    audit = verify_dataset(six_csv_directory, output)

    assert audit.status == "FAIL"
    assert audit.checked_output_csv_count == 18
    assert audit.header_mismatch_count == 0
    assert audit.row_content_or_order_mismatch_count == 1
    assert audit.missing_path_count == 0
    assert audit.extra_path_count == 0


def test_splitter_does_not_publish_when_independent_audit_fails(
    six_csv_directory: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_audit = AuditResult(
        status="FAIL",
        errors=("SIMULATED_FAILURE",),
        source_row_count=15,
        output_row_count=15,
        expected_output_csv_count=18,
        actual_output_csv_count=18,
        checked_output_csv_count=18,
        header_mismatch_count=0,
        row_content_or_order_mismatch_count=1,
        routing_mismatch_count=0,
        missing_path_count=0,
        extra_path_count=0,
    )
    monkeypatch.setattr(
        "assessment_csv_splitter.audit.verify_dataset",
        lambda _input, _output: failed_audit,
    )
    output = tmp_path / "split"

    with pytest.raises(RuntimeError, match="Independent output audit failed"):
        split_dataset(six_csv_directory, output)

    assert not output.exists()
    assert not list(tmp_path.glob(".split.staging-*"))


def test_manifest_verifier_detects_tampered_output_hash(
    six_csv_directory: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "split"
    split_dataset(six_csv_directory, output)
    manifest = output / ".split-audit" / "MANIFEST.csv"
    rows = read_rows(manifest)
    rows[1][9] = "0" * 64
    write_rows(manifest, rows)

    audit = verify_manifest(six_csv_directory, output)

    assert audit.status == "FAIL"
    assert audit.output_hash_mismatch_count == 1
    assert audit.path_mismatch_count == 0
    assert audit.metadata_mismatch_count == 0


def test_splitter_does_not_publish_when_manifest_audit_fails(
    six_csv_directory: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    failed_manifest_audit = ManifestAuditResult(
        status="FAIL",
        errors=("SIMULATED_MANIFEST_FAILURE",),
        manifest_row_count=18,
        data_csv_count=18,
        output_hash_mismatch_count=1,
        path_mismatch_count=0,
        metadata_mismatch_count=0,
    )
    monkeypatch.setattr(
        "assessment_csv_splitter.audit.verify_manifest",
        lambda _input, _output: failed_manifest_audit,
    )
    output = tmp_path / "split"

    with pytest.raises(RuntimeError, match="Manifest audit failed"):
        split_dataset(six_csv_directory, output)

    assert not output.exists()
    assert not list(tmp_path.glob(".split.staging-*"))
