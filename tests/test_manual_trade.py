from decimal import Decimal

import pytest

from scripts.manual_trade import _parse_fraction, _raw_from_decimal


def test_parse_fraction_supports_default_sixteenth():
    assert _parse_fraction("1/16") == Decimal("0.0625")


def test_parse_fraction_rejects_fraction_above_one():
    with pytest.raises(ValueError):
        _parse_fraction("17/16")


def test_raw_conversion_rounds_down():
    assert _raw_from_decimal(Decimal("1.23456789"), 6) == 1234567

