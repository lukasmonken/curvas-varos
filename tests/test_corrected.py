"""Modo CORRIGIDO (E8; Parte 1, seção 10, itens 3, 4, 5 e 7)."""

import math
from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from curvas.engine.corrected import (
    FactorCurve,
    Interpolation,
    IpcaRelease,
    calendar_year_rates,
    cds_current_year,
    compound_daily_cdi,
    compound_monthly_ipca,
    last_published_month,
    real_rate,
    vertex_factor,
)
from curvas.engine.curves import VertexCurve, accumulate_recursive, linear_incremental_grid

rates_st = st.floats(min_value=-0.02, max_value=0.4, allow_nan=False, allow_infinity=False)


@st.composite
def curves(draw: st.DrawFn, min_gap: int = 1) -> VertexCurve:
    first = draw(st.integers(min_value=1, max_value=300))
    gaps = draw(st.lists(st.integers(min_value=min_gap, max_value=600), min_size=0, max_size=10))
    days = [first]
    for g in gaps:
        days.append(days[-1] + g)
    rates = draw(st.lists(rates_st, min_size=len(days), max_size=len(days)))
    return VertexCurve(tuple(days), tuple(rates))


class TestReprecificacao:
    """Item 10.3: cada vértice é recuperado com erro < 1e-12."""

    @given(curves())
    @settings(max_examples=300)
    def test_vertices(self, curve: VertexCurve) -> None:
        fc = FactorCurve(curve)
        for v, s in zip(curve.days, curve.rates, strict=True):
            assert abs(fc.factor(v) - (1 + s) ** (v / 252)) < 1e-12
            assert abs(fc.rate(v) - s) < 1e-12

    def test_curva_da_planilha(self) -> None:
        days = tuple(126 * k for k in range(1, 22))
        rates = (0.064827, 0.064827, 0.060499, 0.059218, 0.059117) + (0.06,) * 16
        fc = FactorCurve(VertexCurve(days, rates))
        assert max(abs(fc.rate(v) - s) for v, s in zip(days, rates, strict=True)) < 1e-12


class TestFlatForward:
    # Segmentos de pelo menos 21 d.u. (um mês): com 1 d.u. entre vértices de taxas
    # muito diferentes, a forward extrapolada por 400 dias estoura o float. Isso é
    # matemática de E8.3, não defeito; a F4 bloqueia fator não finito (seção 12).
    @given(curves(min_gap=21))
    @settings(max_examples=200)
    def test_sanidade(self, curve: VertexCurve) -> None:
        """Item 10.5: fatores positivos, finitos e contínuos nos vértices."""
        fc = FactorCurve(curve)
        last = curve.days[-1] + 400
        factors = [fc.factor(d) for d in range(last + 1)]
        assert factors[0] == 1.0
        assert all(math.isfinite(f) and f > 0 for f in factors)
        # Continuidade: sem salto no vértice; o passo diário de cada lado é a forward
        # diária do segmento daquele lado (o 1º segmento começa em F(0) = 1).
        knots = (0, *curve.days)
        for i in range(1, len(knots)):
            a, b = knots[i - 1], knots[i]
            per_day = (factors[b] / factors[a]) ** (1 / (b - a))
            assert factors[b] / factors[b - 1] == pytest.approx(per_day, rel=1e-9)
            assert factors[a + 1] / factors[a] == pytest.approx(per_day, rel=1e-9)
        # Depois do último vértice, segue a forward do último segmento.
        a, b = knots[-2], knots[-1]
        per_day = (factors[b] / factors[a]) ** (1 / (b - a))
        assert factors[b + 1] / factors[b] == pytest.approx(per_day, rel=1e-9)

    @given(curves())
    def test_log_linear_entre_vertices(self, curve: VertexCurve) -> None:
        """Flat-forward: ln F é linear entre vértices (forward constante no segmento)."""
        fc = FactorCurve(curve)
        for v1, v2 in zip(curve.days, curve.days[1:], strict=False):
            if v2 - v1 >= 2:
                mid = v1 + (v2 - v1) // 2
                w = (mid - v1) / (v2 - v1)
                expected = (1 - w) * math.log(fc.factor(v1)) + w * math.log(fc.factor(v2))
                assert math.log(fc.factor(mid)) == pytest.approx(expected, abs=1e-12)

    def test_antes_do_primeiro_vertice_spot_constante(self) -> None:
        fc = FactorCurve(VertexCurve((126, 252), (0.10, 0.12)))
        for d in (1, 50, 126):
            assert fc.factor(d) == pytest.approx(1.10 ** (d / 252), rel=1e-15)

    def test_depois_do_ultimo_mantem_forward_do_ultimo_segmento(self) -> None:
        fc = FactorCurve(VertexCurve((126, 252), (0.10, 0.12)))
        fwd = fc.factor(252) / fc.factor(126)
        assert fc.factor(378) / fc.factor(252) == pytest.approx(fwd, rel=1e-14)
        assert fc.factor(504) / fc.factor(378) == pytest.approx(fwd, rel=1e-14)

    def test_um_vertice(self) -> None:
        fc = FactorCurve(VertexCurve((252,), (0.1,)))
        assert fc.factor(504) == pytest.approx(1.1**2, rel=1e-15)

    def test_linear_so_para_comparacao(self) -> None:
        fc = FactorCurve(VertexCurve((126, 252), (0.10, 0.12)), Interpolation.LINEAR)
        assert fc.rate(189) == pytest.approx(0.11, abs=1e-15)
        assert fc.rate(1000) == pytest.approx(0.12, abs=1e-15)

    def test_prazo_invalido(self) -> None:
        fc = FactorCurve(VertexCurve((126,), (0.1,)))
        with pytest.raises(ValueError, match="negativo"):
            fc.factor(-1)
        with pytest.raises(ValueError, match="positivo"):
            fc.rate(0)


class TestCurvaFlat:
    """Item 10.4: com curva flat, LEGADO e CORRIGIDO coincidem."""

    @given(rate=rates_st, n=st.integers(min_value=1, max_value=3000))
    def test_fatores(self, rate: float, n: int) -> None:
        curve = VertexCurve(tuple(126 * k for k in range(1, 20)), (rate,) * 19)
        legacy = accumulate_recursive(linear_incremental_grid(curve, n, step=126))
        assert 1 + legacy[-1] == pytest.approx(FactorCurve(curve).factor(n), rel=1e-12)


class TestAnual:
    def test_ano_corrente_e_seguintes(self) -> None:
        fc = FactorCurve(VertexCurve((252,), (0.10,)))
        res = calendar_year_rates(fc, 2026, (80, 331, 579), realized_factor=1.05)
        assert res.years == (2026, 2027, 2028)
        assert res.rates[0] == pytest.approx(1.05 * 1.1 ** (80 / 252) - 1, rel=1e-14)
        assert res.rates[1] == pytest.approx(1.1 ** (251 / 252) - 1, rel=1e-13)
        assert res.rates[2] == pytest.approx(1.1 ** (248 / 252) - 1, rel=1e-13)

    def test_intervalo_da_inflacao(self) -> None:
        fc = FactorCurve(VertexCurve((252,), (0.06,)))
        res = calendar_year_rates(fc, 2026, (80, 331), first_year_curve_days=104)
        assert res.rates[0] == pytest.approx(1.06 ** (104 / 252) - 1, rel=1e-14)
        assert res.rates[1] == pytest.approx(1.06 ** (251 / 252) - 1, rel=1e-13)

    def test_cortes_invalidos(self) -> None:
        fc = FactorCurve(VertexCurve((252,), (0.06,)))
        with pytest.raises(ValueError, match="crescente"):
            calendar_year_rates(fc, 2026, (80, 80))

    def test_cds_dois_campos(self) -> None:
        fc = FactorCurve(VertexCurve((126, 252), (0.004567, 0.005435)))
        now = cds_current_year(fc, 80)
        assert now.annualized_rate == pytest.approx(0.004567, abs=1e-15)
        assert now.remaining_period_accumulated == pytest.approx(1.004567 ** (80 / 252) - 1)
        with pytest.raises(ValueError, match="positivo"):
            cds_current_year(fc, 0)

    def test_cds_dois_campos_depois_do_primeiro_vertice(self) -> None:
        """E8.7: com dU > 1º vértice, annualized_rate não é a taxa do 1º vértice (E4.5)."""
        fc = FactorCurve(VertexCurve((126, 252), (0.004567, 0.005435)))
        now = cds_current_year(fc, 200)
        assert now.remaining_period_accumulated == pytest.approx(fc.factor(200) - 1, rel=1e-15)
        assert now.annualized_rate == pytest.approx(fc.factor(200) ** (252 / 200) - 1)
        assert abs(now.annualized_rate - 0.004567) > 1e-5

    def test_juro_real(self) -> None:
        assert real_rate(0.14, 0.06) == pytest.approx(1.14 / 1.06 - 1, rel=1e-15)
        assert vertex_factor(0.1, 252) == pytest.approx(1.1, rel=1e-15)


class TestRealizado:
    def test_cdi_diario(self) -> None:
        days = [date(2026, 1, 2), date(2026, 1, 5)]
        obs = {days[0]: 0.05, days[1]: 0.05, date(2026, 1, 6): 9.9}
        assert compound_daily_cdi(obs, days) == pytest.approx(1.0005**2, rel=1e-15)
        with pytest.raises(ValueError, match="sem observação"):
            compound_daily_cdi({days[0]: 0.05}, days)

    def test_ipca_mensal(self) -> None:
        monthly = {(2026, 1): 0.33, (2026, 2): 0.70}
        assert compound_monthly_ipca(monthly, 2026, 2) == pytest.approx(1.0033 * 1.007)
        assert compound_monthly_ipca(monthly, 2026, 0) == 1.0
        with pytest.raises(ValueError, match="ausente"):
            compound_monthly_ipca(monthly, 2026, 3)

    def test_ultimo_ipca_divulgado(self) -> None:
        rel = [
            IpcaRelease(2026, 7, date(2026, 8, 11)),
            IpcaRelease(2026, 8, date(2026, 9, 11)),
        ]
        assert last_published_month(rel, date(2026, 9, 4)) == (2026, 7)
        assert last_published_month(rel, date(2026, 9, 11)) == (2026, 8)  # no próprio dia
        with pytest.raises(ValueError, match="nenhuma"):
            last_published_month(rel, date(2026, 8, 10))
