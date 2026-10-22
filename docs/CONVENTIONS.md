# Depreciation conventions

These are the rules used by both engines: the Power Query scripts in
`powerquery/` and the Python reference implementation in `src/depreciation_model/`.
Where the two differ, that is a bug. The Excel `Check` sheet and the pytest suite
are there to catch it.

## 1. Straight-line, monthly

```
monthly charge = cost / useful_life_months
```

There is no residual value; intangible assets are written down to zero.

## 2. Pro-rata by days in the first month

Depreciation starts **on the acquisition date, inclusive**. In the acquisition month
the charge is the monthly charge times the share of the month's days the asset was held:

```
first-month fraction = (days in month - acquisition day + 1) / days in month
```

Example: cost 3,100, life 10 months, acquired 17 January 2024.
Monthly charge 310. January holds 15 of 31 days, so January = 310 x 15/31 = **150.00**.

Every following month is a full charge, whatever its length (February counts the
same as March).

## 3. The tail month

Accumulated depreciation is **capped at cost**. Because the first month was
partial, the asset is not fully depreciated after `useful_life_months` months. The
remaining amount (the days not charged in the first month) is charged in month
`useful_life_months + 1`.

Example above: January 150 + February to October 9 x 310 = 2,940; November gets
the remaining **160.00** (= 310 x 16/31). Total = 3,100.

An asset acquired on the 1st of a month is fully depreciated after exactly
`useful_life_months` months.

## 4. Disposals stop depreciation

Depreciation runs **up to, but not including, the disposal date**. In the disposal month:

```
disposal-month fraction = (disposal day - 1) / days in month
```

In the same month the asset is derecognised:

| column             | disposal month value                          |
|--------------------|-----------------------------------------------|
| `disposals_cost`   | cost                                          |
| `disposal_acc_dep` | accumulated depreciation at disposal          |
| `disposal_nbv`     | cost minus that = NBV written off             |
| `closing_*`        | 0                                             |

There are no rows for that asset in any later month. An asset disposed on the 1st of a
month gets no charge in that month. Acquired and disposed in the same month:
`(disposal day - acquisition day) / days in month` of one monthly charge.

## 5. Fully depreciated assets

When accumulated depreciation reaches cost, the asset stays in the register
with NBV 0 and a depreciation charge of 0 until it is disposed. It still counts in
gross cost and accumulated depreciation. This is how a fixed-asset register reports,
and it is why gross cost is much higher than NBV in the synthetic results.

## 6. Cost-centre transfers

A transfer is effective for the **whole month** in which it is posted: that month's
depreciation and balances go to the new cost centre. Transfers never change
amounts. If an asset is transferred twice in one month, the later posting wins.

## 7. Closed-form calculation (why there is no running total)

Both engines compute accumulated depreciation at the end of month `k` directly:

```
service_months(k) = first-month fraction
                  + number of full months after the acquisition month up to k
                    (stopping before the disposal month)
                  + disposal-month fraction (once k reaches the disposal month)

acc_dep(k)        = min(cost, cost * service_months(k) / useful_life_months)
depreciation(k)   = acc_dep(k) - acc_dep(k - 1)
```

Each asset-month row can therefore be computed on its own. In Power Query this
avoids running totals (which are slow and depend on sort order), and Python and M
produce the same floating-point result because they evaluate the same expression.

Months are compared using an integer *month index* `year * 12 + month - 1`, so
"number of months between" is a subtraction in both languages.

## 8. Rounding

Amounts are kept unrounded through the whole calculation and rounded to cents only
in outputs (CSV files and the `MonthlyTotals` query). If you rounded each row first,
the monthly totals would drift by a few cents from the other engine. The Check sheet
allows a difference of 0.01 per value.

## 9. Source-file assumptions

* Monthly movement files are CSV, comma-delimited, UTF-8 (with or without BOM).
* Numbers use `.` as the decimal mark; `,` and spaces are thousands separators.
* Dates are either ISO `YYYY-MM-DD` or day-first `DD/MM/YYYY` (never month-first).
* An unknown column header, missing column or unknown movement type **stops the
  refresh** with a message naming the file. It is never silently skipped.
