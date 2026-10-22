"""End-to-end reference run: source files -> cleaned movements -> master -> schedule."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from depreciation_model.cleaning import load_movements, load_register
from depreciation_model.config import Paths
from depreciation_model.master import build_asset_master, build_transfers
from depreciation_model.schedule import build_schedule

log = logging.getLogger(__name__)


@dataclass
class ModelResult:
    register: pd.DataFrame
    movements: pd.DataFrame
    master: pd.DataFrame
    transfers: pd.DataFrame
    schedule: pd.DataFrame
    months: list[date]


def run_model(paths: Paths, months: list[date]) -> ModelResult:
    """Run the Python reference implementation over the files in ``paths.source_dir``."""
    register = load_register(paths.register_file)
    movements = load_movements(paths.movements_dir)
    master = build_asset_master(register, movements)
    transfers = build_transfers(movements, master)
    schedule = build_schedule(master, transfers, months)
    return ModelResult(register, movements, master, transfers, schedule, months)
