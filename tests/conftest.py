"""Shared fixtures: one full synthetic run per test session (takes about a second)."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from depreciation_model.config import Paths
from depreciation_model.generate import GeneratedData, generate, write_source_files
from depreciation_model.pipeline import ModelResult, run_model

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def generated() -> GeneratedData:
    return generate(seed=42, report_start=date(2024, 1, 1), n_months=24)


@pytest.fixture(scope="session")
def run_root(tmp_path_factory: pytest.TempPathFactory, generated: GeneratedData) -> Path:
    root = tmp_path_factory.mktemp("run")
    write_source_files(generated, root / "source_files", seed=42)
    return root


@pytest.fixture(scope="session")
def model(run_root: Path, generated: GeneratedData) -> ModelResult:
    return run_model(Paths(root=run_root), generated.months)


def make_master(rows: list[dict]) -> pd.DataFrame:
    """Small hand-written asset master for unit tests."""
    defaults = {
        "asset_name": "Test asset",
        "category": "Software licences",
        "cost_centre": "CC-100",
        "disposal_date": None,
        "source": "register",
    }
    df = pd.DataFrame([{**defaults, **r} for r in rows])
    df["cost"] = df["cost"].astype(float)
    df["useful_life_months"] = df["useful_life_months"].astype(int)
    return df.astype({"disposal_date": object}).where(df.notna(), None)


NO_TRANSFERS = pd.DataFrame(columns=["asset_id", "effective_month_index", "cost_centre"])
