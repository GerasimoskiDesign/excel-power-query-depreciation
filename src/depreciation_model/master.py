"""Asset master: opening register + additions, with disposals and cost-centre transfers.

Mirrors ``07_AssetRegister.pq`` .. ``10_Transfers.pq``. Validation lives here
because these are the joins where hand-built workbooks usually go wrong: an
asset added twice, a disposal for an asset that does not exist, or a disposal
dated before the acquisition.
"""

from __future__ import annotations

import logging

import pandas as pd

from depreciation_model.dates import month_index

log = logging.getLogger(__name__)

MASTER_COLUMNS = [
    "asset_id",
    "asset_name",
    "category",
    "cost_centre",
    "acquisition_date",
    "cost",
    "useful_life_months",
    "disposal_date",
    "source",
]


class MasterDataError(ValueError):
    """Register and movements contradict each other."""


def build_asset_master(register: pd.DataFrame, movements: pd.DataFrame) -> pd.DataFrame:
    """One row per asset ever on the books, with its (possible) disposal date.

    ``cost_centre`` here is the cost centre at acquisition or at the start of
    the window; month-by-month changes come from :func:`build_transfers`.
    """
    reg = register.copy()
    reg["source"] = "register"

    adds = movements[movements["movement_type"] == "ADDITION"]
    additions = pd.DataFrame(
        {
            "asset_id": adds["asset_id"],
            "asset_name": adds["asset_name"],
            "category": adds["category"],
            "cost_centre": adds["cost_centre"],
            "acquisition_date": adds["movement_date"],
            "cost": adds["amount"],
            "useful_life_months": adds["useful_life_months"],
            "disposal_date": None,
            "source": "addition",
        }
    )
    master = pd.concat([reg, additions], ignore_index=True)[MASTER_COLUMNS]

    dupes = master["asset_id"][master["asset_id"].duplicated()]
    if not dupes.empty:
        raise MasterDataError(f"Asset added more than once: {sorted(set(dupes))}")
    bad = master[(master["cost"].isna()) | (master["useful_life_months"].isna())]
    if not bad.empty:
        raise MasterDataError(f"Additions without cost or useful life: {list(bad['asset_id'])}")

    disposals = movements[movements["movement_type"] == "DISPOSAL"]
    if disposals["asset_id"].duplicated().any():
        raise MasterDataError("An asset is disposed more than once")
    known = set(master["asset_id"])
    unknown = sorted(set(disposals["asset_id"]) - known)
    if unknown:
        raise MasterDataError(f"Disposal of unknown asset(s): {unknown}")

    disp_map = dict(zip(disposals["asset_id"], disposals["movement_date"], strict=True))
    for idx, asset_id in master["asset_id"].items():
        if asset_id not in disp_map:
            continue
        if master.at[idx, "disposal_date"] is not None:
            raise MasterDataError(f"{asset_id} was already disposed in the register")
        master.at[idx, "disposal_date"] = disp_map[asset_id]

    early = master[
        master.apply(
            lambda r: r["disposal_date"] is not None and r["disposal_date"] < r["acquisition_date"],
            axis=1,
        )
    ]
    if not early.empty:
        raise MasterDataError(f"Disposal before acquisition: {list(early['asset_id'])}")

    master["cost"] = master["cost"].astype(float)
    master["useful_life_months"] = master["useful_life_months"].astype(int)
    log.info(
        "Asset master: %d assets (%d disposed)", len(master), master["disposal_date"].notna().sum()
    )
    return master.sort_values("asset_id").reset_index(drop=True)


def build_transfers(movements: pd.DataFrame, master: pd.DataFrame) -> pd.DataFrame:
    """Cost-centre changes, effective for the whole month in which they are posted.

    If an asset is transferred twice in one month, the later posting wins
    (ties keep file order). Columns: asset_id, effective_month_index, cost_centre.
    """
    trf = movements[movements["movement_type"] == "TRANSFER"].copy()
    unknown = sorted(set(trf["asset_id"]) - set(master["asset_id"]))
    if unknown:
        raise MasterDataError(f"Transfer of unknown asset(s): {unknown}")
    if trf["cost_centre"].isna().any():
        raise MasterDataError("Transfer without a target cost centre")
    trf["effective_month_index"] = trf["movement_date"].map(month_index)
    trf["_order"] = range(len(trf))
    trf = trf.sort_values(["asset_id", "movement_date", "_order"])
    trf = trf.drop_duplicates(["asset_id", "effective_month_index"], keep="last")
    return trf[["asset_id", "effective_month_index", "cost_centre"]].reset_index(drop=True)
