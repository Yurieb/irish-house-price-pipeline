"""Central Bank of Ireland mortgage rules.

Source: https://www.centralbank.ie/financial-system/financial-stability/macro-prudential-policy/mortgage-measures
"""

# LTI limit - max mortgage as a multiple of gross income
LTI_FIRST_TIME_BUYER = 4.0
LTI_OTHER_BUYER = 3.5

# LTV limit is 90%, so you need at least a 10% deposit
MIN_DEPOSIT_SHARE = 0.10


def max_mortgage(gross_income: float, first_time_buyer: bool) -> float:
    """Max mortgage under the loan-to-income limit."""
    multiple = LTI_FIRST_TIME_BUYER if first_time_buyer else LTI_OTHER_BUYER
    return gross_income * multiple


def max_price(gross_income: float, deposit: float, first_time_buyer: bool) -> float:
    """Highest price the buyer can pay.

    Limited by income (mortgage + deposit) or by deposit (deposit / 10%),
    whichever is lower.
    """
    income_limit = max_mortgage(gross_income, first_time_buyer) + deposit
    deposit_limit = deposit / MIN_DEPOSIT_SHARE
    return min(income_limit, deposit_limit)


def limiting_factor(gross_income: float, deposit: float, first_time_buyer: bool) -> str:
    """Returns 'income' or 'deposit', whichever limit is lower."""
    income_limit = max_mortgage(gross_income, first_time_buyer) + deposit
    deposit_limit = deposit / MIN_DEPOSIT_SHARE
    return "deposit" if deposit_limit < income_limit else "income"
