"""Joins between register and movements: the places where manual workbooks break."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from depreciation_model.config import MOVEMENT_COLUMNS
from depreciation_model.master import MasterDataError, build_asset_master, build_transfers
from depreciation_model.pipeline import ModelResult

REGISTER = pd.DataFrame(
    [
        {
            "asset_id": "IA-1",
            "asset_name": "Licence",
            "category": "Software licences",
            "cost_centre": "CC-100",
            "acquisition_date": date(2022, 1, 10),
            "cost": 1000.0,
            "useful_life_months": 36,
            "disposal_date": None,
        },
        {
            "asset_id": "IA-2",
            "asset_name": "Old licence",
            "category": "Software licences",
            "cost_centre": "CC-200",
            "acquisition_date": date(2019, 1, 10),
            "cost": 500.0,
            "useful_life_months": 36,
            "disposal_date": date(2023, 6, 1),
        },
    ]
).astype(object)


def _movements(rows: list[dict]) -> pd.DataFrame:
    base = dict.fromkeys(MOVEMENT_COLUMNS)
    return pd.DataFrame([{**base, **r} for r in rows], columns=MOVEMENT_COLUMNS).astype(object)


ADD_3 = {
    "asset_id": "IA-3",
    "movement_type": "ADDITION",
    "movement_date": date(2024, 2, 3),
    "amount": 900.0,
    "asset_name": "New",
    "category": "Software licences",
    "useful_life_months": 36,
    "cost_centre": "CC-300",
}


def test_master_combines_register_and_additions_with_disposals() -> None:
    mv = _movements(
        [
            ADD_3,
            {"asset_id": "IA-1", "movement_type": "DISPOSAL", "movement_date": date(2024, 5, 2)},
        ]
    )
    m = build_asset_master(REGISTER, mv).set_index("asset_id")
    assert list(m.index) == ["IA-1", "IA-2", "IA-3"]
    assert m.loc["IA-1", "disposal_date"] == date(2024, 5, 2)
    assert m.loc["IA-3", "acquisition_date"] == date(2024, 2, 3)
    assert m.loc["IA-3", "source"] == "addition"


def test_asset_added_twice_is_rejected() -> None:
    with pytest.raises(MasterDataError, match="more than once"):
        build_asset_master(REGISTER, _movements([ADD_3, ADD_3]))


def test_addition_reusing_a_register_id_is_rejected() -> None:
    with pytest.raises(MasterDataError, match="more than once"):
        build_asset_master(REGISTER, _movements([{**ADD_3, "asset_id": "IA-1"}]))


def test_disposal_of_unknown_asset_is_rejected() -> None:
    mv = _movements(
        [{"asset_id": "IA-99", "movement_type": "DISPOSAL", "movement_date": date(2024, 1, 5)}]
    )
    with pytest.raises(MasterDataError, match="unknown asset"):
        build_asset_master(REGISTER, mv)


def test_disposal_of_already_disposed_asset_is_rejected() -> None:
    mv = _movements(
        [{"asset_id": "IA-2", "movement_type": "DISPOSAL", "movement_date": date(2024, 1, 5)}]
    )
    with pytest.raises(MasterDataError, match="already disposed"):
        build_asset_master(REGISTER, mv)


def test_double_disposal_is_rejected() -> None:
    d = {"asset_id": "IA-1", "movement_type": "DISPOSAL", "movement_date": date(2024, 1, 5)}
    with pytest.raises(MasterDataError, match="more than once"):
        build_asset_master(REGISTER, _movements([d, d]))


def test_disposal_before_acquisition_is_rejected() -> None:
    mv = _movements(
        [
            ADD_3,
            {"asset_id": "IA-3", "movement_type": "DISPOSAL", "movement_date": date(2024, 1, 5)},
        ]
    )
    with pytest.raises(MasterDataError, match="before acquisition"):
        build_asset_master(REGISTER, mv)


def test_addition_without_cost_is_rejected() -> None:
    with pytest.raises(MasterDataError, match="without cost"):
        build_asset_master(REGISTER, _movements([{**ADD_3, "amount": None}]))


def test_later_transfer_in_same_month_wins() -> None:
    mv = _movements(
        [
            {
                "asset_id": "IA-1",
                "movement_type": "TRANSFER",
                "movement_date": date(2024, 3, 20),
                "cost_centre": "CC-600",
            },
            {
                "asset_id": "IA-1",
                "movement_type": "TRANSFER",
                "movement_date": date(2024, 3, 5),
                "cost_centre": "CC-400",
            },
        ]
    )
    master = build_asset_master(REGISTER, mv)
    trf = build_transfers(mv, master)
    assert len(trf) == 1
    assert trf.loc[0, "cost_centre"] == "CC-600"


def test_transfer_of_unknown_asset_is_rejected() -> None:
    mv = _movements(
        [
            {
                "asset_id": "IA-77",
                "movement_type": "TRANSFER",
                "movement_date": date(2024, 3, 5),
                "cost_centre": "CC-400",
            }
        ]
    )
    with pytest.raises(MasterDataError, match="unknown asset"):
        build_transfers(mv, build_asset_master(REGISTER, _movements([])))


def test_generated_master_has_400_assets(model: ModelResult) -> None:
    assert len(model.master) == 400
    assert model.master["asset_id"].is_unique
    assert (model.master["source"] == "addition").sum() == 80
