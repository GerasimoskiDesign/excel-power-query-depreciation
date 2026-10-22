"""Static configuration shared by the generator, the cleaner and the model.

Keeping the header aliases and movement-type synonyms here (mirrored in
``powerquery/04_ColumnAliases.pq`` and ``05_MovementTypeAliases.pq``) means
there is exactly one list to update when a new month arrives with yet another
column name. A test checks that the Python and M alias lists stay identical.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

DEFAULT_SEED = 42
DEFAULT_REPORT_START = "2024-01"
DEFAULT_REPORT_MONTHS = 24

# Canonical movement-file columns, in output order.
MOVEMENT_COLUMNS: list[str] = [
    "asset_id",
    "movement_type",
    "movement_date",
    "amount",
    "asset_name",
    "category",
    "useful_life_months",
    "cost_centre",
]

# Lower-cased, trimmed header text -> canonical column. Must match 04_ColumnAliases.pq.
COLUMN_ALIASES: dict[str, str] = {
    "asset_id": "asset_id",
    "asset id": "asset_id",
    "assetno": "asset_id",
    "asset no": "asset_id",
    "movement_type": "movement_type",
    "type": "movement_type",
    "movement": "movement_type",
    "movement_date": "movement_date",
    "date": "movement_date",
    "posting date": "movement_date",
    "amount": "amount",
    "amount (eur)": "amount",
    "value": "amount",
    "asset_name": "asset_name",
    "asset description": "asset_name",
    "description": "asset_name",
    "category": "category",
    "asset class": "category",
    "useful_life_months": "useful_life_months",
    "useful life (months)": "useful_life_months",
    "life months": "useful_life_months",
    "cost_centre": "cost_centre",
    "cost center": "cost_centre",
    "cc": "cost_centre",
}

# Lower-cased, trimmed movement-type text -> canonical type. Must match 05_MovementTypeAliases.pq.
MOVEMENT_TYPE_ALIASES: dict[str, str] = {
    "addition": "ADDITION",
    "add": "ADDITION",
    "disposal": "DISPOSAL",
    "disp": "DISPOSAL",
    "transfer": "TRANSFER",
    "trf": "TRANSFER",
}

# Category -> (allowed useful lives in months, (min cost, max cost)).
CATEGORIES: dict[str, tuple[tuple[int, ...], tuple[float, float]]] = {
    "Software licences": ((36, 48, 60), (4_000.0, 350_000.0)),
    "Capitalised development": ((36, 48, 60), (20_000.0, 900_000.0)),
    "Usage rights": ((60, 84, 120, 180), (50_000.0, 2_500_000.0)),
    "Trademarks and other rights": ((60, 120), (10_000.0, 400_000.0)),
}
CATEGORY_WEIGHTS: tuple[float, ...] = (0.45, 0.30, 0.10, 0.15)

COST_CENTRES: dict[str, tuple[str, str]] = {
    "CC-100": ("IT Platforms", "Technology"),
    "CC-200": ("Network Operations", "Technology"),
    "CC-300": ("Customer Care", "Commercial"),
    "CC-400": ("Sales and Marketing", "Commercial"),
    "CC-500": ("Finance and Administration", "Corporate"),
    "CC-600": ("Product Development", "Technology"),
}

# Monthly totals compared by the Excel Check sheet (PQ vs Python), in sheet order.
CHECK_METRICS: list[str] = [
    "asset_rows",
    "additions",
    "disposals_cost",
    "depreciation",
    "closing_cost",
    "closing_acc_dep",
    "closing_nbv",
]

CHECK_TOLERANCE = 0.01


@dataclass(frozen=True)
class Paths:
    """Where inputs and outputs live, relative to the repository root."""

    root: Path

    @property
    def source_dir(self) -> Path:
        return self.root / os.getenv("DEPRECIATION_SOURCE_DIR", "source_files")

    @property
    def movements_dir(self) -> Path:
        return self.source_dir / "movements"

    @property
    def register_file(self) -> Path:
        return self.source_dir / "asset_register.csv"

    @property
    def expected_dir(self) -> Path:
        return self.root / os.getenv("DEPRECIATION_EXPECTED_DIR", "expected_outputs")

    @property
    def powerbi_dir(self) -> Path:
        return self.root / "powerbi" / "data"

    @property
    def img_dir(self) -> Path:
        return self.root / "docs" / "img"

    @property
    def workbook_file(self) -> Path:
        return self.root / "depreciation_model.xlsx"


def load_env() -> None:
    """Load optional settings from ``.env`` (never required; see ``.env.example``)."""
    load_dotenv(override=False)


def default_seed() -> int:
    return int(os.getenv("DEPRECIATION_SEED", str(DEFAULT_SEED)))
