-- Raw tables, one per cleaned CSV. Loaded by src/load.py, then dbt builds on top.
-- IF NOT EXISTS everywhere so it can be run more than once.

CREATE SCHEMA IF NOT EXISTS raw;

CREATE TABLE IF NOT EXISTS raw.ppr_sales (
    sale_id       BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sale_date     DATE           NOT NULL,
    address       TEXT           NOT NULL,
    county        TEXT           NOT NULL,
    eircode       TEXT,
    price         NUMERIC(14, 2) NOT NULL CHECK (price > 0),
    is_new_build  BOOLEAN        NOT NULL,
    vat_added     BOOLEAN        NOT NULL,
    loaded_at     TIMESTAMPTZ    NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS raw.household_income (
    county                         TEXT        NOT NULL,
    year                           INTEGER     NOT NULL,
    median_gross_household_income  INTEGER     NOT NULL,
    loaded_at                      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (county, year)
);

CREATE TABLE IF NOT EXISTS raw.annual_earnings (
    county                  TEXT        NOT NULL,
    year                    INTEGER     NOT NULL,
    age_group               TEXT        NOT NULL,
    median_annual_earnings  INTEGER     NOT NULL,
    loaded_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (county, year, age_group)
);
