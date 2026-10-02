"""Cortes e taxas por ano (E4.4)."""

import pytest
from hypothesis import given
from hypothesis import strategies as st

from curvas.engine.annual import (
    annualize,
    compound,
    cuts_fixed_252,
    forward_rate,
    forward_rates_at_cuts,
    product_of_one_plus,
)
from curvas.engine.curves import GridLookupError, accumulate_recursive


def test_cortes_252() -> None:
    assert cuts_fixed_252(231, 11) == (231, 483, 735, 987, 1239, 1491, 1743, 1995, 2247, 2499, 2751)
    assert cuts_fixed_252(62, 3) == (62, 314, 566)
    with pytest.raises(ValueError, match="n_cuts"):
        cuts_fixed_252(1, 0)


def test_forward_entre_cortes() -> None:
    acc = accumulate_recursive((0.1,) * 600)
    rates = forward_rates_at_cuts(acc, (100, 352, 600))
    assert rates[0] == pytest.approx(0.1, abs=1e-12)
    assert len(rates) == 2


def test_corte_fora_da_grade() -> None:
    with pytest.raises(GridLookupError):
        forward_rates_at_cuts((0.0,) * 10, (0, 5))


@given(
    st.floats(min_value=-0.5, max_value=3.0),
    st.floats(min_value=-0.5, max_value=3.0),
)
def test_forward_inverte_composicao(a: float, b: float) -> None:
    f = forward_rate(b, a)
    assert (1 + a) * (1 + f) == pytest.approx(1 + b, rel=1e-12)


def test_anualizacao() -> None:
    assert annualize(0.21, 0.5) == pytest.approx(0.1, abs=1e-15)
    assert annualize(0.05, 1) == (1 + 0.05) ** 1 - 1  # mesma ordem do Excel, não 0.05 exato


def test_composicao_mensal() -> None:
    assert compound([0.0033, 0.007, 0.0088]) == pytest.approx(0.01921394328, abs=1e-11)
    assert product_of_one_plus([]) == 1.0
