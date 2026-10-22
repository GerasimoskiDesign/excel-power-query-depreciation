// Query name: ReportMonths
// Load as: connection only
//
// The reporting months as a table: first day, last day and an integer month
// index (year * 12 + month - 1) that turns "months between" into a subtraction.
let
    Months = List.Transform({0 .. pReportMonths - 1}, each Date.AddMonths(pReportStart, _)),
    AsTable = Table.FromList(Months, Splitter.SplitByNothing(), type table [month_start = date]),
    WithIndex = Table.AddColumn(
        AsTable,
        "month_index",
        each Date.Year([month_start]) * 12 + Date.Month([month_start]) - 1,
        Int64.Type
    ),
    WithEnd = Table.AddColumn(WithIndex, "month_end", each Date.EndOfMonth([month_start]), type date)
in
    WithEnd
