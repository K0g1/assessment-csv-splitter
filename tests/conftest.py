from __future__ import annotations

import csv
from pathlib import Path

import pytest

ROLES = {
    "Assessment Data": (
        ["PIN", "DeviceID", "Assessment Name", "Value"],
        [
            ["P001", "D1", "Baseline", "first"],
            ["P001", "D1", "Baseline", "second"],
            ["P002", "D2", "Follow-Up", "third"],
        ],
    ),
    "Assessment Scores": (
        ["PIN", "DeviceID", "Assessment Name", "Score"],
        [
            ["P001", "D1", "Baseline", "10"],
            ["P002", "D2", "Follow-Up", "20"],
        ],
    ),
    "Narrow Structure Assessment Data": (
        ["PIN", "RegistrationID", "AssessmentName", "Value"],
        [
            ["P001", "R1", "Baseline", "n-first"],
            ["P002", "R2", "Follow-Up", "n-second"],
        ],
    ),
    "Narrow Structure Assessment Scores": (
        ["PIN", "RegistrationID", "AssessmentName", "Score"],
        [
            ["P001", "R1", "Baseline", "11"],
            ["P002", "R2", "Follow-Up", "21"],
        ],
    ),
    "Registration Data": (
        ["PIN", "DeviceID", "Name", "Assessment Name"],
        [
            ["P001", "D1", "Person 1", "Baseline"],
            ["P001", "D1", "Person 1", "Year 2"],
            ["P002", "D2", "Person 2", "Follow-Up"],
        ],
    ),
    "Narrow Structure Registration Data": (
        ["PIN", "RegistrationID", "DeviceID", "Name", "AssessmentName"],
        [
            ["P001", "R1", "D1", "Person 1", "Baseline"],
            ["P001", "R3", "D1", "Person 1", "Year 2"],
            ["P002", "R2", "D2", "Person 2", "Follow-Up"],
        ],
    ),
}


@pytest.fixture
def six_csv_directory(tmp_path: Path) -> Path:
    source = tmp_path / "combined"
    source.mkdir()
    for role, (header, rows) in ROLES.items():
        path = source / f"2026-08-04 12.34.56 {role}.csv"
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle, lineterminator="\n")
            writer.writerow(header)
            writer.writerows(rows)
    return source
