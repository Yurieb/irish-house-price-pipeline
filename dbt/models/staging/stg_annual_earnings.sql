-- Median annual earnings of one person, per county, year and age group.

select
    county,
    year,
    age_group,
    median_annual_earnings
from {{ source('raw', 'annual_earnings') }}
