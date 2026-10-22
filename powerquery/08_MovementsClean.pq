// Query name: MovementsClean
// Load as: connection only (optionally to a sheet, to eyeball the cleaning)
//
// Load folder -> clean each file -> combine. One row per movement, all months.
// Python twin: depreciation_model.cleaning.load_movements
let
    Files = Folder.Files(pSourceFolder & "movements"),
    // Ignore anything that is not a CSV, and Excel lock files.
    CsvOnly = Table.SelectRows(
        Files,
        each Text.Lower([Extension]) = ".csv" and not Text.StartsWith([Name], "~")
    ),
    Sorted = Table.Sort(CsvOnly, {{"Name", Order.Ascending}}),
    Cleaned = Table.AddColumn(Sorted, "Clean", each fnCleanMovementFile([Content], [Name])),
    Combined = Table.Combine(Cleaned[Clean])
in
    Combined
