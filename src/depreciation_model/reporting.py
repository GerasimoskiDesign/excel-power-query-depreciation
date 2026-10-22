"""Monthly totals, expected outputs and the Power BI star schema.

Amounts are kept unrounded through the calculation and rounded to cents only
when written to CSV - rounding row by row first would make the monthly totals
drift a few cents away from what Power Query produces.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

import pandas as pd

from depreciation_model.config import COST_CENTRES
from depreciation_model.dates import month_end
from depreciation_model.schedule import AMOUNT_COLUMNS

log = logging.getLogger(__name__)

# Fixed English names - strftime("%b") would follow the PC's locale.
MONTH_NAMES = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def monthly_totals(schedule: pd.DataFrame) -> pd.DataFrame:
    """Totals per month - the table the Excel Check sheet compares against Power Query."""
    totals = (
        schedule.groupby("month_start", sort=True)[AMOUNT_COLUMNS]
        .sum()
        .join(schedule.groupby("month_start").size().rename("asset_rows"))
        .reset_index()
    )
    return totals[["month_start", "asset_rows", *AMOUNT_COLUMNS]]


def totals_by(schedule: pd.DataFrame, key: str) -> pd.DataFrame:
    """Depreciation and closing balances per month and ``key`` (category / cost_centre)."""
    cols = ["depreciation", "closing_cost", "closing_acc_dep", "closing_nbv"]
    return schedule.groupby(["month_start", key], sort=True)[cols].sum().reset_index()


def yearly_measures(schedule: pd.DataFrame) -> pd.DataFrame:
    """Values the DAX measures must show per calendar year (for checking the Power BI report).

    Balances (cost, accumulated depreciation, NBV) are taken at the last month
    of the year - they are semi-additive and must never be summed over months.
    """
    df = schedule.assign(year=schedule["month_start"].map(lambda d: d.year))
    rows = []
    for year, grp in df.groupby("year", sort=True):
        last = grp["month_start"].max()
        at_end = grp[grp["month_start"] == last]
        rows.append(
            {
                "year": int(year),
                "depreciation": grp["depreciation"].sum(),
                "gross_cost": at_end["closing_cost"].sum(),
                "accumulated_depreciation": at_end["closing_acc_dep"].sum(),
                "nbv": at_end["closing_nbv"].sum(),
            }
        )
    out = pd.DataFrame(rows)
    out["depreciation_pct_of_cost"] = out["depreciation"] / out["gross_cost"]
    prev = out["depreciation"].shift(1)
    out["depreciation_yoy_change"] = out["depreciation"] - prev
    out["depreciation_yoy_pct"] = out["depreciation_yoy_change"] / prev
    return out


def star_schema(
    schedule: pd.DataFrame, master: pd.DataFrame, months: list[date]
) -> dict[str, pd.DataFrame]:
    """dim_asset, dim_date, dim_cost_centre and fact_depreciation with integer surrogate keys."""
    dim_asset = master.sort_values("asset_id").reset_index(drop=True).copy()
    dim_asset.insert(0, "asset_key", range(1, len(dim_asset) + 1))
    dim_asset["monthly_charge"] = dim_asset["cost"] / dim_asset["useful_life_months"]
    # The month's cost centre lives on the fact (transfers); this is only the starting one.
    dim_asset = dim_asset.rename(columns={"cost_centre": "initial_cost_centre"})

    codes = sorted(COST_CENTRES)
    dim_cc = pd.DataFrame(
        {
            "cost_centre_key": range(1, len(codes) + 1),
            "cost_centre_code": codes,
            "cost_centre_name": [COST_CENTRES[c][0] for c in codes],
            "division": [COST_CENTRES[c][1] for c in codes],
        }
    )

    dim_date = pd.DataFrame(
        {
            "date_key": [int(m.strftime("%Y%m%d")) for m in months],
            "month_start": months,
            "month_end": [month_end(m) for m in months],
            "year": [m.year for m in months],
            "quarter": [f"Q{(m.month - 1) // 3 + 1}" for m in months],
            "month_number": [m.month for m in months],
            "month_name": [MONTH_NAMES[m.month - 1] for m in months],
            "year_month": [m.strftime("%Y-%m") for m in months],
            "month_index": [m.year * 12 + m.month - 1 for m in months],
        }
    )

    asset_keys = dict(zip(dim_asset["asset_id"], dim_asset["asset_key"], strict=True))
    cc_keys = dict(zip(dim_cc["cost_centre_code"], dim_cc["cost_centre_key"], strict=True))
    fact = pd.DataFrame(
        {
            "date_key": schedule["month_start"].map(lambda d: int(d.strftime("%Y%m%d"))),
            "asset_key": schedule["asset_id"].map(asset_keys),
            "cost_centre_key": schedule["cost_centre"].map(cc_keys),
        }
    )
    if fact.isna().any().any():
        raise ValueError("Fact table has rows without a dimension key")
    for col in AMOUNT_COLUMNS:
        fact[col] = schedule[col]
    return {
        "dim_asset": dim_asset,
        "dim_date": dim_date,
        "dim_cost_centre": dim_cc,
        "fact_depreciation": fact,
    }


def write_csv(df: pd.DataFrame, path: Path) -> Path:
    """Deterministic CSV: LF line endings, ISO dates, floats rounded to cents."""
    path.parent.mkdir(parents=True, exist_ok=True)
    out = df.copy()
    for col in out.columns:
        if pd.api.types.is_float_dtype(out[col]):
            out[col] = out[col].round(2) + 0.0  # + 0.0 turns -0.0 into 0.0
        elif out[col].dtype == object:
            out[col] = out[col].map(lambda v: v.isoformat() if isinstance(v, date) else v)
    out.to_csv(path, index=False, lineterminator="\n", float_format="%.2f")
    return path


def write_expected_outputs(schedule: pd.DataFrame, expected_dir: Path) -> list[Path]:
    measures = yearly_measures(schedule)
    paths = [
        write_csv(monthly_totals(schedule), expected_dir / "monthly_totals.csv"),
        write_csv(totals_by(schedule, "category"), expected_dir / "monthly_by_category.csv"),
        write_csv(totals_by(schedule, "cost_centre"), expected_dir / "monthly_by_cost_centre.csv"),
    ]
    # Percentages need more than two decimals.
    pct = measures[["depreciation_pct_of_cost", "depreciation_yoy_pct"]]
    measures_out = measures.drop(columns=pct.columns).round(2)
    measures_out["depreciation_pct_of_cost"] = pct["depreciation_pct_of_cost"].round(6)
    measures_out["depreciation_yoy_pct"] = pct["depreciation_yoy_pct"].round(6)
    path = expected_dir / "yearly_measures.csv"
    measures_out.to_csv(path, index=False, lineterminator="\n")
    paths.append(path)
    log.info("Wrote %d expected-output files to %s", len(paths), expected_dir)
    return paths


def write_star_schema(tables: dict[str, pd.DataFrame], out_dir: Path) -> list[Path]:
    paths = [write_csv(df, out_dir / f"{name}.csv") for name, df in tables.items()]
    log.info("Wrote star schema (%s) to %s", ", ".join(tables), out_dir)
    return paths
