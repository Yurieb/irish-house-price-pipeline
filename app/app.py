"""Streamlit app - where in Ireland can a young person afford a home?

Needs the database running and the dbt models built. Run with:
    streamlit run app/app.py
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# so we can import db.py from src/
sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))

from affordability import limiting_factor, max_mortgage, max_price
from ask import MAX_QUESTION_LENGTH, ask
from charts import county_map, trend_chart
from db import get_engine

CENTRAL_BANK_URL = (
    "https://www.centralbank.ie/financial-system/financial-stability/"
    "macro-prudential-policy/mortgage-measures"
)
MAX_COUNTIES_ON_CHART = 4
EXAMPLE_QUESTIONS = [
    "Which county is the most affordable for young people in 2025?",
    "Which 5 counties had the biggest price rise in 2025?",
    "How has the median price in Dublin changed since 2015?",
]

st.set_page_config(page_title="Irish Home Affordability", page_icon="🏠", layout="wide")


@st.cache_data(ttl=3600)
def load_table(table: str) -> pd.DataFrame:
    """Read a mart table. Cached for an hour so we don't hit the db on every click."""
    return pd.read_sql(f"select * from analytics.{table}", get_engine())


@st.cache_data(ttl=3600, max_entries=200, show_spinner=False)
def cached_ask(question: str):
    """Same question within the hour gets the saved answer instead of another AI call."""
    return ask(question)


def euro(amount: float) -> str:
    return f"€{amount:,.0f}"


def long_date(date) -> str:
    """Format a date like 6 November 2026."""
    return f"{date.day} {date:%B %Y}"


latest = load_table("mart_latest_price")
yearly = load_table("mart_price_change")
affordability = load_table("mart_affordability")

period_start = latest["period_start"].iloc[0]
period_end = latest["period_end"].iloc[0]

# header

st.title("Where in Ireland can a young person afford a home?")
st.caption(
    f"Data last updated: sales recorded up to {long_date(period_end)}. "
    "Sources: Property Price Register and Central Statistics Office."
)

# calculator

st.header("Affordability calculator")

inputs, results = st.columns([1, 2], gap="large")

with inputs:
    income = st.number_input(
        "Gross annual income (€)", min_value=0, value=45_000, step=1_000,
        help="Before tax. If you are buying with someone, add both incomes together.",
    )
    deposit = st.number_input("Deposit (€)", min_value=0, value=30_000, step=1_000)
    first_time_buyer = st.checkbox("First-time buyer", value=True)

mortgage = max_mortgage(income, first_time_buyer)
budget = max_price(income, deposit, first_time_buyer)

latest = latest.assign(affordable=latest["median_price"] <= budget)
affordable_count = int(latest["affordable"].sum())

with results:
    left, middle, right = st.columns(3)
    left.metric("Maximum mortgage", euro(mortgage))
    middle.metric("Maximum price", euro(budget))
    right.metric("Counties within budget", f"{affordable_count} of {len(latest)}")

    if limiting_factor(income, deposit, first_time_buyer) == "deposit":
        st.info(
            f"Your deposit is what limits you. Lenders need at least 10% of the price, "
            f"so {euro(deposit)} supports a home of up to {euro(budget)}."
        )
    else:
        multiple = "4" if first_time_buyer else "3.5"
        st.info(
            f"Your income is what limits you. Lenders can lend up to {multiple} times "
            f"gross income, which is {euro(mortgage)}, plus your deposit."
        )

map_column, table_column = st.columns([3, 2], gap="large")

with map_column:
    st.altair_chart(county_map(latest), width="stretch")

with table_column:
    table = latest.sort_values("median_price")[["county", "median_price", "sales_count", "affordable"]]
    table["gap"] = budget - table["median_price"]
    st.dataframe(
        table,
        hide_index=True,
        height=520,
        column_config={
            "county": "County",
            "median_price": st.column_config.NumberColumn("Median price", format="€%,.0f"),
            "sales_count": st.column_config.NumberColumn("Sales", format="%,d"),
            "affordable": st.column_config.CheckboxColumn("Within budget"),
            "gap": st.column_config.NumberColumn("Budget minus price", format="€%,.0f"),
        },
    )

st.caption(
    f"A county is within budget when its median sale price is at or below your maximum "
    f"price. Median prices cover the 12 months from {long_date(period_start)} to "
    f"{long_date(period_end)}. Half of homes in a county sold for less than its median."
)

# trend charts

st.header("How prices have changed")

chosen = st.multiselect(
    "Counties to compare",
    options=sorted(yearly["county"].unique()),
    default=["Dublin", "Cork", "Galway", "Leitrim"],
    max_selections=MAX_COUNTIES_ON_CHART,
)

if not chosen:
    st.warning("Choose at least one county to see the charts.")
else:
    # keep counties in the order they were picked so the colours don't change
    def selected(data: pd.DataFrame) -> pd.DataFrame:
        data = data[data["county"].isin(chosen)]
        return data.sort_values("year").sort_values(
            "county", key=lambda column: column.map(chosen.index), kind="stable"
        )

    price_tab, ratio_tab, change_tab = st.tabs(
        ["Median price", "Price compared with earnings", "Yearly change"]
    )

    with price_tab:
        st.altair_chart(
            trend_chart(selected(yearly), "median_price", "Median price (€)", ",.0f"),
            width="stretch",
        )

    with ratio_tab:
        st.altair_chart(
            trend_chart(
                selected(affordability), "price_to_earnings_age_25_29",
                "Median price ÷ earnings, age 25–29", ".1f",
            ),
            width="stretch",
        )
        st.caption(
            "How many years of gross earnings the median home costs, for one person "
            "aged 25 to 29 living in that county. Higher means less affordable."
        )

    with change_tab:
        st.altair_chart(
            trend_chart(
                selected(yearly.dropna(subset=["change_pct"])), "change_pct",
                "Change on previous year (%)", ".1f",
            ),
            width="stretch",
        )

    st.caption(
        f"{period_end:%Y} is a part-year: it only includes sales up to {long_date(period_end)}."
    )

# ask the data

st.header("Ask the data")
st.caption(
    "Ask a question in plain English. An AI writes a database query, it's checked to make sure "
    "it only reads the summary tables, and the result is summed up for you. AI can get things "
    "wrong, so check the table and the query below the answer."
)


# the buttons only flag that a question is waiting, the AI call happens further down
# so it can show a spinner in the right place
def ask_typed_question():
    st.session_state.ask_pending = True


def ask_example(question: str):
    st.session_state.ask_box = question
    st.session_state.ask_pending = True


st.text_input(
    "Your question",
    key="ask_box",
    max_chars=MAX_QUESTION_LENGTH,
    placeholder="e.g. What was the median price in Galway in 2024?",
    on_change=ask_typed_question,  # pressing enter asks too
)

with st.container(horizontal=True):
    st.button("Ask", type="primary", icon=":material/send:", on_click=ask_typed_question)
    for example in EXAMPLE_QUESTIONS:
        st.button(example, on_click=ask_example, args=(example,))

if st.session_state.pop("ask_pending", False) and st.session_state.ask_box.strip():
    with st.spinner("Working it out..."):
        st.session_state.ask_result = cached_ask(st.session_state.ask_box.strip())

result = st.session_state.get("ask_result")
if result:
    st.markdown(f"**{result.question}**")
    if result.ok:
        st.success(result.answer, icon=":material/chat:")
    else:
        st.warning(result.answer)

    if result.data is not None and not result.data.empty:
        st.dataframe(result.data, hide_index=True, alt=f"Query result for: {result.question}")
    if result.sql:
        with st.expander("Show the SQL query", icon=":material/code:"):
            st.code(result.sql, language="sql")
            # if the AI had to fix its query, show what it tried first and why that didn't work
            for number, attempt in enumerate(result.attempts, start=1):
                st.caption(f"Attempt {number} didn't work. {attempt.problem}")
                st.code(attempt.sql, language="sql")

# notes

st.header("How this works")

st.markdown(
    f"""
- **Mortgage rules.** The calculator applies the
  [Central Bank of Ireland mortgage measures]({CENTRAL_BANK_URL}): a loan of at most
  4 times gross income for first-time buyers (3.5 times for other buyers), and a
  deposit of at least 10% of the price.
- **Prices.** Every residential sale in the Property Price Register since 2010,
  excluding sales not at full market price. New-build prices include VAT.
- **Earnings.** Median annual earnings by county and age group, from the Central
  Statistics Office.
- **What it leaves out.** Stamp duty, legal fees, and schemes such as Help to Buy
  and the First Home Scheme. Lenders can also make exceptions to the limits, and
  will check that you can afford the repayments. This is a guide, not financial advice.
"""
)
