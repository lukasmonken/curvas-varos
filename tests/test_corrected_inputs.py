"""Montagem dos inputs do CORRIGIDO em casos de execução diária (E8.1, E8.6)."""

from datetime import date
from functools import cache

import pytest

from curvas.calendar import BusinessCalendar, load_anbima_calendar
from curvas.engine.corrected import (
    CorrectedInputs,
    InflationGapRule,
    IpcaRelease,
    compute_corrected,
)
from curvas.engine.curves import VertexCurve
from curvas.normalize.corrected_inputs import build_corrected_inputs

CURVE = VertexCurve((126, 252, 504), (0.10, 0.11, 0.12))


@cache
def cal() -> BusinessCalendar:
    return load_anbima_calendar()


def releases(*items: tuple[int, int, date]) -> list[IpcaRelease]:
    return [IpcaRelease(y, m, d) for y, m, d in items]


# Agenda realista em torno da virada 2026/2027.
AGENDA = releases(
    (2026, 10, date(2026, 11, 12)),
    (2026, 11, date(2026, 12, 11)),
    (2026, 12, date(2027, 1, 12)),
    (2027, 1, date(2027, 2, 10)),
    (2027, 2, date(2027, 3, 11)),
)
IPCA = {(2027, 1): 0.5, (2027, 2): 0.4}


def build(as_of: date, agenda: list[IpcaRelease] = AGENDA) -> CorrectedInputs:
    cdi_days = cal().business_days_list(date(as_of.year, 1, 1), as_of)
    return build_corrected_inputs(
        as_of=as_of,
        calendar=cal(),
        di_curve=CURVE,
        inflation_curve=CURVE,
        cds_curve=CURVE,
        cdi_daily_pct=[(d, 0.05) for d in cdi_days],
        ipca_monthly_pct=IPCA,
        ipca_releases=agenda,
    )


def test_janeiro_antes_do_ipca_de_dezembro() -> None:
    ci = build(date(2027, 1, 7))
    assert ci.ipca_last_month == 0
    assert ci.ipca_last_published == (2026, 11)
    assert ci.ipca_realized_factor == 1.0
    assert ci.inflation_gap_business_days == cal().business_days(date(2027, 1, 1), date(2028, 1, 1))
    rule = compute_corrected(ci).inflation_gap_rule
    assert "Nenhum IPCA de 2027 divulgado até t0" in rule
    assert "11/2026" in rule
    assert "00/" not in rule


def test_dia_da_divulgacao_conta() -> None:
    ci = build(date(2027, 2, 10))  # IPCA de janeiro sai às 9h; a curva é de fechamento
    assert ci.ipca_last_month == 1
    assert ci.ipca_realized_factor == pytest.approx(1.005)
    assert ci.inflation_gap_business_days == cal().business_days(date(2027, 2, 1), date(2028, 1, 1))
    rule = compute_corrected(ci).inflation_gap_rule
    assert "de 01/2027 a 01/2027" in rule
    assert "10/02/2027" in rule


def test_cdi_inclui_ate_a_vespera_de_t0() -> None:
    ci = build(date(2027, 1, 7))
    n = cal().business_days(date(2027, 1, 1), date(2027, 1, 7))
    assert ci.cdi_realized_factor == pytest.approx(1.0005**n, rel=1e-15)


def test_t0_nao_util() -> None:
    with pytest.raises(ValueError, match="dia útil"):
        build(date(2027, 1, 9))  # sábado


def test_agenda_que_nao_cobre_t0() -> None:
    with pytest.raises(ValueError, match="não cobre"):
        build(date(2027, 3, 15))


def test_agenda_com_buraco() -> None:
    sem_janeiro = [r for r in AGENDA if (r.ref_year, r.ref_month) != (2027, 1)]
    with pytest.raises(ValueError, match="buraco"):
        build(date(2027, 2, 15), sem_janeiro)


def test_ipca_defasado() -> None:
    velha = releases((2026, 9, date(2026, 10, 9)), (2026, 10, date(2027, 2, 20)))
    with pytest.raises(ValueError, match="defasado"):
        build(date(2027, 2, 3), velha)


def test_cdi_faltando() -> None:
    as_of = date(2027, 1, 7)
    days = cal().business_days_list(date(2027, 1, 1), as_of)
    with pytest.raises(ValueError, match="sem observação"):
        build_corrected_inputs(
            as_of=as_of,
            calendar=cal(),
            di_curve=CURVE,
            inflation_curve=CURVE,
            cds_curve=CURVE,
            cdi_daily_pct=[(d, 0.05) for d in days[1:]],
            ipca_monthly_pct=IPCA,
            ipca_releases=AGENDA,
        )


# ------------------------------------------------------------------ IPCA-15 (Forma A, Q13)

AGENDA15 = releases(
    (2027, 1, date(2027, 1, 27)),
    (2027, 2, date(2027, 2, 25)),
    (2027, 3, date(2027, 3, 25)),
)
IPCA15 = {(2027, 1): 0.30, (2027, 2): 0.60, (2027, 3): 0.50}


def build15(as_of: date) -> CorrectedInputs:
    cdi_days = cal().business_days_list(date(as_of.year, 1, 1), as_of)
    return build_corrected_inputs(
        as_of=as_of,
        calendar=cal(),
        di_curve=CURVE,
        inflation_curve=CURVE,
        cds_curve=CURVE,
        cdi_daily_pct=[(d, 0.05) for d in cdi_days],
        ipca_monthly_pct=IPCA,
        ipca_releases=AGENDA,
        gap_rule=InflationGapRule.IPCA15_SAME_MONTH,
        ipca15_monthly_pct=IPCA15,
        ipca15_releases=AGENDA15,
    )


def test_forma_a_usa_o_ipca15_do_mes_seguinte() -> None:
    ci = build15(date(2027, 3, 1))  # o IPCA de fev só sai em 11/03: o último é o de jan
    assert ci.ipca_last_month == 1
    assert ci.ipca15_used is not None
    assert (ci.ipca15_used.ref_month, ci.ipca15_used.value_pct) == (2, 0.60)
    assert ci.ipca_realized_factor == pytest.approx(1.005 * 1.006)
    # a curva cobre de 01/03 em diante — menos dias que dU(Y₀), o que só vale nesta forma
    assert ci.inflation_gap_business_days == cal().business_days(date(2027, 3, 1), date(2028, 1, 1))
    assert ci.inflation_gap_business_days <= ci.year_end_business_days[0]
    rule = compute_corrected(ci).inflation_gap_rule
    assert "IPCA-15 de 02/2027 (+0,60%, divulgado em 25/02/2027)" in rule
    assert "Forma A" in rule


def test_forma_a_sem_ipca15_divulgado_cai_na_curva() -> None:
    ci = build15(date(2027, 2, 15))  # IPCA de jan já saiu; IPCA-15 de fev só em 25/02
    assert ci.ipca_last_month == 1
    assert ci.ipca15_used is None
    assert ci.inflation_gap_business_days == cal().business_days(date(2027, 2, 1), date(2028, 1, 1))
    rule = compute_corrected(ci).inflation_gap_rule
    assert "Forma A (IPCA-15) ligada, mas o IPCA-15 de 02/2027 só sai em 25/02/2027" in rule


def test_forma_a_com_agenda_sem_o_mes_falha() -> None:
    """Revisão da F3: agenda vazia não pode virar a regra da curva em silêncio."""
    with pytest.raises(ValueError, match="agenda do IPCA-15 sem o mês 02/2027"):
        build_corrected_inputs(
            as_of=date(2027, 2, 15),
            calendar=cal(),
            di_curve=CURVE,
            inflation_curve=CURVE,
            cds_curve=CURVE,
            cdi_daily_pct=[
                (d, 0.05) for d in cal().business_days_list(date(2027, 1, 1), date(2027, 2, 15))
            ],
            ipca_monthly_pct=IPCA,
            ipca_releases=AGENDA,
            gap_rule=InflationGapRule.IPCA15_SAME_MONTH,
            ipca15_monthly_pct=IPCA15,
            ipca15_releases=[],
        )


def test_forma_a_em_janeiro() -> None:
    ci = build15(date(2027, 1, 28))  # sem IPCA de 2027; IPCA-15 de jan saiu em 27/01
    assert ci.ipca_last_month == 0
    assert ci.ipca15_used is not None
    assert ci.ipca15_used.ref_month == 1
    assert ci.ipca_realized_factor == pytest.approx(1.003)
    assert "Nenhum IPCA de 2027 divulgado até t0" in compute_corrected(ci).inflation_gap_rule


def test_forma_a_exige_dados() -> None:
    with pytest.raises(ValueError, match="Forma A"):
        build_corrected_inputs(
            as_of=date(2027, 3, 1),
            calendar=cal(),
            di_curve=CURVE,
            inflation_curve=CURVE,
            cds_curve=CURVE,
            cdi_daily_pct=[
                (d, 0.05) for d in cal().business_days_list(date(2027, 1, 1), date(2027, 3, 1))
            ],
            ipca_monthly_pct=IPCA,
            ipca_releases=AGENDA,
            gap_rule=InflationGapRule.IPCA15_SAME_MONTH,
        )


def test_padrao_e_a_curva() -> None:
    assert build(date(2027, 3, 1)).ipca15_used is None
