// Query name: AssetMonthGrid
// Load as: connection only
//
// One row per asset per reporting month in which the asset is on the books:
// acquired on or before the month end AND not disposed before the month start.
// The disposal month is kept (it carries the disposal); later months are not.
// Each row gets the cost centre valid in that month (latest transfer so far).
// Python twin: depreciation_model.schedule.build_schedule (grid part)
let
    WithMonths = Table.AddColumn(AssetMaster, "months", each ReportMonths, Value.Type(ReportMonths)),
    CrossJoin = Table.ExpandTableColumn(WithMonths, "months", {"month_start", "month_index", "month_end"}),
    OnBooks = Table.SelectRows(
        CrossJoin,
        each [acquisition_date] <= [month_end]
            and ([disposal_date] = null or [disposal_date] >= [month_start])
    ),
    TransfersBuffered = Table.Buffer(Transfers),
    WithCostCentre = Table.AddColumn(
        OnBooks,
        "month_cost_centre",
        (r) =>
            let
                hits = Table.SelectRows(
                    TransfersBuffered,
                    each [asset_id] = r[asset_id] and [effective_month_index] <= r[month_index]
                )
            in
                if Table.IsEmpty(hits) then r[cost_centre]
                else Table.Max(hits, "effective_month_index")[cost_centre],
        type text
    ),
    Tidy = Table.RenameColumns(
        Table.RemoveColumns(WithCostCentre, {"cost_centre"}),
        {{"month_cost_centre", "cost_centre"}}
    )
in
    Tidy
