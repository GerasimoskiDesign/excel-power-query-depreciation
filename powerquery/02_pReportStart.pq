// Query name: pReportStart
// Load as: connection only
//
// First reporting month (named range ReportStart). Any day in the month is
// accepted and normalised to the first day of that month.
let
    Raw = Excel.CurrentWorkbook(){[Name = "ReportStart"]}[Content]{0}[Column1],
    MonthStart = Date.StartOfMonth(Date.From(Raw))
in
    MonthStart
