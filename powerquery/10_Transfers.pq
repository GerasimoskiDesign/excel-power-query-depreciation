// Query name: Transfers
// Load as: connection only
//
// Cost-centre transfers. Convention: a transfer is effective for the WHOLE month
// in which it is posted (the month's depreciation goes to the new cost centre).
// Two transfers of one asset in the same month: the later posting wins.
// Python twin: depreciation_model.master.build_transfers
let
    Source = Table.SelectRows(MovementsClean, each [movement_type] = "TRANSFER"),
    Indexed = Table.AddIndexColumn(Source, "file_order", 0, 1, Int64.Type),
    WithMonth = Table.AddColumn(
        Indexed,
        "effective_month_index",
        each Date.Year([movement_date]) * 12 + Date.Month([movement_date]) - 1,
        Int64.Type
    ),
    // Sort key: posting date first, file order as tie-breaker (no reliance on row order).
    WithKey = Table.AddColumn(
        WithMonth, "sort_key", each Number.From([movement_date]) * 100000 + [file_order], type number
    ),
    Latest = Table.Group(
        WithKey,
        {"asset_id", "effective_month_index"},
        {{"cost_centre", each Table.Max(_, "sort_key")[cost_centre], type text}}
    ),
    UnknownAssets = List.Difference(List.Distinct(Source[asset_id]), AssetMaster[asset_id]),
    MissingTarget = Table.SelectRows(Source, each [cost_centre] = null)[asset_id],
    Result =
        if not List.IsEmpty(UnknownAssets) then
            error Error.Record("MasterDataError", "Transfer of unknown asset(s): " & Text.Combine(UnknownAssets, ", "))
        else if not List.IsEmpty(MissingTarget) then
            error Error.Record("MasterDataError", "Transfer without a target cost centre: " & Text.Combine(MissingTarget, ", "))
        else
            Table.Sort(Latest, {{"asset_id", Order.Ascending}, {"effective_month_index", Order.Ascending}})
in
    Result
