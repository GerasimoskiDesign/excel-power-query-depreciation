"""Messy monthly files must clean to exactly the generator's ground truth."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from depreciation_model.cleaning import (
    SourceFileError,
    clean_movement_file,
    load_movements,
    parse_date,
    parse_number,
)
from depreciation_model.config import MOVEMENT_COLUMNS
from depreciation_model.generate import (
    GeneratedData,
    month_style,
    movement_file_name,
    render_movement_file,
)

HEADER = ",".join(MOVEMENT_COLUMNS)


def _truth_for(generated: GeneratedData, month: date) -> pd.DataFrame:
    rows = generated.movements[generated.movements["file_month"] == month]
    return rows[MOVEMENT_COLUMNS].reset_index(drop=True)


@pytest.mark.parametrize("i", range(24))
def test_every_month_file_cleans_to_ground_truth(
    i: int, generated: GeneratedData, run_root: Path
) -> None:
    month = generated.months[i]
    path = run_root / "source_files" / "movements" / movement_file_name(month)
    cleaned = clean_movement_file(path.read_bytes(), path.name)
    expected = _truth_for(generated, month)
    got = cleaned[MOVEMENT_COLUMNS].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        got.astype(object).where(got.notna(), None),
        expected.astype(object).where(expected.notna(), None),
        check_dtype=False,
    )


def test_all_kinds_of_mess_are_present_in_the_generated_files() -> None:
    styles = [month_style(i) for i in range(24)]
    assert {s.header_variant for s in styles} == {0, 1, 2}
    assert any(s.day_first_dates for s in styles)
    assert any(s.text_numbers for s in styles)
    assert any(s.blank_rows for s in styles)
    assert any(s.messy_text for s in styles)
    assert any(s.bom for s in styles)
    first = styles[0]
    assert not (first.text_numbers or first.blank_rows or first.messy_text or first.bom)


def test_messiest_month_really_is_messy(generated: GeneratedData) -> None:
    # Month index 1 combines BOM, blank rows, renamed headers, text numbers and messy ids.
    month = generated.months[1]
    raw = render_movement_file(
        _truth_for(generated, month).assign(file_month=month), month_style(1), 43
    )
    text = raw.decode("utf-8")
    assert text.startswith("\ufeff,,,")
    assert "Amount (EUR)" in text
    assert '"' in text  # thousands separators force quoting


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1234.5", 1234.5),
        ("1,234.50 ", 1234.5),
        (" 36", 36.0),
        ("1 000 000.25", 1000000.25),
        ("", None),
    ],
)
def test_parse_number_handles_text_formatted_numbers(text: str, expected: float | None) -> None:
    assert parse_number(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2024-03-15", date(2024, 3, 15)),
        ("15/03/2024", date(2024, 3, 15)),
        (" 01/12/2025 ", date(2025, 12, 1)),
        ("2024-02-29 00:00:00", date(2024, 2, 29)),
        ("", None),
    ],
)
def test_parse_date_accepts_iso_and_day_first(text: str, expected: date | None) -> None:
    assert parse_date(text) == expected


def test_day_first_is_not_confused_with_month_first() -> None:
    # 03/04/2024 is 3 April in these exports, never 4 March.
    assert parse_date("03/04/2024") == date(2024, 4, 3)


def test_unknown_header_stops_the_run() -> None:
    content = (HEADER.replace("amount", "amount_usd") + "\n").encode()
    with pytest.raises(SourceFileError, match="unknown column header"):
        clean_movement_file(content, "bad.csv")


def test_missing_column_stops_the_run() -> None:
    content = (HEADER.replace(",cost_centre", "") + "\n").encode()
    with pytest.raises(SourceFileError, match="missing columns"):
        clean_movement_file(content, "bad.csv")


def test_two_headers_for_the_same_column_stop_the_run() -> None:
    content = (HEADER + ",Value\n").encode()
    with pytest.raises(SourceFileError, match="same column"):
        clean_movement_file(content, "bad.csv")


def test_unknown_movement_type_stops_the_run() -> None:
    content = f"{HEADER}\nIA-00001,write-off,2024-01-05,,,,,\n".encode()
    with pytest.raises(SourceFileError, match="unknown movement type"):
        clean_movement_file(content, "bad.csv")


def test_blank_rows_bom_and_messy_text_are_cleaned() -> None:
    content = (
        "\ufeff,,,,,,,\n,,,,,,,\n"
        "Asset ID,Type,Date,Amount (EUR),Asset description,Category,"
        "Useful life (months),Cost center\n"
        ' ia-00007 , addition ,05/02/2024,"12,500.00 ",X licence,Software licences, 48 ,CC-200\n'
        ",,,,,,,\n"
        "IA-00001,trf,2024-02-07,,,,,CC-300\n"
        ",,,,,,,\n"
    ).encode()
    df = clean_movement_file(content, "m.csv")
    assert list(df["asset_id"]) == ["IA-00007", "IA-00001"]
    assert list(df["movement_type"]) == ["ADDITION", "TRANSFER"]
    assert df.loc[0, "amount"] == 12500.0
    assert df.loc[0, "useful_life_months"] == 48
    assert df.loc[0, "movement_date"] == date(2024, 2, 5)
    assert df.loc[1, "amount"] is None


def test_folder_load_ignores_excel_lock_files(tmp_path: Path) -> None:
    (tmp_path / "movements_2024_01.csv").write_text(
        f"{HEADER}\nIA-1,ADDITION,2024-01-02,10,a,b,12,CC-100\n"
    )
    (tmp_path / "~$movements_2024_01.csv").write_text("garbage")
    (tmp_path / "notes.txt").write_text("ignore me")
    df = load_movements(tmp_path)
    assert len(df) == 1


def test_combined_movements_match_ground_truth_counts(model, generated: GeneratedData) -> None:
    got = model.movements["movement_type"].value_counts().to_dict()
    want = generated.movements["movement_type"].value_counts().to_dict()
    assert got == want == {"ADDITION": 80, "DISPOSAL": 30, "TRANSFER": 25}
