from __future__ import annotations

import argparse
import csv
import json
import os
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path

ROLE_HEADERS = {
    "Registration Data.csv": ["PIN", "DeviceID", "Assessment Name"],
    "Narrow Structure Registration Data.csv": ["PIN", "RegistrationID", "AssessmentName"],
    "Assessment Data.csv": ["PIN", "DeviceID", "Assessment Name"],
    "Narrow Structure Assessment Data.csv": ["PIN", "RegistrationID", "AssessmentName"],
    "Assessment Scores.csv": ["PIN", "DeviceID", "Assessment Name"],
    "Narrow Structure Assessment Scores.csv": ["PIN", "RegistrationID", "AssessmentName"],
}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    arguments = parser.parse_args()
    executable = arguments.executable.resolve()
    if os.name != "nt":
        executable.chmod(executable.stat().st_mode | stat.S_IXUSR)

    with tempfile.TemporaryDirectory(prefix="assessment-csv-splitter-smoke-") as temporary:
        root = Path(temporary)
        source = root / "source"
        source.mkdir()
        for role, header in ROLE_HEADERS.items():
            path = source / f"2026-08-04 12.34.56 {role}"
            with path.open("w", encoding="utf-8", newline="") as stream:
                writer = csv.writer(stream, lineterminator="\n")
                writer.writerow(header)
                writer.writerow(["TEST001", "DEVICE001", "Baseline"])
        source_zip = root / "source.zip"
        with zipfile.ZipFile(source_zip, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(source.glob("*.csv")):
                archive.write(path, arcname=f"combined/{path.name}")
        output = root / "output"
        completed = subprocess.run(
            [str(executable), str(source_zip), str(output), "--json"],
            check=False,
            capture_output=True,
            text=True,
            timeout=120,
        )
        if completed.returncode != 0:
            raise RuntimeError(
                f"Binary returned {completed.returncode}: {completed.stderr.strip()}"
            )
        summary = json.loads(completed.stdout)
        if summary["status"] != "PASS" or summary["output_csv_count"] != 6:
            raise RuntimeError(f"Unexpected binary summary: {summary}")
        partition = output / "TEST001" / "Baseline"
        if len(list(partition.glob("*.csv"))) != 6:
            raise RuntimeError("Binary did not produce six partition CSVs")
        audit = json.loads((output / ".split-audit" / "AUDIT.json").read_text())
        if audit["data_audit"]["status"] != "PASS":
            raise RuntimeError("Embedded data audit did not pass")
        if audit["manifest_audit"]["status"] != "PASS":
            raise RuntimeError("Embedded manifest audit did not pass")
        print(json.dumps({"status": "PASS", "executable": executable.name}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
