-- Singular test, fails if this query returns any rows.
-- A median home costing under 1 year or over 30 years of earnings means
-- something is broken upstream.

select county, year, price_to_earnings_age_25_29
from {{ ref('mart_affordability') }}
where price_to_earnings_age_25_29 not between 1 and 30
