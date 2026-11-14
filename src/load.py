"""Load the cleaned CSVs from data/clean/ into Postgres.

Run after clean.py with the database running:
    python src/load.py

Safe to re-run, each table is emptied and refilled in one transaction.
"""

import csv
from pathlib import Path

from sqlalchemy import text

from db import get_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CLEAN_DIR = PROJECT_ROOT / "data" / "clean"
SCHEMA_FILE = PROJECT_ROOT / "sql" / "schema.sql"

# table in the raw schema -> cleaned file that fills it
TABLES = {
    "ppr_sales": "ppr_sales.csv",
    "household_income": "household_income.csv",
    "annual_earnings": "annual_earnings.csv",
}


def load_table(connection, table: str, csv_path: Path) -> None:
    # get the column names from the CSV header for COPY.
    # sale_id and loaded_at aren't in the file so they use their defaults
    with open(csv_path, encoding="utf-8", newline="") as file:
        columns = ", ".join(next(csv.reader(file)))

    connection.execute(text(f"TRUNCATE raw.{table} RESTART IDENTITY"))

    # COPY bulk loads the whole file, much faster than inserting row by row
    copy_sql = f"COPY raw.{table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)"
    with open(csv_path, encoding="utf-8", newline="") as file:
        with connection.connection.cursor() as cursor:
            cursor.copy_expert(copy_sql, file)

    row_count = connection.execute(text(f"SELECT count(*) FROM raw.{table}")).scalar()
    print(f"  {row_count:>9,} rows loaded into raw.{table}")


def main() -> None:
    engine = get_engine()

    # one transaction - commits if everything works, rolls back if anything fails
    with engine.begin() as connection:
        print("Applying schema...")
        connection.exec_driver_sql(SCHEMA_FILE.read_text(encoding="utf-8"))

        print("Loading tables...")
        for table, file_name in TABLES.items():
            load_table(connection, table, CLEAN_DIR / file_name)

    print("Load complete.")


if __name__ == "__main__":
    main()
