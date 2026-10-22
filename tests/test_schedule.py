"""Hand-checked depreciation cases: pro-rata convention, disposals, full depreciation."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from depreciation_model.dates import report_months
from depreciation_model.schedule import (
    accumulated_depreciation,
    build_schedule,
    service_months,
)
from tests.conftest import NO_TRANSFERS, make_master

MONTHS_2024 = report_months(date(2024, 1, 1), 12)


def _schedule(rows: list[dict], months: list[date] = MONTHS_2024) -> pd.DataFrame:
    return build_schedule(make_master(rows), NO_TRANSFERS, months).set_index("month_start")


# --- pro-rata first month ---------------------------------------------------------------


def test_first_month_is_pro_rata_by_days_including_acquisition_day() -> None:
    # 3,100 over 10 months = 310 / month. Acquired 17 Jan: 15 of 31 days -> 150.00.
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 3100,
                "useful_life_months": 10,
                "acquisition_date": date(2024, 1, 17),
            }
        ]
    )
    assert s.loc[date(2024, 1, 1), "depreciation"] == pytest.approx(150.0)
    assert s.loc[date(2024, 2, 1), "depreciation"] == pytest.approx(310.0)


def test_remainder_of_first_month_is_charged_in_month_life_plus_one() -> None:
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 3100,
                "useful_life_months": 10,
                "acquisition_date": date(2024, 1, 17),
            }
        ]
    )
    # Jan 150 + Feb..Oct 9 x 310 = 2,940; Nov gets the remaining 160 (= 310 x 16/31).
    assert s.loc[date(2024, 10, 1), "closing_acc_dep"] == pytest.approx(2940.0)
    assert s.loc[date(2024, 11, 1), "depreciation"] == pytest.approx(160.0)
    assert s.loc[date(2024, 12, 1), "depreciation"] == pytest.approx(0.0)
    assert s["depreciation"].sum() == pytest.approx(3100.0)


def test_acquired_on_first_day_gets_full_month_and_ends_after_exactly_life_months() -> None:
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 1200,
                "useful_life_months": 6,
                "acquisition_date": date(2024, 3, 1),
            }
        ]
    )
    assert s.loc[date(2024, 3, 1), "depreciation"] == pytest.approx(200.0)
    assert s.loc[date(2024, 8, 1), "closing_nbv"] == pytest.approx(0.0)
    assert s.loc[date(2024, 9, 1), "depreciation"] == pytest.approx(0.0)


def test_leap_february_uses_29_days() -> None:
    # Acquired on the last day of Feb 2024: 1 of 29 days.
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 2900,
                "useful_life_months": 10,
                "acquisition_date": date(2024, 2, 29),
            }
        ]
    )
    assert s.loc[date(2024, 2, 1), "depreciation"] == pytest.approx(290.0 / 29)


def test_acquisition_month_row_shows_addition_not_opening_balance() -> None:
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 1000,
                "useful_life_months": 10,
                "acquisition_date": date(2024, 5, 10),
            }
        ]
    )
    may = s.loc[date(2024, 5, 1)]
    assert (may["opening_cost"], may["additions"], may["closing_cost"]) == (0.0, 1000.0, 1000.0)
    assert date(2024, 4, 1) not in s.index  # no rows before acquisition


# --- disposals --------------------------------------------------------------------------


def test_disposal_stops_depreciation_and_derecognises_the_asset() -> None:
    # 2,400 over 24 months = 100 / month, acquired 1 Jan 2023 -> 1,400 by end of Feb 2024.
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 2400,
                "useful_life_months": 24,
                "acquisition_date": date(2023, 1, 1),
                "disposal_date": date(2024, 3, 16),
            }
        ]
    )
    march = s.loc[date(2024, 3, 1)]
    # 15 of 31 days held in March (1-15); the disposal day itself is not charged.
    assert march["depreciation"] == pytest.approx(100 * 15 / 31)
    assert march["disposals_cost"] == pytest.approx(2400.0)
    assert march["disposal_acc_dep"] == pytest.approx(1400 + 100 * 15 / 31)
    assert march["disposal_nbv"] == pytest.approx(1000 - 100 * 15 / 31)
    assert march["closing_cost"] == march["closing_acc_dep"] == march["closing_nbv"] == 0.0
    assert s.index.max() == date(2024, 3, 1)  # nothing after the disposal month


def test_disposal_on_first_day_of_month_charges_nothing_that_month() -> None:
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 2400,
                "useful_life_months": 24,
                "acquisition_date": date(2023, 6, 1),
                "disposal_date": date(2024, 4, 1),
            }
        ]
    )
    assert s.loc[date(2024, 4, 1), "depreciation"] == 0.0
    assert s.loc[date(2024, 4, 1), "disposals_cost"] == 2400.0


def test_acquired_and_disposed_in_the_same_month() -> None:
    # 10 Jun to 20 Jun = 10 of 30 days. 3,000 / 10 months = 300 / month -> 100.
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 3000,
                "useful_life_months": 10,
                "acquisition_date": date(2024, 6, 10),
                "disposal_date": date(2024, 6, 20),
            }
        ]
    )
    june = s.loc[date(2024, 6, 1)]
    assert june["depreciation"] == pytest.approx(100.0)
    assert june["additions"] == june["disposals_cost"] == 3000.0
    assert june["closing_nbv"] == 0.0
    assert len(s) == 1


def test_asset_disposed_before_the_window_produces_no_rows() -> None:
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 500,
                "useful_life_months": 12,
                "acquisition_date": date(2020, 1, 1),
                "disposal_date": date(2023, 12, 31),
            }
        ]
    )
    assert s.empty


# --- fully depreciated assets -----------------------------------------------------------


def test_fully_depreciated_asset_stays_at_zero_nbv_until_disposal() -> None:
    s = _schedule(
        [
            {
                "asset_id": "A",
                "cost": 3600,
                "useful_life_months": 36,
                "acquisition_date": date(2016, 5, 20),
                "disposal_date": date(2024, 9, 5),
            }
        ]
    )
    on_books = s[s.index < date(2024, 9, 1)]
    assert (on_books["depreciation"] == 0).all()
    assert (on_books["closing_nbv"] == 0).all()
    assert (on_books["closing_acc_dep"] == 3600).all()
    sept = s.loc[date(2024, 9, 1)]
    assert sept["depreciation"] == 0.0
    assert sept["disposal_nbv"] == 0.0


def test_accumulated_depreciation_never_exceeds_cost() -> None:
    for k_offset in range(0, 200):
        acc = accumulated_depreciation(1000.0, 36, date(2020, 1, 15), None, 24240 + k_offset)
        assert acc <= 1000.0


def test_service_months_closed_form() -> None:
    acq = date(2024, 1, 17)  # index 24288
    assert service_months(acq, None, 24287) == 0.0
    assert service_months(acq, None, 24288) == pytest.approx(15 / 31)
    assert service_months(acq, None, 24290) == pytest.approx(15 / 31 + 2)
    # disposed 11 Apr: Jan part + Feb + Mar + 10/30 of April, frozen afterwards
    disp = date(2024, 4, 11)
    assert service_months(acq, disp, 24291) == pytest.approx(15 / 31 + 2 + 10 / 30)
    assert service_months(acq, disp, 24300) == service_months(acq, disp, 24291)


# --- cost-centre transfers --------------------------------------------------------------


def test_transfer_moves_whole_month_to_new_cost_centre() -> None:
    master = make_master(
        [
            {
                "asset_id": "A",
                "cost": 1200,
                "useful_life_months": 12,
                "acquisition_date": date(2023, 12, 1),
            }
        ]
    )
    transfers = pd.DataFrame(
        [
            {"asset_id": "A", "effective_month_index": 2024 * 12 + 3 - 1, "cost_centre": "CC-300"},
            {"asset_id": "A", "effective_month_index": 2024 * 12 + 7 - 1, "cost_centre": "CC-500"},
        ]
    )
    s = build_schedule(master, transfers, MONTHS_2024).set_index("month_start")
    assert s.loc[date(2024, 2, 1), "cost_centre"] == "CC-100"
    assert s.loc[date(2024, 3, 1), "cost_centre"] == "CC-300"
    assert s.loc[date(2024, 6, 1), "cost_centre"] == "CC-300"
    assert s.loc[date(2024, 7, 1), "cost_centre"] == "CC-500"
