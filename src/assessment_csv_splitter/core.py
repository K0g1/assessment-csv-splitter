from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import shutil
import stat
import tempfile
import unicodedata
import zipfile
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath

from .models import SplitResult

ROLE_SUFFIXES = (
    "Narrow Structure Registration Data.csv",
    "Narrow Structure Assessment Scores.csv",
    "Narrow Structure Assessment Data.csv",
    "Registration Data.csv",
    "Assessment Scores.csv",
    "Assessment Data.csv",
)

WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{number}" for number in range(1, 10)),
    *(f"LPT{number}" for number in range(1, 10)),
}
WINDOWS_INVALID_CHARACTERS = frozenset('<>:"/\\|?*')
MAX_SOURCE_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_SOURCE_BYTES = 2 * 1024 * 1024 * 1024


@dataclass(slots=True)
class SourceCsv:
    member: str
    basename: str
    role: str
    raw: bytes
    header: list[str]
    rows: list[list[str]]
    pin_index: int
    assessment_index: int
    source_sha256: str
    groups: dict[tuple[str, str], list[list[str]]]


def _normal_header(value: str) -> str:
    return "".join(character for character in value.casefold() if character.isalnum())


def _routing_index(normalized_header: list[str], target: str, label: str, member: str) -> int:
    matches = [index for index, value in enumerate(normalized_header) if value == target]
    if len(matches) != 1:
        raise ValueError(
            f"{member} must contain exactly one {label} column after header normalization; "
            f"found {len(matches)}"
        )
    return matches[0]


def _validate_path_component(
    value: str,
    label: str,
    member: str,
    row_number: int | None,
) -> None:
    reason: str | None = None
    if value in {".", ".."}:
        reason = "dot path component"
    elif any(character in WINDOWS_INVALID_CHARACTERS for character in value):
        reason = "path separator or invalid Windows filename character"
    elif any(ord(character) < 32 for character in value):
        reason = "control character"
    elif value.endswith((".", " ")):
        reason = "trailing dot or space"
    elif value.split(".", maxsplit=1)[0].upper() in WINDOWS_RESERVED_NAMES:
        reason = "reserved Windows device name"
    elif len(value.encode("utf-8")) > 255:
        reason = "component exceeds 255 encoded bytes"
    if reason is not None:
        location = f" in {member}"
        if row_number is not None:
            location += f" at CSV row {row_number}"
        raise ValueError(f"Unsafe {label}{location}: {reason}")


def _filesystem_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold()


def _validate_routing_collisions(pairs: list[tuple[str, str]]) -> None:
    patients_by_key: dict[str, str] = {}
    assessments_by_patient: dict[str, dict[str, str]] = defaultdict(dict)
    for patient, assessment in pairs:
        patient_key = _filesystem_key(patient)
        previous_patient = patients_by_key.setdefault(patient_key, patient)
        if previous_patient != patient:
            raise ValueError("PIN path collision after Unicode normalization and case folding")
        assessment_key = _filesystem_key(assessment)
        previous_assessment = assessments_by_patient[patient].setdefault(assessment_key, assessment)
        if previous_assessment != assessment:
            raise ValueError(
                "Assessment path collision after Unicode normalization and case folding"
            )


def _role_for_name(name: str) -> str:
    matches = [suffix for suffix in ROLE_SUFFIXES if name.casefold().endswith(suffix.casefold())]
    if not matches:
        raise ValueError(f"Unrecognized CSV role: {name}")
    return max(matches, key=len)


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("CSV encoding is not UTF-8 or CP1252")


def _parse_source(raw: bytes, basename: str, member: str) -> SourceCsv:
    _validate_path_component(basename, "source basename", member, None)
    field_limit = MAX_SOURCE_FILE_BYTES
    while True:
        try:
            csv.field_size_limit(field_limit)
            break
        except OverflowError:
            field_limit //= 10
    try:
        parsed = list(csv.reader(io.StringIO(_decode(raw)), strict=True))
    except csv.Error as error:
        raise ValueError(f"Malformed CSV syntax in {member}: {error}") from error
    if not parsed:
        raise ValueError(f"CSV is empty: {member}")
    header, rows = parsed[0], parsed[1:]
    widths = {len(row) for row in rows}
    if widths and widths != {len(header)}:
        raise ValueError(f"Inconsistent row widths: {member}")
    normalized = [_normal_header(value) for value in header]
    pin_index = _routing_index(normalized, "pin", "PIN", member)
    assessment_index = _routing_index(normalized, "assessmentname", "assessment-name", member)
    groups: dict[tuple[str, str], list[list[str]]] = defaultdict(list)
    for row_number, row in enumerate(rows, start=2):
        if not row[pin_index].strip():
            raise ValueError(f"Blank PIN in {member} at CSV row {row_number}")
        if not row[assessment_index].strip():
            raise ValueError(f"Blank assessment name in {member} at CSV row {row_number}")
        _validate_path_component(row[pin_index], "PIN", member, row_number)
        _validate_path_component(row[assessment_index], "assessment name", member, row_number)
        groups[(row[pin_index], row[assessment_index])].append(row)
    return SourceCsv(
        member=member,
        basename=basename,
        role=_role_for_name(basename),
        raw=raw,
        header=header,
        rows=rows,
        pin_index=pin_index,
        assessment_index=assessment_index,
        source_sha256=hashlib.sha256(raw).hexdigest(),
        groups=dict(groups),
    )


def _read_sources(input_path: Path) -> list[SourceCsv]:
    if input_path.is_dir():
        sources: list[SourceCsv] = []
        candidates = sorted(
            path for path in input_path.rglob("*") if path.suffix.casefold() == ".csv"
        )
        for path in candidates:
            if path.is_symlink():
                raise ValueError("Source CSV cannot be a symbolic link")
            if not path.is_file():
                continue
            size = path.stat().st_size
            if size > MAX_SOURCE_FILE_BYTES:
                raise ValueError("A source CSV exceeds the per-file source size limit")
            if sum(len(source.raw) for source in sources) + size > MAX_TOTAL_SOURCE_BYTES:
                raise ValueError("CSV files exceed the total source size limit")
            sources.append(
                _parse_source(
                    path.read_bytes(),
                    path.name,
                    path.relative_to(input_path).as_posix(),
                )
            )
        return sources
    if input_path.is_file() and zipfile.is_zipfile(input_path):
        with zipfile.ZipFile(input_path) as archive:
            infos = sorted(
                (
                    info
                    for info in archive.infolist()
                    if not info.is_dir()
                    and PurePosixPath(info.filename).suffix.casefold() == ".csv"
                ),
                key=lambda info: info.filename,
            )
            total_size = 0
            for info in infos:
                member_path = PurePosixPath(info.filename)
                if member_path.is_absolute() or ".." in member_path.parts or "\\" in info.filename:
                    raise ValueError("Source CSV has an unsafe ZIP member path")
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError("Source CSV in ZIP cannot be a symbolic link")
                if info.flag_bits & 0x1:
                    raise ValueError("Encrypted source CSVs in ZIP are not supported")
                if info.file_size > MAX_SOURCE_FILE_BYTES:
                    raise ValueError("A source CSV exceeds the per-file source size limit")
                total_size += info.file_size
                if total_size > MAX_TOTAL_SOURCE_BYTES:
                    raise ValueError("CSV files exceed the total source size limit")
            return [
                _parse_source(
                    archive.read(info),
                    PurePosixPath(info.filename).name,
                    info.filename,
                )
                for info in infos
            ]
    raise ValueError("Input must be a directory or ZIP archive")


def _write_csv(path: Path, header: list[str], rows: list[list[str]]) -> bytes:
    path.parent.mkdir(parents=True, exist_ok=True)
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    raw = buffer.getvalue().encode("utf-8")
    path.write_bytes(raw)
    return raw


def _data_tree_sha256(root: Path, relative_paths: set[Path]) -> str:
    digest = hashlib.sha256()
    for relative in sorted(relative_paths, key=lambda value: value.as_posix()):
        encoded_path = relative.as_posix().encode("utf-8")
        file_digest = hashlib.sha256((root / relative).read_bytes()).digest()
        digest.update(len(encoded_path).to_bytes(8, "big"))
        digest.update(encoded_path)
        digest.update(file_digest)
    return digest.hexdigest()


def _read_output(path: Path) -> tuple[list[str], list[list[str]]]:
    rows = list(csv.reader(io.StringIO(path.read_text(encoding="utf-8-sig"))))
    if not rows:
        raise ValueError(f"Output CSV is empty: {path}")
    return rows[0], rows[1:]


def _validated_sources(input_path: Path) -> list[SourceCsv]:
    sources = _read_sources(input_path)
    if len(sources) != 6:
        raise ValueError(f"Expected exactly 6 CSV files, found {len(sources)}")
    if len({source.basename for source in sources}) != 6:
        raise ValueError("CSV basenames must be unique")
    if len({_filesystem_key(source.basename) for source in sources}) != 6:
        raise ValueError("CSV basenames collide after Unicode normalization and case folding")
    role_counts = Counter(source.role for source in sources)
    if role_counts != Counter({role: 1 for role in ROLE_SUFFIXES}):
        raise ValueError("Input must contain exactly one CSV for each required role")
    return sources


def _validate_output_scope(input_path: Path, output_path: Path) -> None:
    if input_path.is_dir():
        resolved_input = input_path.resolve()
        resolved_output = output_path.resolve()
        if resolved_output == resolved_input or resolved_input in resolved_output.parents:
            raise ValueError("Output path cannot be inside the input directory")
    if output_path.exists():
        raise FileExistsError(f"Output already exists: {output_path}")


def _result_for_sources(sources: list[SourceCsv], status: str) -> SplitResult:
    pairs = sorted({pair for source in sources for pair in source.groups})
    _validate_routing_collisions(pairs)
    return SplitResult(
        status=status,
        source_file_count=len(sources),
        source_row_count=sum(len(source.rows) for source in sources),
        patient_count=len({patient for patient, _ in pairs}),
        patient_assessment_count=len(pairs),
        output_csv_count=len(pairs) * len(sources),
        header_only_count=sum(
            1 for pair in pairs for source in sources if pair not in source.groups
        ),
    )


def inspect_dataset(input_path: Path, output_path: Path) -> SplitResult:
    input_path = Path(input_path)
    output_path = Path(output_path)
    _validate_output_scope(input_path, output_path)
    return _result_for_sources(_validated_sources(input_path), "READY")


def split_dataset(input_path: Path, output_path: Path) -> SplitResult:
    input_path = Path(input_path)
    output_path = Path(output_path)
    _validate_output_scope(input_path, output_path)
    sources = _validated_sources(input_path)
    plan = _result_for_sources(sources, "PASS")
    pairs = sorted({pair for source in sources for pair in source.groups})
    patients = {patient for patient, _ in pairs}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{output_path.name}.staging-", dir=output_path.parent))
    manifest_rows: list[list[str]] = []
    expected: dict[Path, tuple[list[str], list[list[str]]]] = {}
    header_only_count = 0

    try:
        for patient, assessment in pairs:
            for source in sources:
                rows = source.groups.get((patient, assessment), [])
                relative = Path(patient) / assessment / source.basename
                output_file = staging / relative
                raw = _write_csv(output_file, source.header, rows)
                expected[relative] = (source.header, rows)
                if not rows:
                    header_only_count += 1
                manifest_rows.append(
                    [
                        relative.as_posix(),
                        source.basename,
                        source.role,
                        patient,
                        assessment,
                        str(len(rows)),
                        str(len(source.header)),
                        str(not rows),
                        source.source_sha256,
                        hashlib.sha256(raw).hexdigest(),
                    ]
                )

        errors: list[str] = []
        actual_paths = {
            path.relative_to(staging)
            for path in staging.rglob("*.csv")
            if ".split-audit" not in path.parts
        }
        if actual_paths != set(expected):
            errors.append("Output path set does not match the expected partition set")
        for relative, (header, rows) in expected.items():
            actual_header, actual_rows = _read_output(staging / relative)
            if actual_header != header:
                errors.append(f"Header mismatch: {relative.as_posix()}")
            if actual_rows != rows:
                errors.append(f"Row content/order mismatch: {relative.as_posix()}")

        from .audit import verify_dataset, verify_manifest

        independent_audit = verify_dataset(input_path, staging)
        if independent_audit.status != "PASS":
            raise RuntimeError("Independent output audit failed")

        audit_dir = staging / ".split-audit"
        audit_dir.mkdir()
        _write_csv(
            audit_dir / "MANIFEST.csv",
            [
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
            ],
            manifest_rows,
        )
        manifest_audit = verify_manifest(input_path, staging)
        if manifest_audit.status != "PASS":
            raise RuntimeError("Manifest audit failed")
        data_tree_sha256 = _data_tree_sha256(staging, set(expected))
        audit = {
            "status": "PASS" if not errors else "FAIL",
            "errors": errors,
            "source_file_count": len(sources),
            "source_row_count": sum(len(source.rows) for source in sources),
            "patient_count": len(patients),
            "patient_assessment_count": len(pairs),
            "output_csv_count": len(expected),
            "header_only_count": header_only_count,
            "data_tree_sha256": data_tree_sha256,
            "data_audit": asdict(independent_audit),
            "manifest_audit": asdict(manifest_audit),
        }
        (audit_dir / "AUDIT.json").write_text(
            json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        summary = {key: value for key, value in audit.items() if key != "errors"}
        (audit_dir / "SUMMARY.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        inventory = {
            "input_kind": "directory" if input_path.is_dir() else "zip",
            "source_file_count": len(sources),
            "sources": [
                {
                    "member": source.member,
                    "basename": source.basename,
                    "role": source.role,
                    "byte_count": len(source.raw),
                    "row_count": len(source.rows),
                    "column_count": len(source.header),
                    "pin_column": source.header[source.pin_index],
                    "assessment_column": source.header[source.assessment_index],
                    "source_sha256": source.source_sha256,
                }
                for source in sources
            ],
        }
        (audit_dir / "SOURCE_INVENTORY.json").write_text(
            json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        audit_markdown = "\n".join(
            [
                "# Split Audit",
                "",
                f"Status: {audit['status']}",
                "",
                f"- Source CSV files: {audit['source_file_count']}",
                f"- Source data rows: {audit['source_row_count']}",
                f"- Patient folders: {audit['patient_count']}",
                f"- Patient/assessment folders: {audit['patient_assessment_count']}",
                f"- Output CSV files: {audit['output_csv_count']}",
                f"- Intentional header-only CSV files: {audit['header_only_count']}",
                f"- Data tree SHA-256: `{audit['data_tree_sha256']}`",
                f"- Independent data audit: {independent_audit.status}",
                f"- Manifest audit: {manifest_audit.status}",
                f"- Audit errors: {len(errors)}",
                "",
            ]
        )
        (audit_dir / "AUDIT.md").write_text(audit_markdown, encoding="utf-8")
        if errors:
            raise RuntimeError("Output audit failed")
        if output_path.exists():
            raise FileExistsError(f"Output path already exists: {output_path}")
        os.replace(staging, output_path)
    except BaseException:
        if staging.exists():
            shutil.rmtree(staging)
        raise

    return plan
