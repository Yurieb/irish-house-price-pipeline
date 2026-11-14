"""Altair charts for the Streamlit app."""

import copy
import json
from pathlib import Path

import altair as alt
import pandas as pd

GEOJSON_FILE = Path(__file__).resolve().parent / "ireland_counties.geojson"

# colours for the lines, picked to be colour-blind friendly (max 4 counties)
LINE_COLOURS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
AFFORDABLE_COLOUR = "#2a78d6"
NOT_AFFORDABLE_COLOUR = "#d9d8d2"
MAP_BORDER_COLOUR = "#fcfcfb"


def county_map(prices: pd.DataFrame) -> alt.Chart:
    """Map of the 26 counties, coloured by whether the buyer can afford them.

    prices needs columns: county, median_price, affordable
    """
    counties = json.loads(GEOJSON_FILE.read_text(encoding="utf-8"))["features"]
    by_county = prices.set_index("county")

    # add each county's price and status to its shape so the map can use them
    features = copy.deepcopy(counties)
    for feature in features:
        row = by_county.loc[feature["properties"]["county"]]
        feature["properties"]["median_price"] = float(row["median_price"])
        feature["properties"]["status"] = "Within budget" if row["affordable"] else "Over budget"

    return (
        alt.Chart(alt.Data(values=features))
        .mark_geoshape(stroke=MAP_BORDER_COLOUR, strokeWidth=1.5)
        .encode(
            color=alt.Color(
                "properties.status:N",
                scale=alt.Scale(
                    domain=["Within budget", "Over budget"],
                    range=[AFFORDABLE_COLOUR, NOT_AFFORDABLE_COLOUR],
                ),
                legend=alt.Legend(title=None, orient="top"),
            ),
            tooltip=[
                alt.Tooltip("properties.county:N", title="County"),
                alt.Tooltip("properties.median_price:Q", title="Median price (€)", format=",.0f"),
                alt.Tooltip("properties.status:N", title="For you"),
            ],
        )
        .project(type="mercator")
        .properties(height=520)
    )


def trend_chart(data: pd.DataFrame, column: str, title: str, number_format: str) -> alt.LayerChart:
    """Line chart of a column by year, one line per county.

    data needs columns: county, year, and the column being plotted
    """
    counties = list(dict.fromkeys(data["county"]))
    colour = alt.Color(
        "county:N",
        scale=alt.Scale(domain=counties, range=LINE_COLOURS[: len(counties)]),
        legend=alt.Legend(title=None, orient="top"),
    )
    base = alt.Chart(data).encode(
        x=alt.X("year:O", title=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y(f"{column}:Q", title=title, axis=alt.Axis(format=number_format)),
        color=colour,
    )

    lines = base.mark_line(strokeWidth=2)
    points = base.mark_point(size=60, filled=True, opacity=1).encode(
        tooltip=[
            alt.Tooltip("county:N", title="County"),
            alt.Tooltip("year:O", title="Year"),
            alt.Tooltip(f"{column}:Q", title=title, format=number_format),
        ]
    )
    return (lines + points).properties(height=360)
