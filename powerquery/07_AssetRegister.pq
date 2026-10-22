// Query name: AssetRegister
// Load as: connection only
//
// Opening asset register as at the first reporting day (clean system extract).
// Python twin: depreciation_model.cleaning.load_register
let
    IsoDate = (t as nullable text) as nullable date =>
        if t = null or Text.Trim(t) = "" then null
        else
            let p = Text.Split(Text.Trim(t), "-") in
                #date(Number.FromText(p{0}), Number.FromText(p{1}), Number.FromText(p{2})),
    Source = Csv.Document(
        File.Contents(pSourceFolder & "asset_register.csv"),
        [Delimiter = ",", Encoding = 65001, QuoteStyle = QuoteStyle.Csv]
    ),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumns(
        Promoted,
        {
            {"asset_id", each Text.Upper(Text.Trim(_)), type text},
            {"asset_name", Text.Trim, type text},
            {"category", Text.Trim, type text},
            {"cost_centre", Text.Trim, type text},
            {"acquisition_date", IsoDate, type date},
            {"cost", each Number.FromText(Text.Trim(_), "en-US"), type number},
            {"useful_life_months", each Int64.From(Text.Trim(_)), Int64.Type},
            {"disposal_date", IsoDate, type nullable date}
        }
    ),
    Selected = Table.SelectColumns(
        Typed,
        {
            "asset_id", "asset_name", "category", "cost_centre",
            "acquisition_date", "cost", "useful_life_months", "disposal_date"
        }
    )
in
    Selected
