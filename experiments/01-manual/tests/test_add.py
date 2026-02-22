import pytest

from add import add


def test_two_positive_integers():
    assert add(2, 3) == 5


def test_two_negative_integers():
    assert add(-4, -7) == -11


def test_mixed_signs():
    assert add(-3, 10) == 7


def test_two_floats():
    assert add(1.5, 2.5) == pytest.approx(4.0)


def test_integer_and_float():
    assert add(2, 3.5) == pytest.approx(5.5)
