-- Year-on-year change in median price by county.
-- First year has no previous year so the change is null.

with prices as (

    select
        county_year_key,
        county,
        year,
        median_price,
        lag(median_price) over (partition by county order by year) as previous_median_price
    from {{ ref('mart_median_price') }}

)

select
    county_year_key,
    county,
    year,
    median_price,
    previous_median_price,
    median_price - previous_median_price as change_eur,
    round(100.0 * (median_price - previous_median_price) / previous_median_price, 1) as change_pct
from prices
