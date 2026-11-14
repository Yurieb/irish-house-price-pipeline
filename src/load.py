"""Load the cleaned CSV files from data/clean/ into Postgres.

Run from the project root, after src/clean.py, with the database running:
    python src/load.py

Safe to re-run: each table is emptied and refilled inside one transaction, so
the database never holds duplicate or half-loaded data.
"""

import csv
from pathlib import Path

from sqlalchemy import text

from db import get_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = PROJECT_ROOT / "data" / "clean"
SCHEMA_FILE = PROJECT_ROOT / "sql" / "schema.sql"

# Table in the raw schema -> the cleaned file that fills it.
TABLES = {
    "ppr_sales": "ppr_sales.csv",
    "household_income": "household_income.csv",
    "annual_earnings": "annual_earnings.csv",
}


def load_table(connection, table: str, csv_path: Path) -> None:
    # Read the header row so COPY knows which columns the file contains.
    # Columns not in the file (sale_id, loaded_at) take their default values.
    with open(csv_path, encoding="utf-8", newline="") as file:
        columns = ", ".join(next(csv.reader(file)))

    connection.execute(text(f"TRUNCATE raw.{table} RESTART IDENTITY"))

    # COPY is Postgres's bulk-load command: it streams the whole file in one
    # statement, far faster than one INSERT per row.
    copy_sql = f"COPY raw.{table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with open(csv_path, encoding="utf-8", newline="") as file:
        with connection.connection.cursor() as cursor:
            cursor.copy_expert(copy_sql, file)

    row_count = connection.execute(text(f"SELECT count(*) FROM raw.{table}")).scalar()
    print(f"  {row_count:>9,} rows loaded into raw.{table}")


def main() -> None:
    engine = get_engine()

    # engine.begin() opens a transaction: it commits if everything succeeds
    # and rolls back completely if anything fails.
    with engine.begin() as connection:
        print("Applying schema...")
        connection.exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))

        print("Loading tables...")
        for table, file_name in TABLES.items():
            load_table(connection, table, CLEAN_DIR / file_name)

    print("Load complete.")


if __name__ == "__main__":
    main()
