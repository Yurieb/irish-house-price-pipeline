-- Median price per county over the last 12 months of data.
-- The calculator uses this because the current calendar year is incomplete
-- (in January it would have almost no sales).

with sales as (

    select * from {{ ref('stg_ppr_sales') }}

),

latest as (

    select
        max(sale_date) as period_end,
        max(loaded_at) as data_loaded_at
    from sales

)

select
    sales.county,
    (latest.period_end - interval '1 year' + interval '1 day')::date as period_start,
    latest.period_end,
    latest.data_loaded_at,
    count(*) as sales_count,
    round(percentile_cont(0.5) within group (order by sales.price)::numeric, 0) as median_price
from sales
cross join latest
where sales.sale_date > latest.period_end - interval '1 year'
group by sales.county, latest.period_end, latest.data_loaded_at
