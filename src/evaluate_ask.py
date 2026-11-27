"""Score the ask the data feature on 20 questions with known answers.

Each question has a hand-written SQL query that gets the right answer straight from
the database, so the answers stay correct after every monthly refresh. The AI gets
the question through the normal ask() flow and it counts as right if the correct
answer is in the top row of its result table (or, for a list, it has the same counties).

Needs the same .env settings as src/ask.py. Makes about 40 AI calls (a few cents).

    python src/evaluate_ask.py
    python src/evaluate_ask.py --model eu.amazon.nova-lite-v1:0    # try another model
"""

import argparse
import os
from datetime import date
from pathlib import Path

import pandas as pd

import ask

REPORT = Path(__file__).resolve().parents[1] / "docs" / "ask_evaluation.md"

# (question, query that gives the right answer)
# one row back = the answer is that one value, several rows = the answer is that list of counties
CASES = [
    ("Which county had the highest median price in 2025?",
     "select county from analytics.mart_median_price where year = 2025 order by median_price desc limit 1"),
    ("Which county had the lowest median price in 2025?",
     "select county from analytics.mart_median_price where year = 2025 order by median_price limit 1"),
    ("What was the median price in Dublin in 2025?",
     "select median_price from analytics.mart_median_price where county = 'Dublin' and year = 2025"),
    ("What was the median price in Galway in 2015?",
     "select median_price from analytics.mart_median_price where county = 'Galway' and year = 2015"),
    ("How many homes were sold in Cork in 2024?",
     "select sales_count from analytics.mart_median_price where county = 'Cork' and year = 2024"),
    ("Which county had the most sales in 2025?",
     "select county from analytics.mart_median_price where year = 2025 order by sales_count desc limit 1"),
    ("Which county is the most affordable for young people in 2025?",
     "select county from analytics.mart_affordability where year = 2025 order by price_to_earnings_age_25_29 limit 1"),
    ("Which county is the least affordable for young people in 2025?",
     "select county from analytics.mart_affordability where year = 2025 "
     "order by price_to_earnings_age_25_29 desc limit 1"),
    ("What was the price to earnings ratio for 25 to 29 year olds in Kildare in 2025?",
     "select round(price_to_earnings_age_25_29, 1) from analytics.mart_affordability "
     "where county = 'Kildare' and year = 2025"),
    ("Which 5 counties had the biggest percentage price rise in 2025?",
     "select county from analytics.mart_price_change where year = 2025 order by change_pct desc limit 5"),
    ("Which 3 counties were cheapest in 2025?",
     "select county from analytics.mart_median_price where year = 2025 order by median_price limit 3"),
    ("By what percentage did the median price in Dublin change in 2024?",
     "select round(change_pct, 1) from analytics.mart_price_change where county = 'Dublin' and year = 2024"),
    ("Which county had the biggest percentage price fall in 2012?",
     "select county from analytics.mart_price_change where year = 2012 order by change_pct limit 1"),
    ("What is the median price in Leitrim over the last 12 months?",
     "select median_price from analytics.mart_latest_price where county = 'Leitrim'"),
    ("Which county has the highest median price over the last 12 months?",
     "select county from analytics.mart_latest_price order by median_price desc limit 1"),
    ("How many homes were sold in all of Ireland in 2023?",
     "select sum(sales_count) from analytics.mart_median_price where year = 2023"),
    ("What were the median yearly earnings of 25 to 29 year olds in Mayo in 2025?",
     "select median_earnings_age_25_29 from analytics.mart_affordability where county = 'Mayo' and year = 2025"),
    ("In which year was the median price in Dublin at its lowest?",
     "select year from analytics.mart_median_price where county = 'Dublin' order by median_price limit 1"),
    ("How many counties had a median price above 400,000 euro in 2025?",
     "select count(*) from analytics.mart_median_price where year = 2025 and median_price > 400000"),
    ("What was the price to household income ratio in Wicklow in 2022?",
     "select round(price_to_household_income, 1) from analytics.mart_affordability "
     "where county = 'Wicklow' and year = 2022"),
]


def numbers_match(a, b) -> bool:
    """Close enough to allow for rounding: 0.05 for ratios and percentages, 0.1% for prices and counts."""
    try:
        a, b = float(a), float(b)
    except (TypeError, ValueError):
        return False
    return abs(a - b) <= max(0.051, abs(b) * 0.001)


def is_correct(expected: pd.DataFrame, got: pd.DataFrame | None) -> bool:
    if got is None or got.empty:
        return False
    if len(expected) == 1:
        # one answer: it has to be in the ai's top row. not anywhere in the table,
        # or listing every year would count as right for "which year was cheapest?"
        cells = got.iloc[0].tolist()
        answer = expected.iloc[0, 0]
        if isinstance(answer, str):
            return any(str(cell).strip().lower() == answer.lower() for cell in cells)
        return any(numbers_match(cell, answer) for cell in cells)

    # a list of counties: the ai's counties have to be exactly the same ones
    wanted = {county.lower() for county in expected.iloc[:, 0]}
    column = "county" if "county" in got.columns else got.columns[0]
    return {str(value).lower() for value in got[column]} == wanted


def shorten(data: pd.DataFrame | None) -> str:
    if data is None or data.empty:
        return "(no result)"
    first_column = data.iloc[:, 0].astype(str).tolist()
    if len(data) == 1:
        return ", ".join(str(value) for value in data.iloc[0].tolist())
    return ", ".join(first_column[:5]) + (" ..." if len(first_column) > 5 else "")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--model", help="Bedrock model id to test (default: BEDROCK_MODEL_ID from .env)")
    args = parser.parse_args()
    if args.model:
        os.environ["BEDROCK_MODEL_ID"] = args.model
    model = os.environ["BEDROCK_MODEL_ID"]

    print(f"Testing {model} on {len(CASES)} questions\n")
    rows = []
    for number, (question, truth_sql) in enumerate(CASES, start=1):
        expected = ask.run_query(truth_sql)
        result = ask.ask(question)
        correct = is_correct(expected, result.data)
        retries = len(result.attempts)
        rows.append((question, shorten(expected), shorten(result.data) if result.ok else result.answer,
                     correct, retries))
        retried = f"  ({retries} {'retry' if retries == 1 else 'retries'})" if retries else ""
        print(f"{'PASS' if correct else 'FAIL'}  {number:2}. {question}{retried}")
        if not correct:
            print(f"          expected: {shorten(expected)}")
            print(f"          got:      {rows[-1][2]}")

    score = sum(row[3] for row in rows)
    needed_fix = sum(row[4] > 0 for row in rows)
    print(f"\nScore: {score}/{len(CASES)} correct with {model}")
    print(f"{needed_fix} question(s) needed at least one retry")

    lines = [
        "# Ask the data: evaluation",
        "",
        f"**{score}/{len(CASES)} correct** with `{model}` on {date.today():%d %B %Y}. "
        f"{needed_fix} question(s) needed at least one retry.",
        "",
        "Made by `python src/evaluate_ask.py`. Right answers come from hand-written SQL run on the same "
        "database. An answer counts as correct when the right value is in the top row of the AI's "
        "result table, or for a list question, when it has exactly the same counties.",
        "",
        "| # | Question | Correct answer | AI's result | Retries | |",
        "|---|---|---|---|---|---|",
    ]
    for number, (question, expected, got, correct, retries) in enumerate(rows, start=1):
        got = got.replace("|", "/").replace("\n", " ")
        lines.append(f"| {number} | {question} | {expected} | {got} | {retries} | {'✅' if correct else '❌'} |")
    REPORT.parent.mkdir(exist_ok=True)
    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Report saved to {REPORT.relative_to(REPORT.parents[1])}")


if __name__ == "__main__":
    main()
