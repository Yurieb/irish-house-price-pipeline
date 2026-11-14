-- Median gross household income per county. The CSO publishes 2022 only.

select
    county,
    year,
    median_gross_household_income
from {{ source('raw', 'household_income') }}
