# Loading the Power Query scripts into Excel

openpyxl cannot write Power Query definitions into a workbook, so the `.pq` scripts
are pasted in once by hand. After that, the workbook refreshes with
**Data > Refresh All**. Allow about 15 minutes for the first setup.

Written for Excel for Microsoft 365 on Windows (English UI). Excel 2019/2021 work the
same way; some menu names differ slightly.

## 0. Prepare the files

From the repository root (PowerShell):

```powershell
python -m depreciation_model all
python -m depreciation_model workbook --source-folder source_files
```

The second command resolves `source_files` to its full path and writes it into the
workbook's `SourceFolder` parameter, so you do not need to type it.

Open `depreciation_model.xlsx`. If Excel shows a yellow *Protected View* bar, click
**Enable Editing**.

## 1. Check the parameters

Sheet **Parameters**:

| Cell | Named range    | Value                                                    |
|------|----------------|----------------------------------------------------------|
| B2   | `SourceFolder` | full path to `source_files\` (with or without the final `\`) |
| B3   | `ReportStart`  | first reporting month, e.g. 2024-01-01                   |
| B4   | `ReportMonths` | number of months, e.g. 24                                |

To point the model at another folder later, change B2 and refresh. You do not need to edit any M code.

## 2. Allow the workbook parameters to be combined with the files

The queries read a cell of this workbook and files from disk. Excel's privacy
firewall blocks that combination by default (error: *"Formula.Firewall: Query ...
references other queries or steps, so it may not directly access a data source"*).

1. **Data > Get Data > Query Options**.
2. Under **CURRENT WORKBOOK > Privacy**, choose **Ignore the Privacy Levels and
   potentially improve performance**.
3. **OK**.

This setting applies only to this workbook. The data is all local and synthetic.

## 3. Paste the queries (in this order)

Repeat for each file in `powerquery/`, **in numeric order** (later queries refer
to earlier ones by name):

1. **Data > Get Data > From Other Sources > Blank Query**. The Power Query Editor opens.
2. **Home > Advanced Editor**.
3. Select everything in the editor and replace it with the full contents of the `.pq` file
   (open it in Notepad/VS Code, Ctrl+A, Ctrl+C, then Ctrl+V into the editor).
4. Click **Done**.
5. In the **Query Settings** pane on the right, set **Name** to the name in the
   file's first line (`// Query name: ...`). The name must match exactly.
6. For the next file, stay in the Power Query Editor and use **Home > New Source >
   Other Sources > Blank Query**, then repeat steps 2-5.

| # | File                          | Query name            | Load as                  |
|---|-------------------------------|-----------------------|--------------------------|
| 1 | `01_pSourceFolder.pq`         | `pSourceFolder`       | connection only          |
| 2 | `02_pReportStart.pq`          | `pReportStart`        | connection only          |
| 3 | `03_pReportMonths.pq`         | `pReportMonths`       | connection only          |
| 4 | `04_ColumnAliases.pq`         | `ColumnAliases`       | connection only          |
| 5 | `05_MovementTypeAliases.pq`   | `MovementTypeAliases` | connection only          |
| 6 | `06_fnCleanMovementFile.pq`   | `fnCleanMovementFile` | connection only (function) |
| 7 | `07_AssetRegister.pq`         | `AssetRegister`       | connection only          |
| 8 | `08_MovementsClean.pq`        | `MovementsClean`      | connection only          |
| 9 | `09_AssetMaster.pq`           | `AssetMaster`         | connection only          |
| 10 | `10_Transfers.pq`            | `Transfers`           | connection only          |
| 11 | `11_ReportMonths.pq`         | `ReportMonths`        | connection only          |
| 12 | `12_AssetMonthGrid.pq`       | `AssetMonthGrid`      | connection only          |
| 13 | `13_Depreciation.pq`         | `Depreciation`        | connection only (optional: table on a new sheet) |
| 14 | `14_MonthlyTotals.pq`        | `MonthlyTotals`       | **table on `PQ_MonthlyTotals!$A$1`** |

Tip: put queries 1-6 in a group called *Setup* (right-click > Move To Group).

## 4. Load

1. In the Power Query Editor: **Home > Close & Load > Close & Load To...**
2. Choose **Only Create Connection** > **OK**. This applies to all new queries.
3. Back in Excel, open **Data > Queries & Connections**. Right-click
   **MonthlyTotals > Load To... > Table > Existing worksheet**, type
   `=PQ_MonthlyTotals!$A$1`, then **OK**.
4. **Data > Refresh All**.

## 5. Check the result

Open the **Check** sheet:

* **B2 Overall status** should read **ALL CHECKS PASS** (green).
* B3 `TRUE` means the Power Query output is loaded; B5 `TRUE` means its columns are in
  the expected order.
* Each month row compares 7 measures (rows, additions, disposals, depreciation, gross
  cost, accumulated depreciation, NBV) between Power Query and the Python reference in
  `Expected_MonthlyTotals`. The tolerance is 0.01 per value.

If a row says **MISMATCH**, the *Difference* columns show which value and month are off.

## Troubleshooting

| Symptom | Cause / fix |
|---------|-------------|
| `Formula.Firewall` error | Step 2 not done. |
| `DataSource.NotFound` / could not find path | `SourceFolder` (Parameters!B2) is wrong. It must point to the folder that contains `asset_register.csv`. |
| `Expression.Error: The import X matches no exports` | A query name is misspelt, or a query was pasted before the queries it uses. Check the names against the table above. |
| `UnknownColumn` / `UnknownMovementType` error | A movement file contains a header or type that is not in `ColumnAliases` / `MovementTypeAliases`. Add one row to the alias query **and** to `config.py`. |
| `MasterDataError` | The movement files contradict the register (duplicate addition, disposal of an unknown asset, ...). The message lists the asset ids. |
| Check sheet B5 is `FALSE` | `MonthlyTotals` was edited and its columns are no longer in the expected order. |
| Check says NOT LOADED | `MonthlyTotals` was loaded somewhere other than `PQ_MonthlyTotals!A1`. |
