"""Asset-month grid and straight-line depreciation (the core of the model).

Convention (full write-up in docs/CONVENTIONS.md):

* Monthly charge = cost / useful life in months.
* Depreciation runs from the acquisition date (inclusive) to the disposal
  date (exclusive), pro-rated by days within the first and the disposal month.
* Every month in between earns a full monthly charge, regardless of its length.
* Accumulated depreciation is capped at cost, so the day-based remainder of
  the first month is charged in month ``life + 1`` and an asset then stays at
  zero net book value until it is disposed.

Accumulated depreciation is computed in *closed form* from the number of
"service months" elapsed, instead of as a running sum. That is what lets
Power Query compute every row independently (no slow running totals), and it
makes Python and M agree to floating-point precision.
"""

from __future__ import annotations

import logging
from bisect import bisect_right
from datetime import date

import pandas as pd

from depreciation_model.dates import days_in_month, month_end, month_index

log = logging.getLogger(__name__)

AMOUNT_COLUMNS = [
    "opening_cost",
    "additions",
    "disposals_cost",
    "closing_cost",
    "opening_acc_dep",
    "depreciation",
    "disposal_acc_dep",
    "closing_acc_dep",
    "closing_nbv",
    "disposal_nbv",
]

SCHEDULE_COLUMNS = [
    "month_start",
    "month_index",
    "asset_id",
    "category",
    "cost_centre",
    *AMOUNT_COLUMNS,
]


def service_months(acquired: date, disposed: date | None, k: int) -> float:
    """Months of service from acquisition up to the end of month index ``k``.

    The first month counts the days from the acquisition day to month end;
    the disposal month counts the days before the disposal day; months in
    between count as 1.0 each.
    """
    a = month_index(acquired)
    if k < a:
        return 0.0
    dim_a = days_in_month(acquired)
    if disposed is not None and month_index(disposed) == a:
        return (disposed - acquired).days / dim_a
    first = (dim_a - acquired.day + 1) / dim_a
    last_full = k if disposed is None else min(k, month_index(disposed) - 1)
    full = max(0, last_full - a)
    tail = 0.0
    if disposed is not None and k >= month_index(disposed):
        tail = (disposed.day - 1) / days_in_month(disposed)
    return first + full + tail


def accumulated_depreciation(
    cost: float, life_months: int, acquired: date, disposed: date | None, k: int
) -> float:
    """Accumulated depreciation at the end of month ``k`` - never more than cost."""
    return min(cost, cost * service_months(acquired, disposed, k) / life_months)


def _cost_centre_lookup(transfers: pd.DataFrame) -> dict[str, tuple[list[int], list[str]]]:
    lookup: dict[str, tuple[list[int], list[str]]] = {}
    for asset_id, grp in transfers.sort_values("effective_month_index").groupby("asset_id"):
        lookup[str(asset_id)] = (
            grp["effective_month_index"].tolist(),
            grp["cost_centre"].tolist(),
        )
    return lookup


def build_schedule(
    master: pd.DataFrame, transfers: pd.DataFrame, months: list[date]
) -> pd.DataFrame:
    """One row per asset per reporting month in which the asset is on the books.

    An asset is on the books in a month if it was acquired on or before the
    month end and not disposed before the month start. The disposal month is
    kept (it carries the disposal), every later month is dropped.
    """
    cc_lookup = _cost_centre_lookup(transfers)
    rows = []
    for m in months:
        k = month_index(m)
        m_end = month_end(m)
        for a in master.itertuples(index=False):
            acq: date = a.acquisition_date
            disp: date | None = a.disposal_date
            if acq > m_end or (disp is not None and disp < m):
                continue
            cost = float(a.cost)
            life = int(a.useful_life_months)
            acc_prev = accumulated_depreciation(cost, life, acq, disp, k - 1)
            acc_now = accumulated_depreciation(cost, life, acq, disp, k)
            acquired_now = month_index(acq) == k
            disposed_now = disp is not None and month_index(disp) == k

            opening_cost = 0.0 if acquired_now else cost
            additions = cost if acquired_now else 0.0
            disposals_cost = cost if disposed_now else 0.0
            opening_acc = 0.0 if acquired_now else acc_prev
            depreciation = acc_now - acc_prev
            disposal_acc = acc_now if disposed_now else 0.0
            closing_cost = opening_cost + additions - disposals_cost
            closing_acc = opening_acc + depreciation - disposal_acc

            cost_centre = a.cost_centre
            if a.asset_id in cc_lookup:
                ks, ccs = cc_lookup[a.asset_id]
                pos = bisect_right(ks, k)
                if pos:
                    cost_centre = ccs[pos - 1]

            rows.append(
                {
                    "month_start": m,
                    "month_index": k,
                    "asset_id": a.asset_id,
                    "category": a.category,
                    "cost_centre": cost_centre,
                    "opening_cost": opening_cost,
                    "additions": additions,
                    "disposals_cost": disposals_cost,
                    "closing_cost": closing_cost,
                    "opening_acc_dep": opening_acc,
                    "depreciation": depreciation,
                    "disposal_acc_dep": disposal_acc,
                    "closing_acc_dep": closing_acc,
                    "closing_nbv": closing_cost - closing_acc,
                    "disposal_nbv": cost - acc_now if disposed_now else 0.0,
                }
            )
    schedule = pd.DataFrame(rows, columns=SCHEDULE_COLUMNS)
    log.info(
        "Schedule: %d asset-month rows, %s to %s",
        len(schedule),
        months[0].isoformat(),
        months[-1].isoformat(),
    )
    return schedule
