import pytest

from boekhouding.formatting import eur, fmt_qty, money_input, parse_money, parse_qty


@pytest.mark.parametrize("text, cents", [
    ("1.234,56", 123456), ("1234.56", 123456), ("€ 12", 1200), ("1\xa0000,00", 100000),
    ("-5,5", -550), ("", None),
])
def test_parse_money(text, cents):
    assert parse_money(text) == cents


def test_parse_money_invalid():
    with pytest.raises(ValueError):
        parse_money("abc")


def test_format():
    assert eur(123456) == "€ 1.234,56"
    assert eur(-550) == "€ -5,50"
    assert money_input(123456) == "1234,56"
    assert fmt_qty(2.5) == "2,5"
    assert parse_qty("1,5") == parse_qty("1.5")
