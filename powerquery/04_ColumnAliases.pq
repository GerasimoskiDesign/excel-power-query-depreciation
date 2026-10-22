// Query name: ColumnAliases
// Load as: connection only
//
// Every header spelling seen in the monthly movement exports, mapped to one
// canonical column name. Keys are lower case with surrounding spaces removed.
// When a new month arrives with a new spelling, add ONE row here (and to
// COLUMN_ALIASES in src/depreciation_model/config.py - a test keeps them equal).
// Unknown headers stop the refresh on purpose: silently dropping a column is
// how a disposal gets lost.
let
    Aliases = #table(
        type table [alias = text, canonical = text],
        {
            {"asset_id", "asset_id"},
            {"asset id", "asset_id"},
            {"assetno", "asset_id"},
            {"asset no", "asset_id"},
            {"movement_type", "movement_type"},
            {"type", "movement_type"},
            {"movement", "movement_type"},
            {"movement_date", "movement_date"},
            {"date", "movement_date"},
            {"posting date", "movement_date"},
            {"amount", "amount"},
            {"amount (eur)", "amount"},
            {"value", "amount"},
            {"asset_name", "asset_name"},
            {"asset description", "asset_name"},
            {"description", "asset_name"},
            {"category", "category"},
            {"asset class", "category"},
            {"useful_life_months", "useful_life_months"},
            {"useful life (months)", "useful_life_months"},
            {"life months", "useful_life_months"},
            {"cost_centre", "cost_centre"},
            {"cost center", "cost_centre"},
            {"cc", "cost_centre"}
        }
    )
in
    Aliases
