-- A singular test: dbt fails it if this query returns any rows.
-- A median home costing less than 1 year or more than 30 years of a young
-- person's earnings would mean something upstream is broken.

select county, year, price_to_earnings_age_25_29
from {{ ref('mart_affordability') }}
where price_to_earnings_age_25_29 not between 1 and 30
