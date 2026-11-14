"""Unit tests for the cleaning rules.

Each test builds a few raw rows by hand, runs them through transform_ppr and
checks the result. No data files are needed, so these run anywhere.
"""

import datetime

import pandas as pd
import pytest

from clean import transform_ppr

RAW_COLUMNS = [
    "Date of Sale (dd/mm/yyyy)", "Address", "County", "Eircode", "Price (€)",
    "Not Full Market Price", "VAT Exclusive", "Description of Property",
    "Property Size Description",
]


def raw_row(**changes) -> dict:
    """One valid raw PPR row. Pass keyword arguments to change any value."""
    row = {
        "Date of Sale (dd/mm/yyyy)": "15/03/2024",
        "Address": "1 Main Street",
        "County": "Dublin",
        "Eircode": "",
        "Price (€)": "€300,000.00",
        "Not Full Market Price": "No",
        "VAT Exclusive": "No",
        "Description of Property": "Second-Hand Dwelling house /Apartment",
        "Property Size Description": "",
    }
    for column, value in changes.items():
        row[column] = value
    return row


def clean(*rows: dict) -> pd.DataFrame:
    return transform_ppr(pd.DataFrame(rows, columns=RAW_COLUMNS))


def test_price_text_becomes_a_number():
    result = clean(raw_row(**{"Price (€)": "€1,250,000.50"}))
    assert result["price"].iloc[0] == 1250000.50


def test_date_text_becomes_a_date():
    result = clean(raw_row(**{"Date of Sale (dd/mm/yyyy)": "03/01/2010"}))
    # Day first: this is 3 January, not 1 March.
    assert result["sale_date"].iloc[0] == datetime.date(2010, 1, 3)


def test_invalid_date_stops_the_pipeline():
    with pytest.raises(ValueError):
        clean(raw_row(**{"Date of Sale (dd/mm/yyyy)": "31/02/2024"}))


def test_sales_not_at_full_market_price_are_dropped():
    result = clean(
        raw_row(Address="Kept"),
        raw_row(Address="Dropped", **{"Not Full Market Price": "Yes"}),
    )
    assert result["address"].tolist() == ["Kept"]


def test_exact_duplicates_are_dropped():
    result = clean(raw_row(), raw_row())
    assert len(result) == 1


def test_vat_is_added_to_vat_exclusive_prices():
    result = clean(raw_row(**{
        "Price (€)": "€185,000.00",
        "VAT Exclusive": "Yes",
        "Description of Property": "New Dwelling house /Apartment",
    }))
    assert result["price"].iloc[0] == 209975.00
    assert result["vat_added"].iloc[0]


def test_vat_inclusive_prices_are_unchanged():
    result = clean(raw_row())
    assert result["price"].iloc[0] == 300000.00
    assert not result["vat_added"].iloc[0]


@pytest.mark.parametrize(
    "description, expected",
    [
        ("New Dwelling house /Apartment", True),
        ("Teach/Árasán Cónaithe Nua", True),
        ("Second-Hand Dwelling house /Apartment", False),
        ("Teach/Árasán Cónaithe Athláimhe", False),
    ],
)
def test_new_builds_are_recognised_in_english_and_irish(description, expected):
    result = clean(raw_row(**{"Description of Property": description}))
    assert result["is_new_build"].iloc[0] == expected


def test_unknown_county_stops_the_pipeline():
    with pytest.raises(ValueError, match="Unknown counties"):
        clean(raw_row(County="Atlantis"))
