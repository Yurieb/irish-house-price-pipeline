"""Tests for the ask the data feature.

The AI and the database are swapped for fakes with monkeypatch, so these run
offline and cost nothing (CI has no AWS keys or database).
"""

import pandas as pd
import pytest
from botocore.exceptions import ClientError
from sqlalchemy.exc import OperationalError

import ask
from ask import UnsafeQueryError, check_sql, clean_reply

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


def test_clean_reply_strips_markdown_fences():
    assert clean_reply("```sql\nselect 1\n```") == "select 1"
    assert clean_reply("  select 1  ") == "select 1"


# the whole ask() flow, with a fake AI and a fake database

SUMMARY = "Longford is the cheapest county."
LONGFORD = pd.DataFrame({"county": ["Longford"], "median_price": [210_000]})


@pytest.fixture
def fake(monkeypatch):
    """Replace the AI and the database.

    fake.replies are the queries the AI writes, one per try (the last one repeats).
    fake.results are what the database returns, one per query run (the last one repeats).
    """

    class Fake:
        replies = [GOOD_SQL]
        results = [LONGFORD]
        queries_run = []
        messages = []
        ai_calls = 0

    def fake_model(instructions, message):
        Fake.ai_calls += 1
        if instructions == ask.SUMMARY_INSTRUCTIONS:
            return SUMMARY
        Fake.messages.append(message)
        return Fake.replies.pop(0) if len(Fake.replies) > 1 else Fake.replies[0]

    def fake_run_query(query):
        Fake.queries_run.append(query)
        return Fake.results.pop(0) if len(Fake.results) > 1 else Fake.results[0]

    monkeypatch.setattr(ask, "call_model", fake_model)
    monkeypatch.setattr(ask, "run_query", fake_run_query)
    monkeypatch.setattr(ask, "table_schemas", lambda: "- analytics.mart_latest_price (county text)")
    return Fake


def test_ask_answers_a_question(fake):
    result = ask.ask("Which county is cheapest?")

    assert result.ok
    assert result.answer == SUMMARY
    assert "LIMIT 100" in result.sql
    assert result.data["county"].tolist() == ["Longford"]
    assert len(fake.queries_run) == 1
    assert result.attempts == []


def test_unsafe_ai_query_is_never_run(fake):
    # the AI keeps writing the same bad query on every try
    fake.replies = ["drop table analytics.mart_latest_price"]

    result = ask.ask("delete everything")

    assert not result.ok
    assert "safe query" in result.answer
    assert fake.queries_run == []
    # the rejected query is still shown so people can see what the AI tried
    assert result.sql == "drop table analytics.mart_latest_price"
    # it gave up after the maximum number of tries
    assert len(fake.messages) == ask.MAX_ATTEMPTS


# fixing its own mistakes

def test_fixes_a_query_the_safety_check_rejected(fake):
    fake.replies = ["select * from raw.ppr_sales", GOOD_SQL]

    result = ask.ask("Which county is cheapest?")

    assert result.ok
    assert len(result.attempts) == 1
    assert "raw.ppr_sales" in result.attempts[0].problem
    # the retry told the AI what was wrong
    assert "raw.ppr_sales" in fake.messages[1]
    # the rejected query was never run
    assert len(fake.queries_run) == 1


def test_fixes_a_query_that_found_no_rows(fake):
    fake.results = [pd.DataFrame({"county": []}), LONGFORD]

    result = ask.ask("Which county is cheapest?")

    assert result.ok
    assert result.data["county"].tolist() == ["Longford"]
    assert len(result.attempts) == 1
    assert "no rows" in result.attempts[0].problem
    assert "no rows" in fake.messages[1]


def test_fixes_a_query_the_database_couldnt_run(fake, monkeypatch):
    calls = []

    def fails_once(query):
        calls.append(query)
        if len(calls) == 1:
            raise OperationalError(query, {}, Exception('column "yr" does not exist'))
        return LONGFORD

    monkeypatch.setattr(ask, "run_query", fails_once)

    result = ask.ask("Which county is cheapest?")

    assert result.ok
    assert 'column "yr" does not exist' in fake.messages[1]


def test_still_no_rows_after_every_try_says_no_data(fake):
    fake.results = [pd.DataFrame({"county": []})]

    result = ask.ask("Which counties cost over 5 million?")

    # an empty answer can be the right answer, so it still replies rather than erroring
    assert result.ok
    assert len(fake.queries_run) == ask.MAX_ATTEMPTS
    assert len(result.attempts) == ask.MAX_ATTEMPTS - 1


def test_question_the_data_cant_answer(fake):
    fake.replies = ["CANNOT_ANSWER"]

    result = ask.ask("What's the weather in Galway?")

    assert not result.ok
    assert "house prices" in result.answer
    assert fake.queries_run == []


@pytest.mark.parametrize("question", ["", "   ", "x" * (ask.MAX_QUESTION_LENGTH + 1)])
def test_empty_or_long_questions_dont_call_the_ai(fake, question):
    result = ask.ask(question)

    assert not result.ok
    assert fake.ai_calls == 0


def test_ai_service_down_gives_a_friendly_message(fake, monkeypatch):
    def broken_model(instructions, message):
        raise ClientError({"Error": {"Code": "ThrottlingException", "Message": "slow down"}}, "Converse")

    monkeypatch.setattr(ask, "call_model", broken_model)

    result = ask.ask("Which county is cheapest?")

    assert not result.ok
    assert "AI service" in result.answer


def test_database_error_gives_a_friendly_message(fake, monkeypatch):
    def broken_query(query):
        raise OperationalError(query, {}, Exception("canceling statement due to statement timeout"))

    monkeypatch.setattr(ask, "run_query", broken_query)

    result = ask.ask("Which county is cheapest?")

    assert not result.ok
    assert "database" in result.answer
