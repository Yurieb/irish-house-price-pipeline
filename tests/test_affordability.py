"""Tests for the mortgage rules in the calculator."""

from affordability import limiting_factor, max_mortgage, max_price


def test_first_time_buyer_can_borrow_four_times_income():
    assert max_mortgage(50_000, first_time_buyer=True) == 200_000


def test_other_buyers_can_borrow_three_and_a_half_times_income():
    assert max_mortgage(50_000, first_time_buyer=False) == 175_000


def test_price_is_limited_by_income_when_the_deposit_is_large():
    # 200,000 mortgage + 100,000 deposit = 300,000
    # deposit could cover 1,000,000 so income is the limit
    assert max_price(50_000, 100_000, first_time_buyer=True) == 300_000
    assert limiting_factor(50_000, 100_000, first_time_buyer=True) == "income"


def test_price_is_limited_by_deposit_when_the_deposit_is_small():
    # income allows 210,000 but a 10,000 deposit only covers a 100,000 home
    assert max_price(50_000, 10_000, first_time_buyer=True) == 100_000
    assert limiting_factor(50_000, 10_000, first_time_buyer=True) == "deposit"


def test_no_deposit_means_no_purchase():
    assert max_price(50_000, 0, first_time_buyer=True) == 0
