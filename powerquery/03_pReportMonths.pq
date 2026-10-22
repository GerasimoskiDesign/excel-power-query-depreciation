// Query name: pReportMonths
// Load as: connection only
//
// Number of reporting months (named range ReportMonths), e.g. 24.
let
    Raw = Excel.CurrentWorkbook(){[Name = "ReportMonths"]}[Content]{0}[Column1],
    Months = Number.RoundDown(Number.From(Raw))
in
    Months
