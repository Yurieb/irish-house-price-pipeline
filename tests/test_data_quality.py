"""Data quality tests on the real cleaned PPR file.

These check the output of src/clean.py. They are skipped when the file does
not exist, for example on a fresh clone before the pipeline has been run.
"""

import datetime
from pathlib import Path

import pandas as pd
import pytest

from clean import COUNTIES

CLEAN_FILE = Path(__file__).resolve().parents[1] / "data" / "clean" / "ppr_sales.csv"

pytestmark = pytest.mark.skipif(
    not CLEAN_FILE.exists(), reason="data/clean/ppr_sales.csv not found - run the pipeline first"
)


@pytest.fixture(scope="module")
def sales() -> pd.DataFrame:
    """Read the file once and share it between the tests in this module."""
    return pd.read_csv(CLEAN_FILE, parse_dates=["sale_date"])


def test_file_is_not_empty(sales):
    assert len(sales) > 500_000


def test_no_null_prices(sales):
    assert sales["price"].notna().all()


def test_prices_are_positive(sales):
    assert (sales["price"] > 0).all()


def test_no_null_dates(sales):
    assert sales["sale_date"].notna().all()


def test_dates_are_in_a_valid_range(sales):
    # The register starts in 2010, and a sale cannot be dated in the future.
    assert sales["sale_date"].min() >= pd.Timestamp(2010, 1, 1)
    assert sales["sale_date"].max() <= pd.Timestamp(datetime.date.today())


def test_no_unknown_counties(sales):
    unknown = set(sales["county"]) - set(COUNTIES)
    assert not unknown, f"Unknown counties: {sorted(unknown)}"


def test_every_county_is_present(sales):
    missing = set(COUNTIES) - set(sales["county"])
    assert not missing, f"Counties with no sales: {sorted(missing)}"
