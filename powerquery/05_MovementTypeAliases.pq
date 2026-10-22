// Query name: MovementTypeAliases
// Load as: connection only
//
// Spellings of the movement type column (lower case, trimmed) -> canonical type.
// Mirrors MOVEMENT_TYPE_ALIASES in src/depreciation_model/config.py.
let
    Aliases = #table(
        type table [alias = text, canonical = text],
        {
            {"addition", "ADDITION"},
            {"add", "ADDITION"},
            {"disposal", "DISPOSAL"},
            {"disp", "DISPOSAL"},
            {"transfer", "TRANSFER"},
            {"trf", "TRANSFER"}
        }
    )
in
    Aliases
