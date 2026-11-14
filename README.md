# Irish House Price Pipeline

An end-to-end data pipeline that answers one question: **where in Ireland can a
young person afford a home?**

It combines Property Price Register sale records with CSO household income data
to produce affordability metrics by county, served through a Streamlit web app
and a Power BI dashboard.

> Work in progress. This README is a stub and will be completed at the end of
> the project.

## Data sources

- [Property Price Register](https://www.propertypriceregister.ie/) - every
  residential property sale in Ireland since 2010.
- [CSO PxStat](https://data.cso.ie/) - household income statistics from the
  Central Statistics Office.

## Tech stack

Python, pandas, PostgreSQL, SQLAlchemy, dbt, pytest, Streamlit, Docker,
GitHub Actions, AWS RDS, Power BI.

## Project structure

```
src/     Python scripts: ingest, clean, load
sql/     Database schema
dbt/     dbt models: staging and marts
app/     Streamlit web app
tests/   pytest data quality tests
data/    Raw and cleaned data files (not committed)
docs/    Diagrams and screenshots
```

## Setup

Requires Python 3.13 and Docker Desktop.

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

Then edit `.env` and set your own database password.
