-- read-only login for the "ask the data" feature.
-- it can read the four mart tables and nothing else.
--
-- don't run this file directly, run:  python src/create_readonly_user.py
-- that fills in the name and password from .env so they never live in the repo

-- create the login if it's not there yet. safe to re-run, a second run just resets the password
DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = {user_name}) THEN
        CREATE ROLE {user} LOGIN;
    END IF;
END
$$;

ALTER ROLE {user} WITH LOGIN PASSWORD {password};

-- belt and braces: even if a bad query got past the checks in the app,
-- the database itself refuses writes and kills anything slower than 5 seconds
ALTER ROLE {user} SET default_transaction_read_only = on;
ALTER ROLE {user} SET statement_timeout = '5s';

-- can see the analytics schema...
GRANT USAGE ON SCHEMA analytics TO {user};

-- ...but can only read these four tables. raw and the staging views stay off limits
GRANT SELECT ON
    analytics.mart_median_price,
    analytics.mart_affordability,
    analytics.mart_price_change,
    analytics.mart_latest_price
TO {user};
