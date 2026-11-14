"""Download the raw source data into data/raw/.

Run from the project root:
    python src/ingest.py

Safe to re-run: every run downloads the latest files and overwrites the old
ones, so running it twice leaves the same result as running it once.
"""

import io
import zipfile
from pathlib import Path

import requests

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"

# Property Price Register: every residential sale since 2010, as one zipped CSV.
PPR_URL = (
    "https://www.propertypriceregister.ie/website/npsra/ppr/npsra-ppr.nsf/"
    "Downloads/PPR-ALL.zip/$FILE/PPR-ALL.zip"
)

# CSO PxStat API: one URL per table, with the table code in the middle.
CSO_URL = (
    "https://ws.cso.ie/public/api.restful/"
    "PxStat.Data.Cube_API.ReadDataset/{table}/CSV/1.0/en"
)

# CSO table code -> the file name we save it as.
CSO_TABLES = {
    "GPIIA05": "cso_household_income.csv",  # household income by county, 2022
    "DEA06": "cso_annual_earnings.csv",  # earnings by county, age group and year
}


def download(url: str) -> bytes:
    """Fetch a URL and return its content, raising an error if the request fails."""
    response = requests.get(url, timeout=120)
    response.raise_for_status()
    return response.content


def save(path: Path, data: bytes) -> None:
    """Write to a temporary file, then rename it over the real one.

    If the write is interrupted, the previous good file is left untouched.
    """
    temp_path = path.with_name(path.name + ".part")
    temp_path.write_bytes(data)
    temp_path.replace(path)
    print(f"  saved {path.name} ({len(data):,} bytes)")


def ingest_ppr() -> None:
    print("Downloading Property Price Register...")
    zipped = download(PPR_URL)

    # The zip holds a single CSV. It is saved exactly as published: decoding
    # and fixing the contents is the cleaning step's job.
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
