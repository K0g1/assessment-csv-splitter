from __future__ import annotations

import csv
import json
import zipfile
from pathlib import Path

from assessment_csv_splitter.core import split_dataset


def read_csv(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.reader(handle))


def test_directory_input_creates_uniform_audited_tree(
    six_csv_directory: Path, tmp_path: Path
) -> None:
    output = tmp_path / "split"

    result = split_dataset(six_csv_directory, output)

    assert result.status == "PASS"
    assert result.source_file_count == 6
    assert result.patient_count == 2
    assert result.patient_assessment_count == 3
    assert result.output_csv_count == 18
    assert result.header_only_count == 4
    assert not list((output / "P001").glob("*.csv"))

    expected_names = {path.name for path in six_csv_directory.glob("*.csv")}
    for patient, assessment in [
        ("P001", "Baseline"),
        ("P001", "Year 2"),
        ("P002", "Follow-Up"),
    ]:
        folder = output / patient / assessment
        assert {path.name for path in folder.glob("*.csv")} == expected_names

    assessment_data = output / "P001" / "Baseline" / ("2026-08-04 12.34.56 Assessment Data.csv")
    assert read_csv(assessment_data)[1:] == [
        ["P001", "D1", "Baseline", "first"],
        ["P001", "D1", "Baseline", "second"],
    ]

    header_only = output / "P001" / "Year 2" / ("2026-08-04 12.34.56 Assessment Data.csv")
    assert read_csv(header_only) == [["PIN", "DeviceID", "Assessment Name", "Value"]]

    audit_dir = output / ".split-audit"
    expected_audit_files = {
        "AUDIT.json",
        "AUDIT.md",
        "MANIFEST.csv",
        "SOURCE_INVENTORY.json",
        "SUMMARY.json",
    }
    assert {path.name for path in audit_dir.iterdir()} == expected_audit_files
    audit = json.loads((audit_dir / "AUDIT.json").read_text(encoding="utf-8"))
    assert audit["status"] == "PASS"
    assert audit["errors"] == []
    assert audit["data_audit"]["status"] == "PASS"
    assert audit["data_audit"]["row_content_or_order_mismatch_count"] == 0
    assert audit["manifest_audit"]["status"] == "PASS"
    assert audit["manifest_audit"]["output_hash_mismatch_count"] == 0
    assert len(audit["data_tree_sha256"]) == 64
    summary = json.loads((audit_dir / "SUMMARY.json").read_text(encoding="utf-8"))
    assert summary["source_row_count"] == 15
    assert summary["output_csv_count"] == 18
    assert summary["header_only_count"] == 4
    inventory = json.loads((audit_dir / "SOURCE_INVENTORY.json").read_text(encoding="utf-8"))
    assert len(inventory["sources"]) == 6
    assert "Status: PASS" in (audit_dir / "AUDIT.md").read_text(encoding="utf-8")


def test_zip_input_produces_same_partition_bytes(six_csv_directory: Path, tmp_path: Path) -> None:
    source_zip = tmp_path / "combined.zip"
    with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source_file in sorted(six_csv_directory.glob("*.csv")):
            archive.write(source_file, f"nested export/{source_file.name}")

    directory_output = tmp_path / "from-directory"
    zip_output = tmp_path / "from-zip"
    split_dataset(six_csv_directory, directory_output)
    split_dataset(source_zip, zip_output)

    directory_files = {
        path.relative_to(directory_output): path.read_bytes()
        for path in directory_output.rglob("*.csv")
        if ".split-audit" not in path.parts
    }
    zip_files = {
        path.relative_to(zip_output): path.read_bytes()
        for path in zip_output.rglob("*.csv")
        if ".split-audit" not in path.parts
    }
    assert zip_files == directory_files
