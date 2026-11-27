"""Answer plain-English questions about the house price data, using an AI agent.

How it works:
  The AI gets the question, the mart table layouts and two tools:
    run_sql          run a SELECT on the mart tables and see the rows
    distinct_values  see the values in one column, e.g. how counties are spelled or which years exist
  It decides which tool to call, looks at the result, and keeps going until it can
  answer in one or two sentences. If a query is rejected, errors or finds no rows,
  it sees that and can try something else. It gets 6 turns at most.

Every query, whoever writes it, is checked (one SELECT, mart tables only, 100 rows max)
and runs as a read-only database user with a 5 second timeout.

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
ROWS_SHOWN_TO_AI = 20  # the AI sees the first 20 rows of a result, the app shows them all
MAX_DISTINCT_VALUES = 50
TIMEOUT_MS = 5000
MAX_QUESTION_LENGTH = 300
MAX_TURNS = 6  # so a confused AI can't loop forever or run up the bill

CANNOT_ANSWER = "CANNOT_ANSWER"

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

AGENT_INSTRUCTIONS = """You answer questions about Irish house prices using a PostgreSQL database.

Tables you can use (always write them with the analytics. prefix):
{schema}

Notes:
{notes}

How to work:
- Use the run_sql tool to get the data. Only SELECT queries on the tables above are allowed.
- If you're not sure how a value is written or which years exist, check with distinct_values first.
- If a query is rejected, errors or returns no rows, work out why and try a different query.
- Round ratios to 1 decimal place and prices to whole euro.
- When you have the data, answer in one or two short, plain sentences using only numbers from your
  query results. Write euro amounts like €350,000.
- If the tables can't answer the question, reply with exactly: {cannot_answer}"""

TOOLS = [
    {"toolSpec": {
        "name": "run_sql",
        "description": "Run one PostgreSQL SELECT query on the analytics mart tables and get the rows back.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "A single SELECT query."}},
            "required": ["query"],
        }},
    }},
    {"toolSpec": {
        "name": "distinct_values",
        "description": "List the different values in one column of a mart table (up to 50), "
                       "for example to check how a county is written or which years exist.",
        "inputSchema": {"json": {
            "type": "object",
            "properties": {
                "table": {"type": "string", "description": "Table name without the analytics. prefix."},
                "column": {"type": "string"},
            },
            "required": ["table", "column"],
        }},
    }},
]


class UnsafeQueryError(ValueError):
    """The AI's query broke one of the safety rules."""


@dataclass
class Step:
    """One tool call the agent made, shown in the app so people can see how it got the answer."""
    tool: str
    detail: str  # the SQL, or table.column
    outcome: str  # e.g. "12 rows", "no rows", "rejected: ..."
    worked: bool


@dataclass
class AskResult:
    question: str
    answer: str
    sql: str | None = None  # the query behind the answer
    data: pd.DataFrame | None = None
    ok: bool = True
    steps: list[Step] = field(default_factory=list)


# the AI

def call_model(system: str, messages: list[dict]) -> dict:
    """Send the conversation so far to the Bedrock model, with the tools, and return its reply message."""
    client = boto3.client("bedrock-runtime")
    # the converse api works the same way for every model on bedrock,
    # so switching model is just a change to BEDROCK_MODEL_ID
    response = client.converse(
        modelId=os.environ["BEDROCK_MODEL_ID"],
        system=[{"text": system}],
        messages=messages,
        toolConfig={"tools": TOOLS},
        inferenceConfig={"maxTokens": 1000, "temperature": 0},
    )
    return response["output"]["message"]


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
def table_columns() -> dict[str, list[tuple[str, str]]]:
    """Each mart table's (column, type) pairs, read from the database so they never go out of date."""
    query = text("""
        select table_name, column_name, data_type
        from information_schema.columns
        where table_schema = :schema and table_name = any(:tables)
        order by table_name, ordinal_position
    """)
    with reader_engine().connect() as connection:
        rows = connection.execute(query, {"schema": SCHEMA, "tables": sorted(MART_TABLES)}).all()
    columns: dict[str, list[tuple[str, str]]] = {}
    for table, column, data_type in rows:
        columns.setdefault(table, []).append((column, data_type))
    return columns


def table_schemas() -> str:
    return "\n".join(
        f"- {SCHEMA}.{table} ({', '.join(f'{name} {kind}' for name, kind in columns)})"
        for table, columns in table_columns().items()
    )


def run_query(query: str) -> pd.DataFrame:
    with reader_engine().connect() as connection:
        return pd.read_sql(text(query), connection)


def first_line(error: Exception) -> str:
    """The useful bit of a database error, e.g. 'column "yr" does not exist', without the whole query."""
    message = str(getattr(error, "orig", None) or error).strip()
    return message.splitlines()[0][:300] if message else type(error).__name__


# the tools the agent can call. each returns (text for the AI, step for the app, data if any)

def tool_run_sql(query: str) -> tuple[str, Step, pd.DataFrame | None]:
    try:
        checked = check_sql(query)
    except UnsafeQueryError as error:
        return f"Rejected by the safety check: {error}", Step("run_sql", query, f"rejected: {error}", False), None
    try:
        data = run_query(checked)
    except (SQLAlchemyError, pd.errors.DatabaseError) as error:  # pandas wraps db errors in its own type
        problem = first_line(error)
        return f"Database error: {problem}", Step("run_sql", checked, f"error: {problem}", False), None

    if data.empty:
        return ("The query ran but returned no rows. Check the table and the filter values.",
                Step("run_sql", checked, "no rows", False), data)
    shown = data.head(ROWS_SHOWN_TO_AI).to_csv(index=False)
    more = f"\n({len(data)} rows in total, first {ROWS_SHOWN_TO_AI} shown)" if len(data) > ROWS_SHOWN_TO_AI else ""
    rows = f"{len(data)} row{'s' if len(data) != 1 else ''}"
    return shown + more, Step("run_sql", checked, rows, True), data


def tool_distinct_values(table: str, column: str) -> tuple[str, Step, None]:
    detail = f"{table}.{column}"
    table = table.removeprefix(f"{SCHEMA}.")
    known = dict(table_columns().get(table, []))
    # only names that really exist get into the query, so nothing can be slipped in
    if table not in MART_TABLES or column not in known:
        problem = f"{detail} isn't a column of a mart table."
        return problem, Step("distinct_values", detail, problem, False), None
    try:
        values = run_query(
            f'select distinct "{column}" from {SCHEMA}.{table} order by 1 limit {MAX_DISTINCT_VALUES}'
        ).iloc[:, 0]
    except (SQLAlchemyError, pd.errors.DatabaseError) as error:
        problem = first_line(error)
        return f"Database error: {problem}", Step("distinct_values", detail, f"error: {problem}", False), None
    listed = ", ".join(str(value) for value in values)
    return listed, Step("distinct_values", detail, f"{len(values)} values", True), None


def use_tool(name: str, tool_input: dict) -> tuple[str, Step, pd.DataFrame | None]:
    if name == "run_sql":
        return tool_run_sql(str(tool_input.get("query", "")))
    if name == "distinct_values":
        return tool_distinct_values(str(tool_input.get("table", "")), str(tool_input.get("column", "")))
    return f"There is no tool called {name}.", Step(name, "", "unknown tool", False), None


# putting it together

def ask(question: str) -> AskResult:
    """Answer a question. Never raises, any problem comes back as a friendly message."""
    question = question.strip()
    if not question:
        return AskResult(question, "Please type a question.", ok=False)
    if len(question) > MAX_QUESTION_LENGTH:
        return AskResult(question, f"Please keep your question under {MAX_QUESTION_LENGTH} characters.", ok=False)

    steps: list[Step] = []
    sql, data = None, None  # the last query that returned rows, which is what the answer is based on
    try:
        system = AGENT_INSTRUCTIONS.format(schema=table_schemas(), notes=TABLE_NOTES, cannot_answer=CANNOT_ANSWER)
        messages = [{"role": "user", "content": [{"text": question}]}]

        for _ in range(MAX_TURNS):
            reply = call_model(system, messages)
            messages.append(reply)
            tool_calls = [block["toolUse"] for block in reply["content"] if "toolUse" in block]

            if not tool_calls:
                # no more tools wanted, so this is its answer
                answer = " ".join(block["text"] for block in reply["content"] if "text" in block).strip()
                if CANNOT_ANSWER in answer:
                    return AskResult(question, "I can only answer questions about house prices, sales and "
                                     "affordability by county. Try asking about a county or a year.",
                                     ok=False, steps=steps)
                if data is None:
                    # never answer from thin air, only from rows it actually got
                    return AskResult(question, "I couldn't find data to answer that. Try rewording your question.",
                                     sql=sql, ok=False, steps=steps)
                return AskResult(question, answer, sql=sql, data=data, steps=steps)

            # run every tool it asked for and send the results back
            results = []
            for call in tool_calls:
                output, step, rows = use_tool(call["name"], call.get("input", {}))
                log.info("%s %s -> %s", step.tool, step.detail.replace("\n", " "), step.outcome)
                steps.append(step)
                if step.tool == "run_sql" and step.worked:
                    sql, data = step.detail, rows
                results.append({"toolResult": {"toolUseId": call["toolUseId"], "content": [{"text": output}]}})
            messages.append({"role": "user", "content": results})

        return AskResult(question, "That took too many steps to work out. Try a simpler question.",
                         sql=sql, ok=False, steps=steps)

    except (ClientError, BotoCoreError) as error:
        log.exception("bedrock call failed: %s", error)
        return AskResult(question, "The AI service isn't available right now. Please try again in a minute.",
                         sql=sql, ok=False, steps=steps)
    except Exception as error:
        log.exception("ask failed: %s", error)
        return AskResult(question, "Something went wrong answering that. Please try again.",
                         sql=sql, ok=False, steps=steps)


if __name__ == "__main__":
    result = ask(" ".join(sys.argv[1:]) or "Which county had the highest median price in 2025?")
    print(result.answer)
    print("\nSteps:")
    for number, step in enumerate(result.steps, start=1):
        print(f"  {number}. {step.tool} -> {step.outcome}")
        print("     " + step.detail.replace("\n", "\n     "))
    if result.data is not None:
        print("\n" + result.data.head(10).to_string(index=False))
