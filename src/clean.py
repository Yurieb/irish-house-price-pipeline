"""Clean the raw files in data/raw/ and save them to data/clean/.

Run after ingest.py:
    python src/clean.py

Prints row counts before and after so we can see what got dropped.
"""

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
CLEAN_DIR = PROJECT_ROOT / "data" / "clean"

# New homes are listed in the PPR without VAT which is charged at 13.5%.
VAT_RATE = 0.135

COUNTIES = [
    "Carlow", "Cavan", "Clare", "Cork", "Donegal", "Dublin", "Galway", "Kerry",
    "Kildare", "Kilkenny", "Laois", "Leitrim", "Limerick", "Longford", "Louth",
    "Mayo", "Meath", "Monaghan", "Offaly", "Roscommon", "Sligo", "Tipperary",
    "Waterford", "Westmeath", "Wexford", "Wicklow",
]


def check_counties(df: pd.DataFrame, source: str) -> None:
    """Raise an error if a county isn't one of the 26."""
    unknown = set(df["county"]) - set(COUNTIES)
    if unknown:
        raise ValueError(f"Unknown counties in {source}: {sorted(unknown)}")


def clean_ppr() -> None:
    print("Property Price Register")

    # PPR file is Windows-1252 not UTF-8 (the euro sign breaks UTF-8).
    # read everything as text and convert the columns ourselves
    df = pd.read_csv(RAW_DIR / "ppr_all.csv", encoding="cp1252", dtype=str)
    df = transform_ppr(df)
    df.to_csv(CLEAN_DIR / "ppr_sales.csv", index=False, encoding="utf-8")
    print(f"  {len(df):>9,} rows written to ppr_sales.csv")


def transform_ppr(df: pd.DataFrame) -> pd.DataFrame:
    """Clean the raw PPR rows.

    Separate from the file reading/writing so it can be tested with a few rows.
    """
    df.columns = [
        "sale_date", "address", "county", "eircode", "price",
        "not_full_market_price", "vat_exclusive", "description", "size_description",
    ]
    print(f"  {len(df):>9,} rows read")

    # drop sales not at full market price (e.g. family transfers), they skew the median
    df = df[df["not_full_market_price"] == "No"]
    print(f"  {len(df):>9,} after dropping sales not at full market price")

    # exact duplicate rows = same sale entered twice
    df = df.drop_duplicates()
    print(f"  {len(df):>9,} after dropping exact duplicate rows")

    # "01/01/2010" -> date, errors if the date is invalid
    df["sale_date"] = pd.to_datetime(df["sale_date"], format="%d/%m/%Y").dt.date

    # "€343,000.00" -> 343000.0
    df["price"] = df["price"].str.replace("[€,]", "", regex=True).astype(float)

    # add VAT where the price excludes it, so all prices are what the buyer paid
    df["vat_added"] = df["vat_exclusive"] == "Yes"
    df.loc[df["vat_added"], "price"] *= 1 + VAT_RATE
    df["price"] = df["price"].round(2)
    print(f"  {df['vat_added'].sum():>9,} prices had VAT added")

    # description can be English or Irish - "New ..." or "... Nua" is a new build
    df["is_new_build"] = df["description"].str.startswith("New") | df["description"].str.endswith("Nua")

    df["county"] = df["county"].str.strip()
    check_counties(df, "PPR")

    return df[["sale_date", "address", "county", "eircode", "price", "is_new_build", "vat_added"]]


def clean_cso(raw_name: str, clean_name: str, statistic: str, value_name: str) -> None:
    """Keep one statistic from a CSO table for the 26 counties."""
    print(f"CSO {raw_name}")
    df = pd.read_csv(RAW_DIR / raw_name)
    print(f"  {len(df):>9,} rows read")

    df = df[df["Statistic Label"] == statistic]
    # The earnings table is split by sex we only want the combined figure.
    if "Sex" in df.columns:
        df = df[df["Sex"] == "Both sexes"]
    print(f"  {len(df):>9,} after keeping '{statistic}'")

    # "Co. Dublin" -> "Dublin" to match the PPR, and drop the Ireland total
    df = df[df["County"] != "Ireland"]
    df["county"] = df["County"].str.replace("Co. ", "", regex=False).str.strip()
    check_counties(df, raw_name)

    df = df.rename(columns={"Year": "year", "Age Group": "age_group", "VALUE": value_name})
    columns = [c for c in ["county", "year", "age_group", value_name] if c in df.columns]
    df[columns].to_csv(CLEAN_DIR / clean_name, index=False, encoding="utf-8")
    print(f"  {len(df):>9,} rows written to {clean_name}")


def main() -> None:
    CLEAN_DIR.mkdir(parents=True, exist_ok=True)
    clean_ppr()
    clean_cso(
        "cso_household_income.csv", "household_income.csv",
        "Median Gross Household Income", "median_gross_household_income",
    )
    clean_cso(
        "cso_annual_earnings.csv", "annual_earnings.csv",
        "Median Annual Earnings", "median_annual_earnings",
    )
    print("Cleaning complete.")


if __name__ == "__main__":
    main()
