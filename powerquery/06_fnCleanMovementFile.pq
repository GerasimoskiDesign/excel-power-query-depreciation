// Query name: fnCleanMovementFile
// Load as: connection only (it is a function)
//
// Turns ONE raw monthly movement export into the canonical movement table.
// Python twin: depreciation_model.cleaning.clean_movement_file
//
// Mess it handles (all of it appears in source_files/movements/):
//   * blank rows above the header, between data rows and at the end
//   * a UTF-8 byte-order mark in front of the first cell
//   * renamed and re-ordered columns          -> ColumnAliases
//   * numbers as text: "1,234.50 ", " 36"      -> ParseNumber
//   * ISO and day-first dates                  -> ParseDate
//   * lower-case / padded asset ids and types  -> Text.Upper / MovementTypeAliases
(content as binary, sourceFile as text) as table =>
let
    Bom = Character.FromNumber(65279),
    CleanText = (v as any) as text =>
        if v = null then "" else Text.Trim(Text.Remove(Text.From(v), {Bom})),
    IsBlankRow = (r as record) as logical =>
        List.AllTrue(List.Transform(Record.FieldValues(r), each CleanText(_) = "")),
    BlankToNull = (v as any) as nullable text =>
        let t = CleanText(v) in if t = "" then null else t,
    // Thousands separators and spaces are removed; the decimal mark is always "."
    ParseNumber = (v as any) as nullable number =>
        let t = Text.Remove(CleanText(v), {",", " "}) in
            if t = "" then null else Number.FromText(t, "en-US"),
    // Built by hand from the parts so the result never depends on the PC's locale.
    ParseDate = (v as any) as nullable date =>
        let t = CleanText(v) in
            if t = "" then null
            else if Text.Contains(t, "/") then
                let p = Text.Split(t, "/") in
                    #date(Number.FromText(p{2}), Number.FromText(p{1}), Number.FromText(p{0}))
            else
                let p = Text.Split(Text.Start(t, 10), "-") in
                    #date(Number.FromText(p{0}), Number.FromText(p{1}), Number.FromText(p{2})),
    MapType = (v as any) as text =>
        let
            key = Text.Lower(CleanText(v)),
            match = Table.SelectRows(MovementTypeAliases, each [alias] = key)
        in
            if Table.RowCount(match) = 1 then match{0}[canonical]
            else error Error.Record("UnknownMovementType", sourceFile & ": unknown movement type '" & key & "'"),
    Required = {
        "asset_id", "movement_type", "movement_date", "amount",
        "asset_name", "category", "useful_life_months", "cost_centre"
    },

    // 1. Read every cell as text. Columns = 30 so a short first line can never
    //    make Power Query guess too few columns.
    Raw = Csv.Document(
        content,
        [Delimiter = ",", Columns = 30, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    // 2. Skip blank rows above the header.
    NoLeadingBlanks = Table.Skip(Raw, each IsBlankRow(_)),
    // 3. Map the header row to canonical names (empty header cells are ignored).
    HeaderKeys = List.Transform(
        Record.FieldValues(NoLeadingBlanks{0}),
        each Text.Lower(CleanText(_))
    ),
    Canonical = List.Transform(
        HeaderKeys,
        (h) =>
            let match = Table.SelectRows(ColumnAliases, each [alias] = h) in
                if h = "" then null
                else if Table.RowCount(match) = 1 then match{0}[canonical]
                else error Error.Record("UnknownColumn", sourceFile & ": unknown column header '" & h & "'")
    ),
    Renames = List.RemoveNulls(
        List.Transform(
            List.Positions(Canonical),
            each if Canonical{_} = null then null else {Table.ColumnNames(Raw){_}, Canonical{_}}
        )
    ),
    Mapped = List.RemoveNulls(Canonical),
    Missing = List.Difference(Required, Mapped),
    Duplicated = List.Count(Mapped) <> List.Count(List.Distinct(Mapped)),
    // 4. Body = everything below the header, without blank rows anywhere.
    Body = Table.SelectRows(Table.Skip(NoLeadingBlanks, 1), each not IsBlankRow(_)),
    Renamed =
        if not List.IsEmpty(Missing) then
            error Error.Record("MissingColumns", sourceFile & ": missing columns " & Text.Combine(Missing, ", "))
        else if Duplicated then
            error Error.Record("DuplicateColumns", sourceFile & ": two headers map to the same column")
        else
            Table.RenameColumns(Body, Renames),
    Selected = Table.SelectColumns(Renamed, Required),
    // 5. Standardise values and set types.
    Standardised = Table.FromRecords(
        Table.TransformRows(
            Selected,
            (r) => [
                asset_id = Text.Upper(CleanText(r[asset_id])),
                movement_type = MapType(r[movement_type]),
                movement_date = ParseDate(r[movement_date]),
                amount = ParseNumber(r[amount]),
                asset_name = BlankToNull(r[asset_name]),
                category = BlankToNull(r[category]),
                useful_life_months = ParseNumber(r[useful_life_months]),
                cost_centre = BlankToNull(r[cost_centre]),
                source_file = sourceFile
            ]
        ),
        type table [
            asset_id = text,
            movement_type = text,
            movement_date = date,
            amount = nullable number,
            asset_name = nullable text,
            category = nullable text,
            useful_life_months = nullable Int64.Type,
            cost_centre = nullable text,
            source_file = text
        ]
    )
in
    Standardised
