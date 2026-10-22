"""Totals reconcile: per asset-month, per month, month to month and against the inputs."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from depreciation_model.generate import GeneratedData, generate, write_source_files
from depreciation_model.pipeline import ModelResult
from depreciation_model.reporting import monthly_totals, star_schema, yearly_measures
from tests.conftest import REPO_ROOT

TOL = 1e-6


def test_every_asset_month_rolls_forward(model: ModelResult) -> None:
    s = model.schedule
    cost = s["opening_cost"] + s["additions"] - s["disposals_cost"] - s["closing_cost"]
    acc = s["opening_acc_dep"] + s["depreciation"] - s["disposal_acc_dep"] - s["closing_acc_dep"]
    nbv = s["closing_cost"] - s["closing_acc_dep"] - s["closing_nbv"]
    assert cost.abs().max() < TOL
    assert acc.abs().max() < TOL
    assert nbv.abs().max() < TOL


def test_depreciation_is_never_negative_and_nbv_never_below_zero(model: ModelResult) -> None:
    s = model.schedule
    assert (s["depreciation"] >= -TOL).all()
    assert (s["closing_nbv"] >= -TOL).all()
    assert (s["closing_acc_dep"] <= s["closing_cost"] + TOL).all()


def test_monthly_closing_equals_next_month_opening(model: ModelResult) -> None:
    t = monthly_totals(model.schedule).set_index("month_start")
    closing = t[["closing_cost", "closing_acc_dep"]].iloc[:-1].to_numpy()
    opening = t[["opening_cost", "opening_acc_dep"]].iloc[1:].to_numpy()
    assert abs(closing - opening).max() < TOL


def test_monthly_totals_roll_forward(model: ModelResult) -> None:
    t = monthly_totals(model.schedule)
    nbv_open = t["opening_cost"] - t["opening_acc_dep"]
    rolled = nbv_open + t["additions"] - t["depreciation"] - t["disposal_nbv"]
    assert (rolled - t["closing_nbv"]).abs().max() < TOL


def test_additions_and_disposals_reconcile_to_the_movement_files(model: ModelResult) -> None:
    s, mv = model.schedule, model.movements
    adds = mv.loc[mv["movement_type"] == "ADDITION", "amount"].astype(float).sum()
    assert s["additions"].sum() == pytest.approx(adds)
    disposed = set(mv.loc[mv["movement_type"] == "DISPOSAL", "asset_id"])
    assert set(s.loc[s["disposals_cost"] > 0, "asset_id"]) == disposed


def test_disposed_assets_have_no_rows_after_disposal_month(model: ModelResult) -> None:
    s = model.schedule
    disp = model.master.dropna(subset=["disposal_date"]).set_index("asset_id")["disposal_date"]
    rows = s[s["asset_id"].isin(disp.index)]
    last_month = rows.groupby("asset_id")["month_start"].max()
    for asset_id, last in last_month.items():
        d: date = disp[asset_id]
        assert last == date(d.year, d.month, 1)


def test_fully_depreciated_assets_stay_at_zero_in_generated_data(model: ModelResult) -> None:
    s = model.schedule.sort_values(["asset_id", "month_start"])
    zero = s[s["closing_nbv"].abs() < TOL]
    assert len(zero) > 500  # the old register really contains fully depreciated assets
    first_zero = zero.groupby("asset_id")["month_start"].min()
    later = s.merge(first_zero.rename("first_zero"), on="asset_id")
    later = later[later["month_start"] > later["first_zero"]]
    assert (later["depreciation"].abs() < TOL).all()
    assert (later["closing_nbv"].abs() < TOL).all()


def test_total_depreciation_equals_change_in_accumulated_balance(model: ModelResult) -> None:
    t = monthly_totals(model.schedule)
    start = t["opening_acc_dep"].iloc[0]
    end = t["closing_acc_dep"].iloc[-1]
    assert start + t["depreciation"].sum() - t["disposal_acc_dep"].sum() == pytest.approx(end)


def test_yearly_balances_are_taken_at_year_end_not_summed(model: ModelResult) -> None:
    t = monthly_totals(model.schedule).set_index("month_start")
    y = yearly_measures(model.schedule).set_index("year")
    assert y.loc[2025, "nbv"] == pytest.approx(t.loc[date(2025, 12, 1), "closing_nbv"])
    assert y.loc[2024, "depreciation"] == pytest.approx(
        t.loc[date(2024, 1, 1) : date(2024, 12, 1), "depreciation"].sum()
    )
    assert y.loc[2025, "depreciation_yoy_change"] == pytest.approx(
        y.loc[2025, "depreciation"] - y.loc[2024, "depreciation"]
    )


def test_star_schema_keys_are_complete_and_totals_match(model: ModelResult) -> None:
    tables = star_schema(model.schedule, model.master, model.months)
    fact = tables["fact_depreciation"]
    assert tables["dim_asset"]["asset_key"].is_unique
    assert set(fact["asset_key"]) <= set(tables["dim_asset"]["asset_key"])
    assert set(fact["date_key"]) == set(tables["dim_date"]["date_key"])
    assert set(fact["cost_centre_key"]) <= set(tables["dim_cost_centre"]["cost_centre_key"])
    assert not fact.duplicated(["date_key", "asset_key"]).any()
    assert fact["depreciation"].sum() == pytest.approx(model.schedule["depreciation"].sum())


def test_generation_is_deterministic(tmp_path: Path, generated: GeneratedData) -> None:
    again = generate(seed=42, report_start=date(2024, 1, 1), n_months=24)
    pd.testing.assert_frame_equal(again.movements, generated.movements)
    a = write_source_files(again, tmp_path / "a")
    b = write_source_files(generated, tmp_path / "b")
    for fa, fb in zip(a, b, strict=True):
        assert fa.read_bytes() == fb.read_bytes()
    other = generate(seed=7, report_start=date(2024, 1, 1), n_months=24)
    assert not other.register.equals(generated.register)


def test_committed_expected_outputs_match_a_fresh_run(model: ModelResult) -> None:
    committed = pd.read_csv(REPO_ROOT / "expected_outputs" / "monthly_totals.csv")
    fresh = monthly_totals(model.schedule)
    assert list(committed.columns) == list(fresh.columns)
    for col in committed.columns[1:]:
        assert (committed[col] - fresh[col].round(2)).abs().max() < 0.006, col


def test_powerbi_readme_check_values_match_expected_outputs() -> None:
    readme = (REPO_ROOT / "powerbi" / "README.md").read_text(encoding="utf-8")
    measures = pd.read_csv(REPO_ROOT / "expected_outputs" / "yearly_measures.csv")
    for _, row in measures.iterrows():
        for col in ("depreciation", "gross_cost", "accumulated_depreciation", "nbv"):
            assert f"{row[col]:,.2f}" in readme, (row["year"], col)
