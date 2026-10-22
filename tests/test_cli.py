"""The CLI runs end to end from an empty folder."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from depreciation_model.cli import _window, main


def test_window_ends_at_as_of_month() -> None:
    months = _window("2025-12", 24)
    assert months[0].isoformat() == "2024-01-01"
    assert months[-1].isoformat() == "2025-12-01"
    assert len(months) == 24


def test_all_command_builds_every_output(tmp_path: Path) -> None:
    assert main(["all", "--root", str(tmp_path), "--as-of", "2025-06", "--months", "12"]) == 0
    assert len(list((tmp_path / "source_files" / "movements").glob("*.csv"))) == 12
    totals = pd.read_csv(tmp_path / "expected_outputs" / "monthly_totals.csv")
    assert totals["month_start"].iloc[0] == "2024-07-01"
    for name in ("dim_asset", "dim_date", "dim_cost_centre", "fact_depreciation"):
        assert (tmp_path / "powerbi" / "data" / f"{name}.csv").exists()
    assert (tmp_path / "depreciation_model.xlsx").exists()
    assert len(list((tmp_path / "docs" / "img").glob("*.png"))) == 2
