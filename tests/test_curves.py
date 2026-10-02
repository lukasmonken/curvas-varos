"""Interpolação e acumulação (E4.1, E4.2), com testes de propriedade."""

import math
from itertools import pairwise

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from curvas.engine.curves import (
    GridLookupError,
    VertexCurve,
    accumulate_recursive,
    grid_value,
    linear_incremental_grid,
)

rates_st = st.floats(min_value=-0.05, max_value=0.6, allow_nan=False, allow_infinity=False)


@st.composite
def curves(draw: st.DrawFn) -> tuple[VertexCurve, int]:
    first = draw(st.integers(min_value=1, max_value=300))
    gaps = draw(st.lists(st.integers(min_value=1, max_value=300), min_size=0, max_size=8))
    days = [first]
    for g in gaps:
        days.append(days[-1] + g)
    rates = draw(st.lists(rates_st, min_size=len(days), max_size=len(days)))
    last_day = draw(st.integers(min_value=1, max_value=days[-1] + 300))
    return VertexCurve(tuple(days), tuple(rates)), last_day


def closed_form(curve: VertexCurve, d: int) -> float:
    days, rates = curve.days, curve.rates
    if d <= days[0]:
        return rates[0]
    if d >= days[-1]:
        return rates[-1]
    k = next(i for i in range(1, len(days)) if days[i] >= d)
    v1, v2 = days[k - 1], days[k]
    return rates[k - 1] + (rates[k] - rates[k - 1]) * (d - v1) / (v2 - v1)


class TestInterpolacaoLinear:
    @given(curves())
    @settings(max_examples=300)
    def test_propriedades(self, case: tuple[VertexCurve, int]) -> None:
        curve, last_day = case
        grid = linear_incremental_grid(curve, last_day)
        assert len(grid) == last_day
        assert all(math.isfinite(x) for x in grid)

        # Passa exatamente pelos vértices (âncoras =C7, =C8, …).
        for v, r in zip(curve.days, curve.rates, strict=True):
            if v <= last_day:
                assert grid[v - 1] == r

        for d in range(1, last_day + 1):
            x = grid[d - 1]
            if d < curve.days[0]:
                assert x == curve.rates[0]  # flat à esquerda
            elif d > curve.days[-1]:
                assert x == curve.rates[-1]  # flat à direita
            else:
                assert x == pytest.approx(closed_form(curve, d), abs=1e-12)
                k = next(i for i, v in enumerate(curve.days) if v >= d)
                lo = min(curve.rates[max(k - 1, 0)], curve.rates[k]) - 1e-12
                hi = max(curve.rates[max(k - 1, 0)], curve.rates[k]) + 1e-12
                assert lo <= x <= hi

    @given(curves())
    def test_passo_explicito_igual_ao_espacamento(self, case: tuple[VertexCurve, int]) -> None:
        """Vértices equiespaçados em 126: ``/126`` fixo (DI) = ``/(v2−v1)`` (CDS)."""
        curve, _ = case
        equi = VertexCurve(tuple(126 * (i + 1) for i in range(len(curve.days))), curve.rates)
        last = equi.days[-1] + 10
        assert linear_incremental_grid(equi, last, step=126) == linear_incremental_grid(equi, last)

    def test_monotona_entre_vertices(self) -> None:
        curve = VertexCurve((126, 252, 378), (0.10, 0.12, 0.11))
        grid = linear_incremental_grid(curve, 400)
        assert all(b >= a for a, b in pairwise(grid[125:252]))
        assert all(b <= a for a, b in pairwise(grid[251:378]))

    def test_um_vertice_e_flat(self) -> None:
        assert linear_incremental_grid(VertexCurve((10,), (0.07,)), 20) == (0.07,) * 20

    def test_grade_menor_que_ultimo_vertice(self) -> None:
        grid = linear_incremental_grid(VertexCurve((5, 10), (0.0, 0.5)), 7)
        assert grid == pytest.approx((0.0,) * 5 + (0.1, 0.2), abs=1e-15)

    @pytest.mark.parametrize(
        ("days", "rates", "msg"),
        [
            ((), (), "pelo menos um"),
            ((1, 2), (0.1,), "mesmo tamanho"),
            ((0, 2), (0.1, 0.1), "dia útil 1"),
            ((5, 5), (0.1, 0.1), "crescentes"),
            ((1, 2), (0.1, math.nan), "finitas"),
            ((1,), (math.inf,), "finitas"),
        ],
    )
    def test_vertices_invalidos(
        self, days: tuple[int, ...], rates: tuple[float, ...], msg: str
    ) -> None:
        with pytest.raises(ValueError, match=msg):
            VertexCurve(days, rates)

    def test_last_day_invalido(self) -> None:
        with pytest.raises(ValueError, match="last_day"):
            linear_incremental_grid(VertexCurve((1,), (0.1,)), 0)


class TestAcumulacaoRecursiva:
    @given(
        rate=rates_st,
        initial=st.floats(min_value=0.5, max_value=1.5),
        n=st.integers(min_value=1, max_value=3000),
    )
    def test_curva_flat_igual_a_potencia(self, rate: float, initial: float, n: int) -> None:
        """Em trecho flat, a recursiva coincide com ``F0·(1+s)^(d/252)`` (E4.2)."""
        acc = accumulate_recursive((rate,) * n, initial)
        assert 1 + acc[-1] == pytest.approx(initial * (1 + rate) ** (n / 252), rel=1e-12)

    @given(st.lists(rates_st, min_size=2, max_size=400))
    def test_razao_diaria(self, rates: list[float]) -> None:
        acc = accumulate_recursive(rates)
        for d in range(1, len(rates)):
            ratio = (1 + acc[d]) / (1 + acc[d - 1])
            assert ratio == pytest.approx((1 + rates[d]) ** (1 / 252), rel=1e-12)
            assert ratio > 0

    def test_nao_e_spot(self) -> None:
        """E6.1: com curva inclinada a recursiva não reprecifica o vértice spot."""
        curve = VertexCurve((126, 504), (0.064827, 0.059218))
        acc = accumulate_recursive(linear_incremental_grid(curve, 504))
        assert abs((1 + acc[503]) - (1 + 0.059218) ** 2) > 1e-3

    def test_dia_1_aplica_fator_antes(self) -> None:
        acc = accumulate_recursive((0.1, 0.1), 1.01)
        assert acc[0] == 1.01 * 1.1 ** (1 / 252) - 1

    def test_vazia(self) -> None:
        assert accumulate_recursive(()) == ()


class TestLookup:
    def test_vlookup_exato(self) -> None:
        grid = (0.1, 0.2, 0.3)
        assert grid_value(grid, 1) == 0.1
        assert grid_value(grid, 3) == 0.3

    @pytest.mark.parametrize("day", [0, -1, 4])
    def test_fora_da_grade(self, day: int) -> None:
        with pytest.raises(GridLookupError):
            grid_value((0.1, 0.2, 0.3), day)
