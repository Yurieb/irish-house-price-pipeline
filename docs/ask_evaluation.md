# Ask the data: evaluation

**20/20 correct** with `eu.amazon.nova-pro-v1:0` on 27 November 2026. The agent made 21 tool calls in total, and 1 question(s) had a call that didn't work (rejected, an error, or no rows) before it carried on.

Made by `python src/evaluate_ask.py`. Right answers come from hand-written SQL run on the same database. An answer counts as correct when the right value is in the top row of the AI's result table, or for a list question, when it has exactly the same counties.

| # | Question | Correct answer | AI's result | Tool calls | |
|---|---|---|---|---|---|
| 1 | Which county had the highest median price in 2025? | Dublin | Dublin, 499500.0 | 1 | ✅ |
| 2 | Which county had the lowest median price in 2025? | Longford | Longford, 185000.0 | 1 | ✅ |
| 3 | What was the median price in Dublin in 2025? | 499500.0 | 499500.0 | 1 | ✅ |
| 4 | What was the median price in Galway in 2015? | 140000.0 | 140000.0 | 1 | ✅ |
| 5 | How many homes were sold in Cork in 2024? | 6419 | 6419 | 1 | ✅ |
| 6 | Which county had the most sales in 2025? | Dublin | Dublin, 18485 | 1 | ✅ |
| 7 | Which county is the most affordable for young people in 2025? | Longford | Longford, 4.6 | 1 | ✅ |
| 8 | Which county is the least affordable for young people in 2025? | Dublin | Dublin, 12.0 | 1 | ✅ |
| 9 | What was the price to earnings ratio for 25 to 29 year olds in Kildare in 2025? | 10.5 | 10.5 | 1 | ✅ |
| 10 | Which 5 counties had the biggest percentage price rise in 2025? | Cavan, Leitrim, Tipperary, Laois, Louth | Cavan, Leitrim, Tipperary, Laois, Louth | 1 | ✅ |
| 11 | Which 3 counties were cheapest in 2025? | Longford, Donegal, Leitrim | Longford, Donegal, Leitrim | 1 | ✅ |
| 12 | By what percentage did the median price in Dublin change in 2024? | 9.8 | 9.8 | 1 | ✅ |
| 13 | Which county had the biggest percentage price fall in 2012? | Laois | Laois, -26.3 | 1 | ✅ |
| 14 | What is the median price in Leitrim over the last 12 months? | 230000.0 | 230000.0 | 1 | ✅ |
| 15 | Which county has the highest median price over the last 12 months? | Dublin | Dublin, 500000.0 | 2 (1 didn't work) | ✅ |
| 16 | How many homes were sold in all of Ireland in 2023? | 59707.0 | 59707.0 | 1 | ✅ |
| 17 | What were the median yearly earnings of 25 to 29 year olds in Mayo in 2025? | 40409 | 40409 | 1 | ✅ |
| 18 | In which year was the median price in Dublin at its lowest? | 2012 | 2012.0, 215000.0 | 1 | ✅ |
| 19 | How many counties had a median price above 400,000 euro in 2025? | 4 | 4 | 1 | ✅ |
| 20 | What was the price to household income ratio in Wicklow in 2022? | 6.4 | 6.4 | 1 | ✅ |
