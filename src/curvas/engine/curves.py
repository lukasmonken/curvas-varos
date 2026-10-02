"""Curvas diárias: interpolação nas taxas e acumulação dia a dia.

Funções puras. Uma grade diária é uma tupla em que a posição ``d - 1`` guarda o
valor do dia útil ``d`` (o dia 1 é o primeiro). É o mesmo layout das colunas
``W:Y`` (Inflação, DI) e ``L:N`` (CDS) da planilha legada.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

BUSINESS_DAYS_PER_YEAR = 252


class GridLookupError(LookupError):
    """Dia fora da grade. Equivale ao ``#N/A`` de um ``VLOOKUP(..., FALSE)``."""


@dataclass(frozen=True)
class VertexCurve:
    """Vértices em dias úteis (estritamente crescentes) e taxas anuais em decimal (E3.2, E4.1)."""

    days: tuple[int, ...]
    rates: tuple[float, ...]

    def __post_init__(self) -> None:
        if not self.days:
            raise ValueError("a curva precisa de pelo menos um vértice")
        if len(self.days) != len(self.rates):
            raise ValueError("days e rates precisam ter o mesmo tamanho")
        if self.days[0] < 1:
            raise ValueError("vértices começam no dia útil 1")
        if any(b <= a for a, b in zip(self.days, self.days[1:], strict=False)):
            raise ValueError("vértices precisam ser estritamente crescentes")
        if not all(math.isfinite(r) for r in self.rates):
            raise ValueError("taxas dos vértices precisam ser finitas")


def grid_value(grid: Sequence[float], day: int) -> float:
    """Valor da grade no dia ``day``, com a semântica de ``VLOOKUP(day, grade, n, FALSE)``.

    Implementa a busca exata usada em E4.4 (cortes por ano). Dia inexistente na
    grade gera :class:`GridLookupError`, como o ``#N/A`` da planilha.
    """
    if day < 1 or day > len(grid):
        raise GridLookupError(f"dia {day} fora da grade de 1 a {len(grid)}")
    return grid[day - 1]


def linear_incremental_grid(
    curve: VertexCurve,
    last_day: int,
    *,
    step: float | None = None,
) -> tuple[float, ...]:
    """Taxa diária por interpolação linear nas taxas, como a planilha legada (E4.1).

    A planilha não usa a fórmula fechada. Ela soma um incremento constante ao dia
    anterior, e este código repete essa ordem de operações:

    - antes do 1º vértice: taxa do 1º vértice (``DI!X3:X127 = $X$128``);
    - no vértice ``k``: a própria taxa (``DI!X128 = C7``, ``X254 = C8`` …);
    - entre vértices: ``x(d) = x(d-1) + (s_k - s_{k-1}) / passo``
      (``DI!X129 = X128 + ($C$8-$C$7)/126``);
    - depois do último vértice: ``x(d) = x(d-1)`` (``DI!X2397 = X2396``).

    ``step=None`` usa o espaçamento real entre vértices, como a aba CDS
    (``CDS!M134 = M133 + ($F$9-$F$8)/($C$9-$C$8)``). As abas DI e Inflação
    escrevem ``126`` fixo no divisor; passe ``step=126`` para elas.
    """
    if last_day < 1:
        raise ValueError("last_day precisa ser >= 1")
    days, rates = curve.days, curve.rates
    size = max(last_day, days[-1])
    grid = [0.0] * size

    # Antes do primeiro vértice: flat (DI!X3:X127 = $X$128).
    for d in range(1, days[0]):
        grid[d - 1] = rates[0]
    grid[days[0] - 1] = rates[0]

    for k in range(1, len(days)):
        left, right = days[k - 1], days[k]
        divisor = float(right - left) if step is None else step
        increment = (rates[k] - rates[k - 1]) / divisor
        for d in range(left + 1, right):
            grid[d - 1] = grid[d - 2] + increment
        # Âncora no vértice (DI!X254 = C8).
        grid[right - 1] = rates[k]

    # Depois do último vértice: repete o anterior (DI!X2397 = X2396).
    for d in range(days[-1] + 1, size + 1):
        grid[d - 1] = grid[d - 2]

    return tuple(grid[:last_day])


def accumulate_recursive(
    daily_rates: Sequence[float],
    initial_factor: float = 1.0,
) -> tuple[float, ...]:
    """Acumulado dia a dia, recursivo, com a taxa de cada dia em base 252 (E4.2).

    - dia 1: ``A(1) = F0 · (1 + x(1))^(1/252) − 1``
      (``DI!Y3 = (PRODUCT(1+T11:T22)*(1+X3)^(1/252))-1``);
    - dia d: ``A(d) = (1 + A(d−1)) · (1 + x(d))^(1/252) − 1``
      (``DI!Y4 = (1+Y3)*(1+X4)^(1/252) - 1``).

    ``initial_factor`` é o fator realizado aplicado no dia 1 (``PRODUCT(1+T)``).
    No CDS ele vale 1 (``CDS!N8 = (1+$M$8)^(1/252) - 1``). O valor guardado em
    cada dia é o acumulado (fator − 1), na mesma ordem de arredondamento da planilha.
    """
    if not daily_rates:
        return ()
    exponent = 1 / BUSINESS_DAYS_PER_YEAR
    out = [0.0] * len(daily_rates)
    acc = initial_factor * math.pow(1 + daily_rates[0], exponent) - 1
    out[0] = acc
    for i in range(1, len(daily_rates)):
        acc = (1 + acc) * math.pow(1 + daily_rates[i], exponent) - 1
        out[i] = acc
    return tuple(out)
