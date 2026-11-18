"""Create the read-only database user for the "ask the data" feature.

Runs sql/readonly_user.sql as the main POSTGRES_USER. The new user's name and
password come from ASK_POSTGRES_USER and ASK_POSTGRES_PASSWORD in .env.

    python src/create_readonly_user.py

Safe to re-run.
"""

import os
from pathlib import Path

from psycopg2 import sql

from db import get_engine

SQL_FILE = Path(__file__).resolve().parents[1] / "sql" / "readonly_user.sql"


def main() -> None:
    engine = get_engine()  # also loads .env
    user = os.environ["ASK_POSTGRES_USER"]
    password = os.environ["ASK_POSTGRES_PASSWORD"]

    # psycopg2 quotes the name and password safely, so odd characters can't break the sql
    statement = sql.SQL(SQL_FILE.read_text(encoding="utf-8")).format(
        user=sql.Identifier(user),
        user_name=sql.Literal(user),
        password=sql.Literal(password),
    )

    with engine.begin() as connection:
        with connection.connection.cursor() as cursor:
            cursor.execute(statement)

    print(f"Read-only user '{user}' is ready. It can only SELECT from the four mart tables.")


if __name__ == "__main__":
    main()
