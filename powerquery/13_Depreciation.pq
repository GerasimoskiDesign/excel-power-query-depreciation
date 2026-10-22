// Query name: Depreciation
// Load as: connection only (or to a sheet / the Data Model for analysis)
//
// Monthly straight-line depreciation per asset-month, with the full roll-forward:
//   closing_cost    = opening_cost + additions - disposals_cost
//   closing_acc_dep = opening_acc_dep + depreciation - disposal_acc_dep
//   closing_nbv     = closing_cost - closing_acc_dep
// Python twin: depreciation_model.schedule (service_months / build_schedule)
//
// CONVENTION (docs/CONVENTIONS.md):
//   * monthly charge = cost / useful_life_months
//   * first month pro-rata by days: (days in month - acquisition day + 1) / days in month
//   * disposal month pro-rata by days held: (disposal day - 1) / days in month
//   * full months in between count 1.0 each
//   * accumulated depreciation is capped at cost -> fully depreciated assets stay at NBV 0
//
// Accumulated depreciation is computed in closed form from "service months",
// so every row is independent: no running totals, no sort-order dependence.
let
    MonthIdx = (d as date) as number => Date.Year(d) * 12 + Date.Month(d) - 1,

    // Months of service from acquisition up to the END of month index k.
    ServiceMonths = (acquired as date, disposed as nullable date, k as number) as number =>
        let
            a = MonthIdx(acquired),
            dimA = Date.DaysInMonth(acquired),
            sameMonth = disposed <> null and MonthIdx(disposed) = a,
            first = (dimA - Date.Day(acquired) + 1) / dimA,
            lastFull = if disposed = null then k else List.Min({k, MonthIdx(disposed) - 1}),
            full = List.Max({0, lastFull - a}),
            tail =
                if disposed <> null and k >= MonthIdx(disposed) then
                    (Date.Day(disposed) - 1) / Date.DaysInMonth(disposed)
                else
                    0
        in
            if k < a then 0
            else if sameMonth then Duration.Days(disposed - acquired) / dimA
            else first + full + tail,

    // Accumulated depreciation at the end of month k - never more than cost.
    AccDep = (cost as number, life as number, acquired as date, disposed as nullable date, k as number) as number =>
        List.Min({cost, cost * ServiceMonths(acquired, disposed, k) / life}),

    WithAmounts = Table.AddColumn(
        AssetMonthGrid,
        "amounts",
        each
            let
                accPrev = AccDep([cost], [useful_life_months], [acquisition_date], [disposal_date], [month_index] - 1),
                accNow = AccDep([cost], [useful_life_months], [acquisition_date], [disposal_date], [month_index]),
                acquiredNow = MonthIdx([acquisition_date]) = [month_index],
                disposedNow = [disposal_date] <> null and MonthIdx([disposal_date]) = [month_index],
                openingCost = if acquiredNow then 0 else [cost],
                additionsAmt = if acquiredNow then [cost] else 0,
                disposalsCost = if disposedNow then [cost] else 0,
                openingAcc = if acquiredNow then 0 else accPrev,
                depreciationAmt = accNow - accPrev,
                disposalAcc = if disposedNow then accNow else 0,
                closingCost = openingCost + additionsAmt - disposalsCost,
                closingAcc = openingAcc + depreciationAmt - disposalAcc,
                disposalNbv = if disposedNow then [cost] - accNow else 0
            in
                // Field names differ from the let-variables on purpose: inside a record
                // literal, "x = x" would refer to the field itself (cyclic reference).
                [
                    opening_cost = openingCost,
                    additions = additionsAmt,
                    disposals_cost = disposalsCost,
                    closing_cost = closingCost,
                    opening_acc_dep = openingAcc,
                    depreciation = depreciationAmt,
                    disposal_acc_dep = disposalAcc,
                    closing_acc_dep = closingAcc,
                    closing_nbv = closingCost - closingAcc,
                    disposal_nbv = disposalNbv
                ]
    ),
    AmountColumns = {
        "opening_cost", "additions", "disposals_cost", "closing_cost", "opening_acc_dep",
        "depreciation", "disposal_acc_dep", "closing_acc_dep", "closing_nbv", "disposal_nbv"
    },
    Expanded = Table.ExpandRecordColumn(WithAmounts, "amounts", AmountColumns),
    Typed = Table.TransformColumnTypes(
        Expanded,
        List.Transform(AmountColumns, each {_, type number})
            & {{"month_start", type date}, {"month_index", Int64.Type}}
    ),
    Result = Table.SelectColumns(
        Typed,
        {"month_start", "month_index", "asset_id", "category", "cost_centre"} & AmountColumns
    )
in
    Result
