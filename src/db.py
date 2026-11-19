"""Database connection used by the other scripts."""

import os

from dotenv import load_dotenv
from sqlalchemy import URL, Engine, create_engine


def get_engine(
    user_env: str = "POSTGRES_USER",
    password_env: str = "POSTGRES_PASSWORD",
    **engine_options,
) -> Engine:
    """Create a SQLAlchemy engine from the POSTGRES_* environment variables.

    Locally these come from .env. In Docker and GitHub Actions they are set
    directly so load_dotenv() does nothing.

    The ask feature passes its own user and password variables so it logs in
    as the read-only user instead.
    """
    load_dotenv()
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ[user_env],
        password=os.environ[password_env],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
    )
    return create_engine(url, **engine_options)
