# Ask the data: evaluation

**19/20 correct** with `eu.amazon.nova-lite-v1:0` on 26 November 2026.

Made by `python src/evaluate_ask.py`. Right answers come from hand-written SQL run on the same database. An answer counts as correct when the right value is in the top row of the AI's result table, or for a list question, when it has exactly the same counties.

| # | Question | Correct answer | AI's result | |
|---|---|---|---|---|
| 1 | Which county had the highest median price in 2025? | Dublin | Dublin, 499500.0 | ✅ |
| 2 | Which county had the lowest median price in 2025? | Longford | Longford, 200000.0 | ✅ |
| 3 | What was the median price in Dublin in 2025? | 499500.0 | 499500.0 | ✅ |
| 4 | What was the median price in Galway in 2015? | 140000.0 | 140000.0 | ✅ |
| 5 | How many homes were sold in Cork in 2024? | 6419 | (no result) | ❌ |
| 6 | Which county had the most sales in 2025? | Dublin | Dublin, 18485 | ✅ |
| 7 | Which county is the most affordable for young people in 2025? | Longford | Longford, 4.6 | ✅ |
| 8 | Which county is the least affordable for young people in 2025? | Dublin | Dublin, 12.0 | ✅ |
| 9 | What was the price to earnings ratio for 25 to 29 year olds in Kildare in 2025? | 10.5 | 10.5 | ✅ |
| 10 | Which 5 counties had the biggest percentage price rise in 2025? | Cavan, Leitrim, Tipperary, Laois, Louth | Cavan, Leitrim, Tipperary, Laois, Louth | ✅ |
| 11 | Which 3 counties were cheapest in 2025? | Longford, Donegal, Leitrim | Longford, Donegal, Leitrim | ✅ |
| 12 | By what percentage did the median price in Dublin change in 2024? | 9.8 | 9.8 | ✅ |
| 13 | Which county had the biggest percentage price fall in 2012? | Laois | Laois, -26.3 | ✅ |
| 14 | What is the median price in Leitrim over the last 12 months? | 230000.0 | 230000.0 | ✅ |
| 15 | Which county has the highest median price over the last 12 months? | Dublin | Dublin, 500000.0 | ✅ |
| 16 | How many homes were sold in all of Ireland in 2023? | 59707.0 | 59707.0 | ✅ |
| 17 | What were the median yearly earnings of 25 to 29 year olds in Mayo in 2025? | 40409 | 40409 | ✅ |
| 18 | In which year was the median price in Dublin at its lowest? | 2012 | 2012.0, 215000.0 | ✅ |
| 19 | How many counties had a median price above 400,000 euro in 2025? | 4 | 4 | ✅ |
| 20 | What was the price to household income ratio in Wicklow in 2022? | 6.4 | 6.4 | ✅ |
