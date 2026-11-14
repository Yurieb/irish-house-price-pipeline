-- One row per sale (full market price, VAT included).

select
    sale_id,
    sale_date,
    extract(year from sale_date)::int as sale_year,
    county,
    price,
    is_new_build,
    loaded_at
from {{ source('raw', 'ppr_sales') }}
