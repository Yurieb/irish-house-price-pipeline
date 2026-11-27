"""Tests for the ask the data feature.

The AI and the database are swapped for fakes with monkeypatch, so these run
offline and cost nothing (CI has no AWS keys or database).
"""

import pandas as pd
import pytest
from botocore.exceptions import ClientError
from sqlalchemy.exc import OperationalError

import ask
from ask import UnsafeQueryError, check_sql

GOOD_SQL = "select county, median_price from analytics.mart_latest_price order by median_price"


# checking the query

@pytest.mark.parametrize("query", [
    "DROP TABLE analytics.mart_latest_price",
    "insert into analytics.mart_latest_price (county) values ('x')",
    "update analytics.mart_latest_price set median_price = 1",
    "delete from analytics.mart_latest_price",
    "truncate analytics.mart_latest_price",
    "create table analytics.x as select * from analytics.mart_latest_price",
    "select * into analytics.copy from analytics.mart_latest_price",
    # two statements, the second one sneaks in a write
    "select 1 from analytics.mart_latest_price; drop table analytics.mart_latest_price",
    # a write hidden inside a WITH
    "with d as (delete from analytics.mart_latest_price returning *) select * from d",
])
def test_rejects_queries_that_change_data(query):
    with pytest.raises(UnsafeQueryError):
        check_sql(query)


@pytest.mark.parametrize("query", [
    "select * from raw.ppr_sales",
    "select * from analytics.stg_ppr_sales",
    "select * from pg_catalog.pg_roles",
    "select * from information_schema.tables",
    # mart name but the wrong schema
    "select * from public.mart_latest_price",
    # one good table joined to a bad one
    "select * from analytics.mart_latest_price m join raw.ppr_sales r on m.county = r.county",
])
def test_rejects_tables_that_arent_marts(query):
    with pytest.raises(UnsafeQueryError, match="isn't one of the mart tables"):
        check_sql(query)


def test_rejects_text_that_isnt_sql():
    with pytest.raises(UnsafeQueryError):
        check_sql("this is not sql")


@pytest.mark.parametrize("query", [
    GOOD_SQL,
    # extract(year from ...) has the word "from" in it, a simple text search would get confused
    "select extract(year from period_end) as y from analytics.mart_latest_price",
    # names made with WITH are fine
    "with t as (select * from analytics.mart_median_price) select county from t",
    "select a.county from analytics.mart_affordability a "
    "join analytics.mart_price_change p on a.county = p.county and a.year = p.year",
])
def test_allows_read_only_queries_on_marts(query):
    assert check_sql(query).upper().startswith(("SELECT", "WITH"))


def test_adds_a_limit_when_there_isnt_one():
    assert "LIMIT 100" in check_sql(GOOD_SQL)


def test_caps_a_limit_that_is_too_high():
    assert "LIMIT 100" in check_sql(GOOD_SQL + " limit 5000")


def test_keeps_a_smaller_limit():
    checked = check_sql(GOOD_SQL + " limit 5")
    assert "LIMIT 5" in checked
    assert "LIMIT 100" not in checked


# the agent, with a fake AI and a fake database

LONGFORD = pd.DataFrame({"county": ["Longford"], "median_price": [210_000]})
NO_ROWS = pd.DataFrame({"county": []})
ANSWER = "Longford is the cheapest county, at €210,000."
COLUMNS = {
    "mart_latest_price": [("county", "text"), ("median_price", "numeric")],
    "mart_median_price": [("county", "text"), ("year", "integer"), ("median_price", "numeric")],
}


def sql_call(query):
    """What the model sends back when it wants to run a query."""
    return {"role": "assistant", "content": [{"toolUse": {
        "toolUseId": "t1", "name": "run_sql", "input": {"query": query}}}]}


def tool_call(name, **tool_input):
    return {"role": "assistant", "content": [{"toolUse": {"toolUseId": "t1", "name": name, "input": tool_input}}]}


def says(text):
    """What the model sends back when it has finished."""
    return {"role": "assistant", "content": [{"text": text}]}


@pytest.fixture
def fake(monkeypatch):
    """Replace the AI and the database.

    fake.script is what the AI does, one reply per turn (the last one repeats).
    fake.results is what the database returns, one per query (the last one repeats).
    fake.seen keeps the tool results the AI was sent, so tests can check what it was told.
    """

    class Fake:
        script = [sql_call(GOOD_SQL), says(ANSWER)]
        results = [LONGFORD]
        queries_run = []
        seen = []
        ai_calls = 0

    def fake_model(system, messages):
        Fake.ai_calls += 1
        last = messages[-1]["content"][0]
        if "toolResult" in last:
            Fake.seen.append(last["toolResult"]["content"][0]["text"])
        return Fake.script.pop(0) if len(Fake.script) > 1 else Fake.script[0]

    def fake_run_query(query):
        Fake.queries_run.append(query)
        return Fake.results.pop(0) if len(Fake.results) > 1 else Fake.results[0]

    monkeypatch.setattr(ask, "call_model", fake_model)
    monkeypatch.setattr(ask, "run_query", fake_run_query)
    monkeypatch.setattr(ask, "table_columns", lambda: COLUMNS)
    return Fake


def test_answers_a_question(fake):
    result = ask.ask("Which county is cheapest?")

    assert result.ok
    assert result.answer == ANSWER
    assert "LIMIT 100" in result.sql
    assert result.data["county"].tolist() == ["Longford"]
    assert [step.tool for step in result.steps] == ["run_sql"]
    # the AI was sent the rows it asked for
    assert "Longford" in fake.seen[0]


def test_unsafe_query_is_never_run(fake):
    fake.script = [sql_call("drop table analytics.mart_latest_price"), says("Done, I deleted it.")]

    result = ask.ask("delete everything")

    assert fake.queries_run == []
    assert "Rejected by the safety check" in fake.seen[0]
    # it never got any rows, so it isn't allowed to answer
    assert not result.ok
    assert result.answer != "Done, I deleted it."
    assert not result.steps[0].worked


def test_wont_answer_without_running_a_query(fake):
    # a made-up answer with no data behind it
    fake.script = [says("Longford, definitely.")]

    result = ask.ask("Which county is cheapest?")

    assert not result.ok
    assert "couldn't find data" in result.answer


def test_question_the_data_cant_answer(fake):
    fake.script = [says("CANNOT_ANSWER")]

    result = ask.ask("What's the weather in Galway?")

    assert not result.ok
    assert "house prices" in result.answer
    assert fake.queries_run == []


@pytest.mark.parametrize("question", ["", "   ", "x" * (ask.MAX_QUESTION_LENGTH + 1)])
def test_empty_or_long_questions_dont_call_the_ai(fake, question):
    result = ask.ask(question)

    assert not result.ok
    assert fake.ai_calls == 0


def test_stops_after_too_many_turns(fake):
    # an AI that never stops calling tools
    fake.script = [sql_call(GOOD_SQL)]

    result = ask.ask("Which county is cheapest?")

    assert not result.ok
    assert "too many steps" in result.answer
    assert fake.ai_calls == ask.MAX_TURNS


# fixing its own mistakes

def test_tries_again_after_a_rejected_query(fake):
    fake.script = [sql_call("select * from raw.ppr_sales"), sql_call(GOOD_SQL), says(ANSWER)]

    result = ask.ask("Which county is cheapest?")

    assert result.ok
    # it was told why, and the rejected query was never run
    assert "raw.ppr_sales" in fake.seen[0]
    assert len(fake.queries_run) == 1
    assert [step.worked for step in result.steps] == [False, True]


def test_tries_again_after_no_rows(fake):
    fake.script = [sql_call(GOOD_SQL), sql_call(GOOD_SQL + " limit 5"), says(ANSWER)]
    fake.results = [NO_ROWS, LONGFORD]

    result = ask.ask("Which county is cheapest?")

    assert result.ok
    assert "no rows" in fake.seen[0]
    assert result.data["county"].tolist() == ["Longford"]


def test_tries_again_after_a_database_error(fake, monkeypatch):
    calls = []

    def fails_once(query):
        calls.append(query)
        if len(calls) == 1:
            raise OperationalError(query, {}, Exception('column "yr" does not exist'))
        return LONGFORD

    monkeypatch.setattr(ask, "run_query", fails_once)
    fake.script = [sql_call(GOOD_SQL), sql_call(GOOD_SQL), says(ANSWER)]

    result = ask.ask("Which county is cheapest?")

    assert result.ok
    assert 'column "yr" does not exist' in fake.seen[0]


# the distinct_values tool

def test_distinct_values_lists_a_column(fake):
    fake.script = [tool_call("distinct_values", table="mart_median_price", column="year"),
                   sql_call(GOOD_SQL), says(ANSWER)]
    fake.results = [pd.DataFrame({"year": [2024, 2025]}), LONGFORD]

    result = ask.ask("Which county was cheapest in 2025?")

    assert result.ok
    assert fake.seen[0] == "2024, 2025"
    assert fake.queries_run[0] == 'select distinct "year" from analytics.mart_median_price order by 1 limit 50'


@pytest.mark.parametrize("table, column", [
    ("ppr_sales", "price"),                      # not a mart
    ("mart_median_price", "password"),           # not a real column
    ("mart_median_price", 'year"; drop table x; --'),  # trying to sneak sql in
])
def test_distinct_values_only_allows_real_mart_columns(fake, table, column):
    fake.script = [tool_call("distinct_values", table=table, column=column), says(ANSWER)]

    ask.ask("Which county is cheapest?")

    assert fake.queries_run == []
    assert "isn't a column of a mart table" in fake.seen[0]


# when things outside our control break

def test_ai_service_down_gives_a_friendly_message(fake, monkeypatch):
    def broken_model(system, messages):
        raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse")

    monkeypatch.setattr(ask, "call_model", broken_model)

    result = ask.ask("Which county is cheapest?")

    assert not result.ok
    assert "AI service" in result.answer
