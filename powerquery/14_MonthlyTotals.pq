// Query name: MonthlyTotals
// Load as: TABLE on sheet PQ_MonthlyTotals, cell A1 (the Check sheet reads it)
//
// Totals per month. Column ORDER matters: the Check sheet compares column by
// column with Expected_MonthlyTotals and also verifies the header names.
// Python twin: depreciation_model.reporting.monthly_totals
let
    AmountColumns = {
        "opening_cost", "additions", "disposals_cost", "closing_cost", "opening_acc_dep",
        "depreciation", "disposal_acc_dep", "closing_acc_dep", "closing_nbv", "disposal_nbv"
    },
    Grouped = Table.Group(
        Depreciation,
        {"month_start"},
        {{"asset_rows", Table.RowCount, Int64.Type}}
            & List.Transform(
                AmountColumns,
                (c) => {c, each List.Sum(Table.Column(_, c)), type number}
            )
    ),
    Sorted = Table.Sort(Grouped, {{"month_start", Order.Ascending}}),
    // Round only at the very end (row-level rounding would drift from the reference).
    Rounded = Table.TransformColumns(
        Sorted,
        List.Transform(AmountColumns, (c) => {c, each Number.Round(_, 2), type number})
    ),
    Result = Table.SelectColumns(Rounded, {"month_start", "asset_rows"} & AmountColumns)
in
    Result
