"""Taxas por ano a partir de acumulados diários (funções puras)."""

import math
from collections.abc import Sequence

from curvas.engine.curves import BUSINESS_DAYS_PER_YEAR, grid_value


def cuts_fixed_252(first_cut: int, n_cuts: int) -> tuple[int, ...]:
    """Cortes ``d₁ = YTG`` e ``dₙ = dₙ₋₁ + 252`` (E4.4).

    Espelha ``DI!R28 = R26+252``, ``R29 = R28+252`` … e ``CDS!I10 = I9+252`` ….
    """
    if n_cuts < 1:
        raise ValueError("n_cuts precisa ser >= 1")
    cuts = [first_cut]
    for _ in range(n_cuts - 1):
        cuts.append(cuts[-1] + BUSINESS_DAYS_PER_YEAR)
    return tuple(cuts)


def forward_rate(acc_end: float, acc_start: float) -> float:
    """Taxa do período entre dois cortes: ``(1 + A_fim) / (1 + A_início) − 1`` (E4.4).

    Mesma ordem de operações de ``DI!S28 = (1+VLOOKUP(R28,…))/(1+VLOOKUP(R26,…))-1``.
    """
    return (1 + acc_end) / (1 + acc_start) - 1


def forward_rates_at_cuts(accumulated: Sequence[float], cuts: Sequence[int]) -> tuple[float, ...]:
    """Taxas entre cortes consecutivos de uma grade de acumulados (E4.4).

    Devolve ``len(cuts) - 1`` taxas (``DI!S28:S37`` para 11 cortes).
    """
    values = [grid_value(accumulated, c) for c in cuts]
    return tuple(forward_rate(values[i], values[i - 1]) for i in range(1, len(values)))


def annualize(accumulated: float, exponent: float) -> float:
    """``(1 + A)^expoente − 1``.

    Usada pela anualização do DI (``DI!E4``, expoente ``4/(5−q)``) e do CDS
    (``CDS!E4``, expoente ``252/YTG``). Ver F0, seção 2, e E4.6.
    """
    return math.pow(1 + accumulated, exponent) - 1


def compound(rates: Sequence[float]) -> float:
    """``PRODUCT(1 + taxas) − 1``, multiplicando na ordem dada (E4.3)."""
    return product_of_one_plus(rates) - 1


def product_of_one_plus(rates: Sequence[float]) -> float:
    """``PRODUCT(1 + taxas)``, multiplicando na ordem dada (E4.2, E4.3).

    É o fator realizado do dia 1 (``DI!Y3``: ``PRODUCT(1+T11:T22)``) e do ano 1
    (``DI!S27``: ``PRODUCT(1+U11:U22)``).
    """
    factor = 1.0
    for r in rates:
        factor *= 1 + r
    return factor
