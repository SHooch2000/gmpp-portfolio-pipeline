# GMPP Portfolio Data Pipeline

An end-to-end analytics engineering project: six years (2021–2026) of the UK
Infrastructure and Projects Authority's Government Major Projects Portfolio
(GMPP) data, taken from raw published files through to a tested dimensional
model, built on Azure SQL and dbt.

Built as a portfolio project to demonstrate dbt, cloud warehousing, and
CI/CD in a Microsoft-stack context — skills that sit alongside an existing
background in SQL Server, Power BI, and dimensional modelling.

## Why this dataset

The IPA publishes GMPP data annually on gov.uk. The publication's shape
changes between years — column names, financial-year price bases, and even
file format are inconsistent release to release. Handling that drift
correctly is itself the modelling problem this project is built to solve,
not an obstacle to work around.

## Architecture

```
Azure Blob Storage (gmppstorage/gmppdata)
        │  Python loader (pandas + azure-storage-blob)
        ▼
Azure SQL — raw schema (raw.gmpp_2021 … raw.gmpp_2026, raw.gmpp_column_map)
        │  dbt
        ▼
Azure SQL — dbt_dev schema
   staging   → stg_gmpp_2021 … stg_gmpp_2026
   marts     → int_gmpp_unioned
             → dim_project, dim_department, dim_date
             → fct_project_status, fct_project_commentary
```

## Tech stack

- **Ingestion:** Python (pandas, azure-storage-blob, SQLAlchemy/pyodbc)
- **Warehouse:** Azure SQL Database
- **Transformation:** dbt-core + dbt-sqlserver
- **Testing/docs:** dbt tests, `dbt docs`

## Raw layer

Each year lands in its own table (`raw.gmpp_<year>`), loaded as-is:

- Every column `NVARCHAR`, no type inference at load time — casting happens
  later, in dbt, where it's version-controlled and testable
- Original source column names preserved as closely as SQL Server allows
  (see **Column name handling** below)
- `_source_file` and `_loaded_at` metadata columns added to every row
- Idempotent — the loader drops and recreates each raw table on every run

### Column name handling

GMPP source headers often pack a short label and a full field definition
into one cell, separated by a line break — e.g. `IPA Delivery Confidence
Assessment` followed by a parenthetical explanation of the five-point
rating scale. SQL Server caps identifiers at 128 characters, so the full
text can't be used as a column name directly.

The loader splits each header on its first line break: the short label
becomes the SQL column name, and the **full original header** (label +
definition) is preserved in a sidecar table, `raw.gmpp_column_map`
(year, ordinal position, SQL column name, original header text). Nothing
from the source is discarded — it's relocated to where SQL Server can
hold it.

### File formats

Not every year's publication is the same file type — at least one year is
`.xlsx` rather than `.csv`. The loader branches on file extension
(`read_excel` vs `read_csv`, with a UTF-8 → cp1252 fallback for the CSVs)
rather than assuming a single format across all six years.

## Staging layer

One `stg_gmpp_<year>` model per source year. Each model maps that year's
actual raw columns onto a shared, consistent contract (`project_id`,
`department`, `dca_rating`, `report_year`, etc.), so the differences
between years are resolved explicitly, one model at a time, rather than
assumed away.

`report_year` is a hardcoded literal per model (`'2021' as report_year` in
`stg_gmpp_2021`, and so on) — each staging model only ever reads from one
year's raw table, so the literal is a fact about that model's fixed input,
not a guess.

## Star schema

**Grain:** one row per project, per report year — a project that appears
in five publications has five rows, one per year's reported status.

| Table | Role |
|---|---|
| `dim_project` | One row per distinct `project_id` |
| `dim_department` | One row per sponsoring department |
| `dim_date` | One row per GMPP `report_year` |
| `fct_project_status` | Numeric measures: baseline/forecast/whole-life cost, variance %, DCA rating |
| `fct_project_commentary` | Narrative text: schedule, cost, and delivery-confidence commentary |

### Design decisions

**Cost fields use `TRY_CAST`, not `CAST`.** Source cost columns are text
containing `£` and thousands separators, and a small number of
commercially sensitive MOD projects have cost fields replaced with FOI
exemption text (e.g. *"Exempt under Section 43..."*) instead of a number.
`TRY_CAST` returns `NULL` for non-numeric text rather than failing the
whole model build over a handful of legitimately exempt values.

**Commentary is split into its own fact table.** Narrative fields are
written at the same grain as `fct_project_status` but compress and query
very differently from numeric measures — bulky free text in the same
table as cost/status measures bloats a Power BI semantic model and gets
scanned even when unused. Splitting them keeps the numeric fact table
lean; both tables share the same `project_key`/`date_key` and can be
related 1:1 when narrative detail is needed.

**Rows with a null `project_id` are excluded from both fact tables.** A
handful of projects have their `Major Projects ID` itself withheld under
FOI exemption, not just their narrative fields. `dim_project` excludes
null IDs (they can't form a meaningful dimension row), and both fact
tables filter to match — a documented, deliberate exclusion rather than a
silent one. This is a known limitation: those projects' cost figures are
not represented in portfolio-level totals.

## Testing

`relationships` tests on every foreign key in both fact tables, checked
against their dimension tables via `dbt test`. Confirms referential
integrity end-to-end rather than assuming the joins are clean.

## Running it

```bash
# 1. Load raw data (from the repo root, or wherever load_gmpp.py lives)
python load_gmpp.py

# 2. Run and test the dbt project
cd gmpp_dbt
dbt run
dbt test

# 3. Browse the docs / lineage graph
dbt docs generate
dbt docs serve
```

Requires a `.env` with `AZURE_STORAGE_CONNECTION_STRING` and
`AZURE_SQL_CONNECTION_STRING`, and a `~/.dbt/profiles.yml` pointing at the
same Azure SQL database under the `dbt_dev` schema. Neither file is
committed to this repo.

## Known limitations / next steps

- Two projects per year are excluded from the fact tables due to withheld
  identifiers (see **Design decisions** above)
- No CI/CD yet — `dbt run`/`dbt test` are run manually; a GitHub Actions
  workflow triggering on push is the next phase
- No Power BI semantic model built on top yet
- `dim_project` is Type 1 (no history) — if a project's name or department
  changes between publications, only the latest value is kept