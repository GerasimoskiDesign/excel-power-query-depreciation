// Query name: pSourceFolder
// Load as: connection only
//
// Full path of the folder that contains asset_register.csv and movements\.
// It is read from the named range SourceFolder on the Parameters sheet, so
// pointing the model at another folder never requires the Advanced Editor.
let
    Raw = Excel.CurrentWorkbook(){[Name = "SourceFolder"]}[Content]{0}[Column1],
    Trimmed = Text.Trim(Text.From(Raw)),
    // Accept the path with or without a trailing backslash.
    WithSlash = if Text.EndsWith(Trimmed, "\") then Trimmed else Trimmed & "\"
in
    WithSlash
