"""Seeded synthetic data: an opening asset register and 24 messy monthly movement files.

The register is a clean system extract as at the first reporting day. The
monthly movement files imitate what finance teams actually receive: every
month the same information, but exported by different people and tools - so
column names change, numbers arrive as text with thousands separators, dates
flip to day-first, blank rows appear and some files carry a UTF-8 BOM. The
mess is deterministic per month (see :func:`month_style`) so tests can assert
that every variant is cleaned correctly.
"""

from __future__ import annotations

import csv
import io
import logging
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from depreciation_model.config import (
    CATEGORIES,
    CATEGORY_WEIGHTS,
    COST_CENTRES,
    MOVEMENT_COLUMNS,
)
from depreciation_model.dates import (
    month_end,
    month_index,
    month_start,
    random_day_between,
    report_months,
)

log = logging.getLogger(__name__)

REGISTER_COLUMNS = [
    "asset_id",
    "asset_name",
    "category",
    "cost_centre",
    "acquisition_date",
    "cost",
    "useful_life_months",
    "disposal_date",
]

NAME_TEMPLATES: dict[str, tuple[str, ...]] = {
    "Software licences": (
        "ERP licence",
        "CRM licence",
        "Database licence",
        "Analytics suite licence",
        "Security software licence",
        "Monitoring tool licence",
        "Collaboration suite licence",
    ),
    "Capitalised development": (
        "Billing engine module",
        "Self-care portal release",
        "Data warehouse build",
        "Order management feature",
        "Mobile app release",
        "Integration layer",
        "Reporting platform",
    ),
    "Usage rights": (
        "Network capacity right",
        "Duct usage right",
        "Site access right",
        "Content distribution right",
    ),
    "Trademarks and other rights": (
        "Brand licence",
        "Domain portfolio",
        "Patent licence",
        "Content rights package",
    ),
}

# Header row per variant: canonical column -> header text written to the file.
HEADER_VARIANTS: list[dict[str, str]] = [
    {c: c for c in MOVEMENT_COLUMNS},
    {
        "asset_id": "Asset ID",
        "movement_type": "Type",
        "movement_date": "Date",
        "amount": "Amount (EUR)",
        "asset_name": "Asset description",
        "category": "Category",
        "useful_life_months": "Useful life (months)",
        "cost_centre": "Cost center",
    },
    {
        "asset_id": "AssetNo",
        "movement_type": "Movement",
        "movement_date": "Posting date",
        "amount": "Value",
        "asset_name": "Description",
        "category": "Asset class",
        "useful_life_months": "Life months",
        "cost_centre": "CC",
    },
]
# Variant 2 is a legacy export that also orders the columns differently.
VARIANT_2_ORDER = [
    "movement_date",
    "asset_id",
    "movement_type",
    "asset_name",
    "amount",
    "cost_centre",
    "category",
    "useful_life_months",
]

TYPE_SPELLINGS: dict[str, tuple[str, ...]] = {
    "ADDITION": ("Addition", "addition ", "ADD"),
    "DISPOSAL": ("Disposal", " DISP", "disposal"),
    "TRANSFER": ("Transfer", "trf", "TRANSFER "),
}


@dataclass(frozen=True)
class MonthStyle:
    """How one month's file is formatted. Month 0 is always the clean reference format."""

    header_variant: int
    day_first_dates: bool
    text_numbers: bool
    blank_rows: bool
    messy_text: bool
    bom: bool


def month_style(i: int) -> MonthStyle:
    """Deterministic formatting for month ``i`` so every kind of mess is guaranteed to appear."""
    return MonthStyle(
        header_variant=i % 3,
        day_first_dates=i % 4 in (2, 3),
        text_numbers=i % 2 == 1,
        blank_rows=i % 3 == 1,
        messy_text=i % 5 in (1, 3),
        bom=i % 3 == 1,
    )


@dataclass
class GeneratedData:
    """Clean ground truth. ``movements`` is what a perfect cleaner must reproduce."""

    register: pd.DataFrame
    movements: pd.DataFrame
    months: list[date]


def _new_assets(
    rng: np.random.Generator,
    ids: list[str],
    lo: date,
    hi: date,
) -> pd.DataFrame:
    categories = list(CATEGORIES)
    rows = []
    for asset_id in ids:
        cat = categories[rng.choice(len(categories), p=CATEGORY_WEIGHTS)]
        lives, (cmin, cmax) = CATEGORIES[cat]
        acq = random_day_between(lo, hi, rng.random())
        cost = round(float(np.exp(rng.uniform(np.log(cmin), np.log(cmax)))), 2)
        template = NAME_TEMPLATES[cat][rng.integers(len(NAME_TEMPLATES[cat]))]
        rows.append(
            {
                "asset_id": asset_id,
                "asset_name": f"{template} ({acq.year})",
                "category": cat,
                "cost_centre": sorted(COST_CENTRES)[rng.integers(len(COST_CENTRES))],
                "acquisition_date": acq,
                "cost": cost,
                "useful_life_months": int(lives[rng.integers(len(lives))]),
                "disposal_date": None,
            }
        )
    return pd.DataFrame(rows, columns=REGISTER_COLUMNS)


def generate(
    seed: int = 42,
    report_start: date = date(2024, 1, 1),
    n_months: int = 24,
    n_register: int = 320,
    n_additions: int = 80,
    n_disposals: int = 30,
    n_transfers: int = 25,
) -> GeneratedData:
    """Build the opening register and the clean list of in-window movements."""
    rng = np.random.default_rng(seed)
    months = report_months(report_start, n_months)
    window_start, window_end = months[0], month_end(months[-1])

    # Opening register: acquired over the eight years before the window.
    reg_ids = [f"IA-{i:05d}" for i in range(1, n_register + 1)]
    register = _new_assets(rng, reg_ids, date(2016, 1, 1), window_start - timedelta(days=1))
    # About 6% were already disposed before the window; they must produce no rows.
    for i in register.index:
        acq = register.at[i, "acquisition_date"]
        if rng.random() < 0.06 and acq < window_start - timedelta(days=120):
            lo = acq + timedelta(days=60)
            register.at[i, "disposal_date"] = random_day_between(
                lo, window_start - timedelta(days=1), rng.random()
            )

    add_ids = [f"IA-{i:05d}" for i in range(n_register + 1, n_register + n_additions + 1)]
    additions = _new_assets(rng, add_ids, window_start, window_end)

    # In-window disposals of assets that are on the books long enough to be disposed.
    assets = pd.concat([register, additions], ignore_index=True)
    eligible = assets[
        assets["disposal_date"].isna()
        & (assets["acquisition_date"] + timedelta(days=30) <= window_end)
    ]
    picked = rng.choice(eligible.index.to_numpy(), size=n_disposals, replace=False)
    disposal_dates: dict[str, date] = {}
    for i in sorted(picked):
        lo = max(assets.at[i, "acquisition_date"] + timedelta(days=30), window_start)
        disposal_dates[assets.at[i, "asset_id"]] = random_day_between(lo, window_end, rng.random())

    # Cost-centre transfers: asset in service, at most one per asset per month,
    # never in the disposal month (keeps the month's cost centre unambiguous).
    candidates = assets[assets["disposal_date"].isna()].reset_index(drop=True)
    planned: list[tuple[date, str]] = []
    used: set[tuple[str, int]] = set()
    while len(planned) < n_transfers:
        row = candidates.iloc[int(rng.integers(len(candidates)))]
        t_date = random_day_between(window_start, window_end, rng.random())
        disp = disposal_dates.get(row["asset_id"])
        key = (row["asset_id"], month_index(t_date))
        if t_date < row["acquisition_date"] or key in used:
            continue
        if disp is not None and month_index(t_date) >= month_index(disp):
            continue
        used.add(key)
        planned.append((t_date, row["asset_id"]))
    current_cc = dict(zip(assets["asset_id"], assets["cost_centre"], strict=True))
    transfers = []
    for t_date, asset_id in sorted(planned):
        options = [cc for cc in sorted(COST_CENTRES) if cc != current_cc[asset_id]]
        new_cc = options[int(rng.integers(len(options)))]
        current_cc[asset_id] = new_cc
        transfers.append((asset_id, t_date, new_cc))

    rows = []
    for _, a in additions.iterrows():
        rows.append(
            {
                "asset_id": a["asset_id"],
                "movement_type": "ADDITION",
                "movement_date": a["acquisition_date"],
                "amount": a["cost"],
                "asset_name": a["asset_name"],
                "category": a["category"],
                "useful_life_months": a["useful_life_months"],
                "cost_centre": a["cost_centre"],
            }
        )
    names = dict(zip(assets["asset_id"], assets["asset_name"], strict=True))
    for asset_id, d in disposal_dates.items():
        rows.append(
            {
                "asset_id": asset_id,
                "movement_type": "DISPOSAL",
                "movement_date": d,
                "amount": None,
                "asset_name": names[asset_id],
                "category": None,
                "useful_life_months": None,
                "cost_centre": None,
            }
        )
    for asset_id, d, new_cc in transfers:
        rows.append(
            {
                "asset_id": asset_id,
                "movement_type": "TRANSFER",
                "movement_date": d,
                "amount": None,
                "asset_name": None,
                "category": None,
                "useful_life_months": None,
                "cost_centre": new_cc,
            }
        )
    movements = pd.DataFrame(rows, columns=MOVEMENT_COLUMNS)
    movements["file_month"] = movements["movement_date"].map(month_start)
    movements = movements.sort_values(["movement_date", "asset_id"]).reset_index(drop=True)

    log.info(
        "Generated %d register assets, %d additions, %d disposals, %d transfers over %d months",
        len(register),
        len(additions),
        len(disposal_dates),
        len(transfers),
        n_months,
    )
    return GeneratedData(register=register, movements=movements, months=months)


def movement_file_name(month: date) -> str:
    return f"movements_{month.year}_{month.month:02d}.csv"


def _fmt_number(value: object, as_text: bool, decimals: int) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return ""
    if as_text:
        return f"{float(value):,.{decimals}f} "
    return f"{float(value):.{decimals}f}"


def render_movement_file(month_rows: pd.DataFrame, style: MonthStyle, seed: int) -> bytes:
    """Write one month's movements in that month's (messy) export format."""
    rng = np.random.default_rng(seed)
    header_map = HEADER_VARIANTS[style.header_variant]
    order = VARIANT_2_ORDER if style.header_variant == 2 else MOVEMENT_COLUMNS
    blank = [""] * len(order)

    out_rows: list[list[str]] = []
    for _, r in month_rows.iterrows():
        values: dict[str, str] = {}
        asset_id = r["asset_id"]
        mtype = r["movement_type"]
        if style.messy_text:
            asset_id = f" {asset_id.lower()}" if rng.random() < 0.5 else f"{asset_id}  "
            spellings = TYPE_SPELLINGS[mtype]
            mtype = spellings[int(rng.integers(len(spellings)))]
        d: date = r["movement_date"]
        values["asset_id"] = asset_id
        values["movement_type"] = mtype
        values["movement_date"] = d.strftime("%d/%m/%Y" if style.day_first_dates else "%Y-%m-%d")
        values["amount"] = _fmt_number(r["amount"], style.text_numbers, 2)
        life = r["useful_life_months"]
        values["useful_life_months"] = "" if pd.isna(life) else str(int(life))
        if style.text_numbers and values["useful_life_months"]:
            values["useful_life_months"] = f" {values['useful_life_months']}"
        for col in ("asset_name", "category", "cost_centre"):
            values[col] = "" if pd.isna(r[col]) else str(r[col])
        out_rows.append([values[c] for c in order])

    if style.blank_rows and out_rows:
        out_rows.insert(len(out_rows) // 2, blank)

    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    if style.blank_rows:
        writer.writerows([blank, blank])
    writer.writerow([header_map[c] for c in order])
    writer.writerows(out_rows)
    if style.blank_rows:
        writer.writerows([blank, blank])
    return buf.getvalue().encode("utf-8-sig" if style.bom else "utf-8")


def write_source_files(data: GeneratedData, source_dir: Path, seed: int = 42) -> list[Path]:
    """Write ``asset_register.csv`` and one movement file per month (even empty months)."""
    movements_dir = source_dir / "movements"
    movements_dir.mkdir(parents=True, exist_ok=True)
    for old in movements_dir.glob("movements_*.csv"):
        old.unlink()

    register = data.register.copy()
    register["acquisition_date"] = register["acquisition_date"].map(lambda d: d.isoformat())
    register["disposal_date"] = register["disposal_date"].map(
        lambda d: d.isoformat() if isinstance(d, date) else ""
    )
    register["cost"] = register["cost"].map(lambda x: f"{x:.2f}")
    register_path = source_dir / "asset_register.csv"
    register.to_csv(register_path, index=False, lineterminator="\n")

    written = [register_path]
    for i, month in enumerate(data.months):
        rows = data.movements[data.movements["file_month"] == month]
        path = movements_dir / movement_file_name(month)
        path.write_bytes(render_movement_file(rows, month_style(i), seed + i))
        written.append(path)
    log.info("Wrote register and %d movement files to %s", len(data.months), source_dir)
    return written
