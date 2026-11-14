-- Median price and number of sales by county and year.

select
    county || '-' || sale_year as county_year_key,
    county,
    sale_year as year,
    count(*) as sales_count,
    round(percentile_cont(0.5) within group (order by price)::numeric, 0) as median_price
from {{ ref('stg_ppr_sales') }}
group by county, sale_year
