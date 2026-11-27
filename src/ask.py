"""Answer plain-English questions about the house price data.

How it works:
  1. send the AI the mart table columns and the question, get back one SQL query
  2. check the query is a single SELECT on the mart tables, and cap it at 100 rows
  3. run it as the read-only database user with a 5 second timeout
     if it's rejected, errors or finds no rows, the AI is told why and tries again (3 tries max)
  4. ask the AI to sum up the result in one or two sentences

Uses Amazon Bedrock through boto3. Needs these in .env (or Streamlit secrets):
  ASK_POSTGRES_USER, ASK_POSTGRES_PASSWORD, AWS_ACCESS_KEY_ID,
  AWS_SECRET_ACCESS_KEY, AWS_DEFAULT_REGION, BEDROCK_MODEL_ID

Try it from the terminal:
    python src/ask.py "Which county had the highest median price in 2025?"
"""

import logging
import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache

import boto3
import pandas as pd
import sqlglot
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp

from db import get_engine

load_dotenv()  # before boto3 reads the AWS_* settings
log = logging.getLogger(__name__)

SCHEMA = "analytics"
MART_TABLES = {"mart_median_price", "mart_affordability", "mart_price_change", "mart_latest_price"}
MAX_ROWS = 100
TIMEOUT_MS = 5000
MAX_QUESTION_LENGTH = 300
MAX_ATTEMPTS = 3  # first try plus two fixes, so a confused AI can't loop forever

# things the column names alone don't tell the AI
TABLE_NOTES = """
- county is one of the 26 counties of Ireland, written like 'Dublin' or 'Cork' (no 'Co.').
- year is a calendar year. Sales data runs 2010 to 2026, and 2026 is only part of a year.
- Prices are in euro and are medians, not averages.
- mart_median_price: median sale price and number of sales per county per year.
- mart_price_change: change in median price from the previous year. change_pct is a percentage (5.2 means 5.2%).
- mart_affordability: years 2011 to 2025. price_to_earnings_age_25_29 is the median price divided by the
  median yearly earnings of people aged 25 to 29 (higher = less affordable).
  median_gross_household_income and price_to_household_income only have values for 2022.
- mart_latest_price: one row per county for the most recent 12 months of sales (period_start to period_end).
""".strip()

SQL_INSTRUCTIONS = """You write PostgreSQL queries about Irish house prices.

Tables you can use (always write them with the analytics. prefix):
{schema}

Notes:
{notes}

Rules:
- Reply with one SELECT query and nothing else. No explanation, no markdown.
- Only use the tables above.
- Add LIMIT 100 or lower.
- Round ratios to 1 decimal place and prices to whole euro.
- If the tables can't answer the question, reply with exactly: CANNOT_ANSWER"""

SUMMARY_INSTRUCTIONS = """You explain query results about Irish house prices to a member of the public.
Answer the question in one or two short, plain sentences using only the numbers in the result.
Write euro amounts like €350,000. If the result is empty, say no matching data was found."""


class UnsafeQueryError(ValueError):
    """The AI's query broke one of the safety rules."""


@dataclass
class Attempt:
    """A query that didn't work, and why. Sent back to the AI so it can fix it."""
    sql: str
    problem: str


@dataclass
class AskResult:
    question: str
    answer: str
    sql: str | None = None
    data: pd.DataFrame | None = None
    ok: bool = True
    attempts: list[Attempt] = field(default_factory=list)  # failed tries before the final query


# the AI

def call_model(instructions: str, message: str) -> str:
    """Send one message to the Bedrock model and return its reply text."""
    client = boto3.client("bedrock-runtime")
    # the converse api works the same way for every model on bedrock,
    # so switching model is just a change to BEDROCK_MODEL_ID
    response = client.converse(
        modelId=os.environ["BEDROCK_MODEL_ID"],
        system=[{"text": instructions}],
        messages=[{"role": "user", "content": [{"text": message}]}],
        inferenceConfig={"maxTokens": 600, "temperature": 0},
    )
    return response["output"]["message"]["content"][0]["text"].strip()


def write_query(instructions: str, question: str, attempts: list["Attempt"]) -> str:
    """Ask the AI for a query. On a retry it also sees its earlier queries and what was wrong with them."""
    message = question
    if attempts:
        earlier = "\n\n".join(f"Query:\n{attempt.sql}\nProblem: {attempt.problem}" for attempt in attempts)
        message = f"{question}\n\nYour earlier queries didn't work:\n\n{earlier}\n\nWrite a corrected query."
    return clean_reply(call_model(instructions, message))


def clean_reply(reply: str) -> str:
    """Strip the ```sql fences models sometimes add even when told not to."""
    reply = reply.strip()
    if reply.startswith("```"):
        reply = reply.strip("`")
        if reply.lower().startswith("sql"):
            reply = reply[3:]
    return reply.strip()


# checking the query

def check_sql(query: str) -> str:
    """Make sure the query is safe to run, and return it with a LIMIT of 100 at most.

    Uses a real SQL parser rather than searching the text, so it can tell a table
    name from something like extract(year from period_end).
    """
    try:
        statements = [s for s in sqlglot.parse(query, read="postgres") if s is not None]
    except sqlglot.errors.ParseError:
        raise UnsafeQueryError("The query isn't valid SQL.")

    if len(statements) != 1:
        raise UnsafeQueryError("Only one statement is allowed.")
    statement = statements[0]

    if not isinstance(statement, exp.Select):
        raise UnsafeQueryError("Only SELECT queries are allowed.")
    if statement.args.get("into"):
        raise UnsafeQueryError("SELECT INTO creates a table, so it isn't allowed.")
    # catches a write hidden inside a WITH, e.g. with d as (delete from ...) select ...
    if statement.find(exp.Insert, exp.Update, exp.Delete, exp.Merge, exp.Drop, exp.Create, exp.Alter, exp.Command):
        raise UnsafeQueryError("The query tries to change data.")

    # names from WITH ... AS (...) are fine to select from
    cte_names = {cte.alias_or_name for cte in statement.find_all(exp.CTE)}
    for table in statement.find_all(exp.Table):
        if not table.db and table.name in cte_names:
            continue
        if table.db not in ("", SCHEMA) or table.name not in MART_TABLES:
            shown = f"{table.db}.{table.name}" if table.db else table.name or "a function"
            raise UnsafeQueryError(f"The query uses {shown}, which isn't one of the mart tables.")

    # keep the AI's limit if it's 100 or lower, otherwise force it to 100
    limit = statement.args.get("limit")
    limit_value = limit.expression if limit else None
    if not (isinstance(limit_value, exp.Literal) and limit_value.is_int and int(limit_value.this) <= MAX_ROWS):
        statement = statement.limit(MAX_ROWS)

    return statement.sql(dialect="postgres", pretty=True)


# the database

@lru_cache(maxsize=1)
def reader_engine() -> Engine:
    # read-only user, and postgres cancels any query that runs longer than 5 seconds
    return get_engine(
        "ASK_POSTGRES_USER",
        "ASK_POSTGRES_PASSWORD",
        connect_args={"options": f"-c statement_timeout={TIMEOUT_MS}"},
    )


@lru_cache(maxsize=1)
def table_schemas() -> str:
    """List the mart tables and their columns, read from the database so it never goes out of date."""
    query = text("""
        select table_name, string_agg(column_name || ' ' || data_type, ', ' order by ordinal_position)
        from information_schema.columns
        where table_schema = :schema and table_name = any(:tables)
        group by table_name
        order by table_name
    """)
    with reader_engine().connect() as connection:
        rows = connection.execute(query, {"schema": SCHEMA, "tables": sorted(MART_TABLES)}).all()
    return "\n".join(f"- {SCHEMA}.{name} ({columns})" for name, columns in rows)


def run_query(query: str) -> pd.DataFrame:
    with reader_engine().connect() as connection:
        return pd.read_sql(text(query), connection)


def first_line(error: Exception) -> str:
    """The useful bit of a database error, e.g. 'column "yr" does not exist', without the whole query."""
    message = str(getattr(error, "orig", None) or error).strip()
    return message.splitlines()[0][:300] if message else type(error).__name__


# putting it together

def ask(question: str) -> AskResult:
    """Answer a question. Never raises, any problem comes back as a friendly message."""
    question = question.strip()
    if not question:
        return AskResult(question, "Please type a question.", ok=False)
    if len(question) > MAX_QUESTION_LENGTH:
        return AskResult(question, f"Please keep your question under {MAX_QUESTION_LENGTH} characters.", ok=False)

    sql = None
    attempts: list[Attempt] = []
    try:
        instructions = SQL_INSTRUCTIONS.format(schema=table_schemas(), notes=TABLE_NOTES)

        # if a query fails, tell the AI what went wrong and let it try again
        for number in range(1, MAX_ATTEMPTS + 1):
            last_try = number == MAX_ATTEMPTS
            reply = write_query(instructions, question, attempts)
            if reply == "CANNOT_ANSWER":
                return AskResult(
                    question,
                    "I can only answer questions about house prices, sales and affordability by county. "
                    "Try asking about a county or a year.",
                    ok=False,
                    attempts=attempts,
                )

            sql = reply  # so a rejected query can still be shown
            try:
                sql = check_sql(reply)
                data = run_query(sql)
            except UnsafeQueryError as error:
                if last_try:
                    raise
                problem = f"The safety check rejected it: {error}"
            except (SQLAlchemyError, pd.errors.DatabaseError) as error:  # pandas wraps db errors in its own type
                if last_try:
                    raise
                problem = f"The database gave an error: {first_line(error)}"
            else:
                if not data.empty or last_try:
                    break
                problem = ("It ran but returned no rows. Check you used the right table "
                           "and that the filter values match the data.")

            log.info("attempt %d failed: %s", number, problem)
            attempts.append(Attempt(sql, problem))

        result_text = data.head(20).to_csv(index=False) if not data.empty else "(no rows)"
        answer = call_model(SUMMARY_INSTRUCTIONS, f"Question: {question}\n\nResult:\n{result_text}")
        return AskResult(question, answer, sql=sql, data=data, attempts=attempts)

    except UnsafeQueryError as error:
        log.warning("rejected query: %s", error)
        return AskResult(question, f"I couldn't turn that into a safe query. {error} Try rewording your question.",
                         sql=sql, ok=False, attempts=attempts)
    except (ClientError, BotoCoreError) as error:
        log.exception("bedrock call failed: %s", error)
        return AskResult(question, "The AI service isn't available right now. Please try again in a minute.",
                         sql=sql, ok=False, attempts=attempts)
    except (SQLAlchemyError, pd.errors.DatabaseError) as error:
        log.exception("query failed: %s", error)
        return AskResult(question, "The database couldn't run that query (it may have taken too long). "
                         "Try a simpler question.", sql=sql, ok=False, attempts=attempts)
    except Exception as error:
        log.exception("ask failed: %s", error)
        return AskResult(question, "Something went wrong answering that. Please try again.",
                         sql=sql, ok=False, attempts=attempts)


if __name__ == "__main__":
    result = ask(" ".join(sys.argv[1:]) or "Which county had the highest median price in 2025?")
    print(result.answer)
    for number, attempt in enumerate(result.attempts, start=1):
        print(f"\nAttempt {number} didn't work: {attempt.problem}\n{attempt.sql}")
    if result.sql:
        print("\nSQL:\n" + result.sql)
    if result.data is not None:
        print("\n" + result.data.head(10).to_string(index=False))
