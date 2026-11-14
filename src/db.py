"""Database connection used by the other scripts."""

import os

from dotenv import load_dotenv
from sqlalchemy import URL, Engine, create_engine


def get_engine() -> Engine:
    """Create a SQLAlchemy engine from the POSTGRES_* environment variables.

    Locally these come from .env. In Docker and GitHub Actions they are set
    directly so load_dotenv() does nothing.
    """
    load_dotenv()
    url = URL.create(
        drivername="postgresql+psycopg2",
        username=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=int(os.environ["POSTGRES_PORT"]),
        database=os.environ["POSTGRES_DB"],
    )
    return create_engine(url)
