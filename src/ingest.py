"""Download the raw data into data/raw/.

Run from the project root:
    python src/ingest.py

Safe to re-run, it just overwrites the old files.
"""

import io
import zipfile
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Property Price Register - all residential sales since 2010 in one zipped CSV
PPR_URL = (
    "https://www.propertypriceregister.ie/website/npsra/ppr/npsra-ppr.nsf/"
    "Downloads/PPR-ALL.zip/$FILE/PPR-ALL.zip"
)

# CSO PxStat API, the table code goes in the URL
CSO_URL = (
    "https://ws.cso.ie/public/api.restful/"
    "PxStat.Data.Cube_API.ReadDataset/{table}/CSV/1.0/en"
)

# CSO table code -> file name to save as
CSO_TABLES = {
    "GPIIA05": "cso_household_income.csv",  # household income by county, 2022
    "DEA06": "cso_annual_earnings.csv",  # earnings by county, age group and year
}


def download(url: str) -> bytes:
    """Download a URL and return the content. Raises an error on a bad response."""
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def save(path: Path, data: bytes) -> None:
    """Write to a temp file first, then rename it.

    If the download fails halfway the old file is still there.
    """
    temp_path = path.with_name(path.name + ".part")
    temp_path.write_bytes(data)
    temp_path.replace(path)
    print(f"  saved {path.name} ({len(data):,} bytes)")


def ingest_ppr() -> None:
    print("Downloading Property Price Register...")
    zipped = download(PPR_URL)

    # zip has one CSV in it, save it as is (cleaning happens in clean.py)
    with zipfile.ZipFile(io.BytesIO(zipped)) as archive:
        csv_names = [name for name in archive.namelist() if name.lower().endswith(".csv")]
        if len(csv_names) != 1:
            raise ValueError(f"Expected one CSV in the PPR zip, found: {archive.namelist()}")
        save(RAW_DIR / "ppr_all.csv", archive.read(csv_names[0]))


def ingest_cso() -> None:
    for table, file_name in CSO_TABLES.items():
        print(f"Downloading CSO table {table}...")
        save(RAW_DIR / file_name, download(CSO_URL.format(table=table)))


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    ingest_ppr()
    ingest_cso()
    print("Ingestion complete.")


if __name__ == "__main__":
    main()
