// Query name: AssetMaster
// Load as: connection only
//
// One row per asset ever on the books = opening register + additions from the
// monthly files, with the disposal date taken from the register or from a
// DISPOSAL movement. Python twin: depreciation_model.master.build_asset_master
//
// The refresh fails with a readable message instead of producing wrong numbers
// when: an asset is added twice, a disposal refers to an unknown asset, an
// asset is disposed twice, or a disposal is dated before the acquisition.
let
    Register = Table.AddColumn(AssetRegister, "source", each "register", type text),
    Additions = Table.SelectRows(MovementsClean, each [movement_type] = "ADDITION"),
    AdditionsShaped = Table.FromRecords(
        Table.TransformRows(
            Additions,
            (r) => [
                asset_id = r[asset_id],
                asset_name = r[asset_name],
                category = r[category],
                cost_centre = r[cost_centre],
                acquisition_date = r[movement_date],
                cost = r[amount],
                useful_life_months = r[useful_life_months],
                disposal_date = null,
                source = "addition"
            ]
        ),
        Value.Type(Register)
    ),
    Combined = Table.Combine({Register, AdditionsShaped}),

    Disposals = Table.SelectRows(MovementsClean, each [movement_type] = "DISPOSAL"),
    DisposalDates = Table.Group(
        Disposals,
        {"asset_id"},
        {
            {"movement_disposal_date", each List.Max([movement_date]), type nullable date},
            {"disposal_count", Table.RowCount, Int64.Type}
        }
    ),
    Joined = Table.NestedJoin(
        Combined, {"asset_id"}, DisposalDates, {"asset_id"}, "d", JoinKind.LeftOuter
    ),
    Expanded = Table.ExpandTableColumn(
        Joined, "d", {"movement_disposal_date", "disposal_count"}
    ),

    // Validation - collect every problem, then fail once with all of them.
    DuplicateIds = Table.SelectRows(
        Table.Group(Combined, {"asset_id"}, {{"n", Table.RowCount, Int64.Type}}),
        each [n] > 1
    )[asset_id],
    UnknownDisposals = List.Difference(DisposalDates[asset_id], Combined[asset_id]),
    DisposedTwice = Table.SelectRows(DisposalDates, each [disposal_count] > 1)[asset_id],
    AlreadyDisposed = Table.SelectRows(
        Expanded, each [movement_disposal_date] <> null and [disposal_date] <> null
    )[asset_id],
    MissingCost = Table.SelectRows(
        Combined, each [cost] = null or [useful_life_months] = null
    )[asset_id],
    Problems =
        (if List.IsEmpty(DuplicateIds) then {} else {"Asset added more than once: " & Text.Combine(DuplicateIds, ", ")})
        & (if List.IsEmpty(UnknownDisposals) then {} else {"Disposal of unknown asset(s): " & Text.Combine(UnknownDisposals, ", ")})
        & (if List.IsEmpty(DisposedTwice) then {} else {"Asset disposed more than once: " & Text.Combine(DisposedTwice, ", ")})
        & (if List.IsEmpty(AlreadyDisposed) then {} else {"Already disposed in the register: " & Text.Combine(AlreadyDisposed, ", ")})
        & (if List.IsEmpty(MissingCost) then {} else {"Additions without cost or useful life: " & Text.Combine(MissingCost, ", ")}),
    Validated =
        if List.IsEmpty(Problems) then Expanded
        else error Error.Record("MasterDataError", Text.Combine(Problems, "; ")),

    WithDisposal = Table.AddColumn(
        Validated,
        "final_disposal_date",
        each if [movement_disposal_date] <> null then [movement_disposal_date] else [disposal_date],
        type nullable date
    ),
    Tidy = Table.RenameColumns(
        Table.RemoveColumns(WithDisposal, {"disposal_date", "movement_disposal_date", "disposal_count"}),
        {{"final_disposal_date", "disposal_date"}}
    ),
    EarlyDisposals = Table.SelectRows(
        Tidy, each [disposal_date] <> null and [disposal_date] < [acquisition_date]
    )[asset_id],
    Result =
        if List.IsEmpty(EarlyDisposals) then
            Table.Sort(
                Table.SelectColumns(
                    Tidy,
                    {
                        "asset_id", "asset_name", "category", "cost_centre", "acquisition_date",
                        "cost", "useful_life_months", "disposal_date", "source"
                    }
                ),
                {{"asset_id", Order.Ascending}}
            )
        else
            error Error.Record("MasterDataError", "Disposal before acquisition: " & Text.Combine(EarlyDisposals, ", "))
in
    Result
