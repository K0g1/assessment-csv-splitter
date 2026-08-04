from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    environment = os.environ.copy()
    source_root = Path(__file__).parents[1] / "src"
    environment["PYTHONPATH"] = str(source_root)
    return subprocess.run(
        [sys.executable, "-m", "assessment_csv_splitter", *arguments],
        cwd=cwd,
        env=environment,
        text=True,
        capture_output=True,
        check=False,
    )


def test_cli_splits_dataset_and_emits_json_summary(
    six_csv_directory: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "split"

    completed = run_cli(str(six_csv_directory), str(output), "--json", cwd=tmp_path)

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    summary = json.loads(completed.stdout)
    assert summary["status"] == "PASS"
    assert summary["source_file_count"] == 6
    assert summary["output_csv_count"] == 18
    assert summary["audit_directory"] == str(output / ".split-audit")
    assert output.is_dir()


def test_cli_dry_run_validates_without_writing(
    six_csv_directory: Path,
    tmp_path: Path,
) -> None:
    output = tmp_path / "split"

    completed = run_cli(
        str(six_csv_directory),
        str(output),
        "--dry-run",
        "--json",
        cwd=tmp_path,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    assert summary["status"] == "READY"
    assert summary["source_row_count"] == 15
    assert summary["patient_assessment_count"] == 3
    assert summary["output_csv_count"] == 18
    assert summary["header_only_count"] == 4
    assert not output.exists()
