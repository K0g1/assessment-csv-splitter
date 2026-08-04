from __future__ import annotations

import csv
import stat
import zipfile
from pathlib import Path

import pytest

import assessment_csv_splitter.core as core
from assessment_csv_splitter.core import split_dataset


def rewrite_rows(path: Path, rows: list[list[str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)


def read_rows(path: Path) -> list[list[str]]:
    with path.open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.reader(handle))


def test_blank_pin_is_rejected_without_committing_output(
    six_csv_directory: Path, tmp_path: Path
) -> None:
    registration = next(six_csv_directory.glob("* Registration Data.csv"))
    rows = read_rows(registration)
    rows[1][0] = ""
    rewrite_rows(registration, rows)
    output = tmp_path / "split"

    with pytest.raises(ValueError, match="Blank PIN"):
        split_dataset(six_csv_directory, output)

    assert not output.exists()


def test_blank_assessment_is_rejected_without_committing_output(
    six_csv_directory: Path, tmp_path: Path
) -> None:
    registration = next(six_csv_directory.glob("* Registration Data.csv"))
    rows = read_rows(registration)
    rows[1][-1] = ""
    rewrite_rows(registration, rows)
    output = tmp_path / "split"

    with pytest.raises(ValueError, match="Blank assessment name"):
        split_dataset(six_csv_directory, output)

    assert not output.exists()


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        (0, "../escape", "Unsafe PIN"),
        (0, "P/001", "Unsafe PIN"),
        (0, r"P\\001", "Unsafe PIN"),
        (-1, "CON", "Unsafe assessment name"),
        (-1, "Follow:Up", "Unsafe assessment name"),
        (-1, "Follow-Up.", "Unsafe assessment name"),
        (-1, "Follow-Up ", "Unsafe assessment name"),
    ],
)
def test_unsafe_routing_components_are_rejected_before_staging(
    six_csv_directory: Path,
    tmp_path: Path,
    column: int,
    value: str,
    message: str,
) -> None:
    registration = next(six_csv_directory.glob("* Registration Data.csv"))
    rows = read_rows(registration)
    rows[1][column] = value
    rewrite_rows(registration, rows)
    output = tmp_path / "split"

    with pytest.raises(ValueError, match=message):
        split_dataset(six_csv_directory, output)

    assert not output.exists()
    assert not (tmp_path / "escape").exists()


@pytest.mark.parametrize(
    ("column", "value", "message"),
    [
        (0, "p001", "PIN path collision"),
        (-1, "baseline", "Assessment path collision"),
    ],
)
def test_casefold_equivalent_routing_components_are_rejected(
    six_csv_directory: Path,
    tmp_path: Path,
    column: int,
    value: str,
    message: str,
) -> None:
    registration = next(six_csv_directory.glob("* Registration Data.csv"))
    rows = read_rows(registration)
    rows[2][column] = value
    rewrite_rows(registration, rows)
    output = tmp_path / "split"

    with pytest.raises(ValueError, match=message):
        split_dataset(six_csv_directory, output)

    assert not output.exists()


def test_output_cannot_be_nested_inside_input_directory(
    six_csv_directory: Path,
) -> None:
    output = six_csv_directory / "split"

    with pytest.raises(ValueError, match="inside the input directory"):
        split_dataset(six_csv_directory, output)

    assert not output.exists()


@pytest.mark.parametrize(
    ("replacement_header", "message"),
    [
        ("P I N", "exactly one PIN"),
        ("Visit Name", "exactly one assessment-name"),
    ],
)
def test_routing_headers_must_be_unambiguous(
    six_csv_directory: Path,
    tmp_path: Path,
    replacement_header: str,
    message: str,
) -> None:
    assessment_data = next(six_csv_directory.glob("* Assessment Data.csv"))
    rows = read_rows(assessment_data)
    if replacement_header == "P I N":
        rows[0][1] = replacement_header
    else:
        rows[0][2] = replacement_header
    rewrite_rows(assessment_data, rows)
    output = tmp_path / "split"

    with pytest.raises(ValueError, match=message):
        split_dataset(six_csv_directory, output)

    assert not output.exists()


def test_source_basename_must_be_windows_safe(
    six_csv_directory: Path,
    tmp_path: Path,
) -> None:
    assessment_data = next(six_csv_directory.glob("* Assessment Data.csv"))
    unsafe_name = six_csv_directory / f"bad:name {assessment_data.name}"
    assessment_data.rename(unsafe_name)
    output = tmp_path / "split"

    with pytest.raises(ValueError, match="Unsafe source basename"):
        split_dataset(six_csv_directory, output)

    assert not output.exists()


def test_symlinked_source_csv_is_rejected(
    six_csv_directory: Path,
    tmp_path: Path,
) -> None:
    source_file = next(six_csv_directory.glob("* Assessment Scores.csv"))
    external_file = tmp_path / "external.csv"
    source_file.replace(external_file)
    source_file.symlink_to(external_file)
    output = tmp_path / "split"

    with pytest.raises(ValueError, match="symbolic link"):
        split_dataset(six_csv_directory, output)

    assert not output.exists()


def test_zip_symlink_member_is_rejected(
    six_csv_directory: Path,
    tmp_path: Path,
) -> None:
    source_zip = tmp_path / "combined.zip"
    files = sorted(six_csv_directory.glob("*.csv"))
    with zipfile.ZipFile(source_zip, "w") as archive:
        for index, source_file in enumerate(files):
            member_name = f"nested/{source_file.name}"
            if index == 0:
                info = zipfile.ZipInfo(member_name)
                info.create_system = 3
                info.external_attr = (stat.S_IFLNK | 0o777) << 16
                archive.writestr(info, "elsewhere.csv")
            else:
                archive.write(source_file, member_name)
    output = tmp_path / "split"

    with pytest.raises(ValueError, match="symbolic link"):
        split_dataset(source_zip, output)

    assert not output.exists()


def test_total_source_size_limit_is_enforced_before_parsing(
    six_csv_directory: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(core, "MAX_TOTAL_SOURCE_BYTES", 1)
    output = tmp_path / "split"

    with pytest.raises(ValueError, match="total source size limit"):
        split_dataset(six_csv_directory, output)

    assert not output.exists()


def test_large_csv_field_is_preserved(
    six_csv_directory: Path,
    tmp_path: Path,
) -> None:
    assessment_data = next(six_csv_directory.glob("* Assessment Data.csv"))
    rows = read_rows(assessment_data)
    large_value = "x" * 200_000
    rows[1][-1] = large_value
    rewrite_rows(assessment_data, rows)
    output = tmp_path / "split"

    split_dataset(six_csv_directory, output)

    partition = output / "P001" / "Baseline" / assessment_data.name
    assert read_rows(partition)[1][-1] == large_value
