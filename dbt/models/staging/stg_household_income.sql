-- Median gross household income by county. CSO only has 2022.

select
    county,
    year,
    median_gross_household_income
from {{ source('raw', 'household_income') }}
