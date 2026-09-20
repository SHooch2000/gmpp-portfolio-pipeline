"""
GMPP raw loader: Azure Blob Storage (gmppstorage/gmppdata) -> Azure SQL (raw.gmpp_<year>)

Loads each GMPP source file as-is into its own raw table:
- every column as NVARCHAR (dtype=str, no inference)
- original source column names preserved verbatim
- _source_file and _loaded_at metadata columns added
- idempotent: drops and recreates each table on every run (if_exists="replace")

Requires in .env:
    AZURE_STORAGE_CONNECTION_STRING=...
    AZURE_SQL_CONNECTION_STRING=DRIVER={ODBC Driver 18 for SQL Server};SERVER=...;DATABASE=...;UID=...;PWD=...;...
"""

import io
import os
import re
import openpyxl
import urllib.parse
from datetime import datetime, timezone

import pandas as pd
from azure.storage.blob import BlobServiceClient
from dotenv import load_dotenv
from sqlalchemy import DateTime, create_engine, text

load_dotenv()

CONTAINER = "gmppdata"

# --- connections -----------------------------------------------------------

blob_conn_str = os.environ["AZURE_STORAGE_CONNECTION_STRING"]
service = BlobServiceClient.from_connection_string(blob_conn_str)
container = service.get_container_client(CONTAINER)

sql_conn_str = os.environ["AZURE_SQL_CONNECTION_STRING"]
params = urllib.parse.quote_plus(sql_conn_str)
engine = create_engine(f"mssql+pyodbc:///?odbc_connect={params}", use_setinputsizes=False,)

with engine.begin() as conn:
    conn.execute(text(
        "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = 'raw') "
        "EXEC('CREATE SCHEMA raw')"
    ))

# --- helpers -----------------------------------------------------------

def read_blob(name: str) -> pd.DataFrame:
    """Download a blob and read it as an all-string DataFrame."""
    data = container.download_blob(name).readall()
    return pd.read_excel(io.BytesIO(data), dtype=str, engine="openpyxl")

def sanitize_columns(columns: list[str], year: str, source_file: str) -> tuple[list[str], list[dict]]:
    """Shorten column headers to fit SQL Server's 128-char identifier limit.
 
    GMPP headers often pack a short label and a full field definition into
    one cell, separated by a line break — too long to use as a SQL column
    name verbatim. This keeps the label (text before the first line break)
    as the SQL column name, and returns a mapping of every column's full
    original header so nothing is actually lost, just relocated to a
    sidecar table since SQL identifiers can't hold it.
 
    Also de-duplicates: if two shortened names collide, later ones get a
    numeric suffix.
    """
    short_names: list[str] = []
    mapping_rows: list[dict] = []
    seen: dict[str, int] = {}
 
    for position, original in enumerate(columns):
        label = str(original).split("\n")[0].strip()[:128]
        if not label:
            label = f"column_{position}"
 
        if label in seen:
            seen[label] += 1
            label = f"{label}_{seen[label]}"[:128]
        else:
            seen[label] = 0
 
        short_names.append(label)
        mapping_rows.append({
            "report_year": year,
            "source_file": source_file,
            "ordinal_position": position,
            "sql_column_name": label,
            "original_header": str(original),
        })
 
    return short_names, mapping_rows


def extract_year(blob_name: str) -> str | None:
    """Pull a 4-digit year (20xx) out of a blob name/path."""
    match = re.search(r"20\d{2}", blob_name)
    return match.group(0) if match else None


# --- main loop -----------------------------------------------------------

blob_names = [b.name for b in container.list_blobs()]
print(f"Found {len(blob_names)} blobs in {CONTAINER}:")
for name in blob_names:
    print(f"  {name}")

loaded_at = datetime.now(timezone.utc)
all_mapping_rows: list[dict] = []

for name in blob_names:
    year = extract_year(name)
    if year is None:
        print(f"SKIP — could not parse a year out of: {name}")
        continue

    print(f"\nLoading {name} -> raw.gmpp_{year} ...")
    df = read_blob(name)

    original_columns = df.columns.tolist()
    short_columns, mapping_rows = sanitize_columns(original_columns, year, name)
    df.columns = short_columns
    all_mapping_rows.extend(mapping_rows)

    df["_source_file"] = name
    df["_loaded_at"] = loaded_at

    df.to_sql(
    f"gmpp_{year}",
    engine,
    schema="raw",
    if_exists="replace",
    index=False,
    # SQL Server's TIMESTAMP is a rowversion type, not a datetime — you
    # can never insert into it. Force _loaded_at to DATETIME2 instead,
    # or SQLAlchemy's default mapping picks TIMESTAMP and every insert fails.
    dtype={"_loaded_at": DateTime()},
    )
    print(f"  wrote {len(df)} rows, {len(df.columns)} columns")

# Sidecar table: every original header, mapped to the shortened SQL column
# name that actually holds its data. This is the lookup for "what does
# [gmpp_id_number] in raw.gmpp_2021 actually mean" later in dbt docs.

print(f"\nCollected {len(all_mapping_rows)} column-mapping rows across all files.")
 
if not all_mapping_rows:
    print("WARNING: no mapping rows collected — skipping raw.gmpp_column_map. "
          "Check that all_mapping_rows.extend(mapping_rows) runs inside the per-file loop.")
else:
    column_map_df = pd.DataFrame(all_mapping_rows)
    column_map_df.to_sql(
        "gmpp_column_map",
        engine,
        schema="raw",
        if_exists="replace",
        index=False,
    )
    print(f"Wrote {len(column_map_df)} rows to raw.gmpp_column_map")
 
print("\nDone.")