-- Price-to-income ratios for each county and year: how many years of income
-- the median home costs. Higher means less affordable.
--
-- Covers the years the CSO earnings data covers. Household income exists for
-- 2022 only, so those two columns are null in every other year.

with prices as (

    select * from {{ ref('mart_median_price') }}

),

young_earnings as (

    select county, year, median_annual_earnings
    from {{ ref('stg_annual_earnings') }}
    where age_group = '25 - 29 years'

),

all_earnings as (

    select county, year, median_annual_earnings
    from {{ ref('stg_annual_earnings') }}
    where age_group = '15 years and over'

),

household_income as (

    select * from {{ ref('stg_household_income') }}

)

select
    prices.county_year_key,
    prices.county,
    prices.year,
    prices.median_price,
    young_earnings.median_annual_earnings as median_earnings_age_25_29,
    round(prices.median_price / young_earnings.median_annual_earnings, 1) as price_to_earnings_age_25_29,
    all_earnings.median_annual_earnings as median_earnings_all_ages,
    round(prices.median_price / all_earnings.median_annual_earnings, 1) as price_to_earnings_all_ages,
    household_income.median_gross_household_income,
    round(prices.median_price / household_income.median_gross_household_income, 1) as price_to_household_income
from prices
inner join young_earnings
    on prices.county = young_earnings.county and prices.year = young_earnings.year
inner join all_earnings
    on prices.county = all_earnings.county and prices.year = all_earnings.year
left join household_income
    on prices.county = household_income.county and prices.year = household_income.year
