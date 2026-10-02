"""CDI realizado mês a mês (``realized.cdi_monthly``, schema 1.1; Q11-B e Q18)."""

import json
import math
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from curvas.calendar import load_anbima_calendar
from curvas.models import MonthlyValue
from curvas.normalize.bcb_sgs import parse_sgs
from curvas.output.json_out import cdi_monthly
from test_run import SGS_FILES, T0, client, go

CAL = load_anbima_calendar()
CDI = parse_sgs(SGS_FILES["12"].read_bytes())  # SGS 12 até 29/09/2026
RATES = dict(CDI)


def product(months: Sequence[MonthlyValue]) -> float:
    return math.prod(1 + m.value_pct / 100 for m in months)


def compound_pct(days: Sequence[date]) -> float:
    return (math.prod(1 + RATES[d] / 100 for d in days) - 1) * 100


def test_saida_publicada_bate_com_o_fator(tmp_path: Path) -> None:
    out = go(tmp_path, T0)
    months = out.realized.cdi_monthly
    assert [(m.year, m.month) for m in months] == [(2026, m) for m in range(1, 10)]
    assert all(m.release_date is None for m in months)
    assert abs(product(months) / out.realized.cdi.factor - 1) < 1e-12


def test_inclui_os_dias_preenchidos_pela_q18(tmp_path: Path) -> None:
    rows = json.loads(SGS_FILES["12"].read_text())[:-2]  # sem 28 e 29/09
    out = go(tmp_path, T0, client=client({"sgs:12": json.dumps(rows).encode()}))
    assert any(a.code == "cdi_preenchido" for a in out.alerts)
    months = out.realized.cdi_monthly
    assert months[-1].month == 9
    assert abs(product(months) / out.realized.cdi.factor - 1) < 1e-12


def test_mes_de_t0_e_parcial() -> None:
    t0 = date(2026, 9, 16)
    months = cdi_monthly(CDI, CAL.business_days_list(date(2026, 1, 1), t0))
    assert [(m.year, m.month) for m in months] == [(2026, m) for m in range(1, 10)]
    sept = CAL.business_days_list(date(2026, 9, 1), t0)
    assert sept[-1] == date(2026, 9, 15)  # véspera de t0 (Q11-B)
    assert months[-1].value_pct == pytest.approx(compound_pct(sept), rel=1e-13)
    august = CAL.business_days_list(date(2026, 8, 1), date(2026, 9, 1))
    assert months[-2].value_pct == pytest.approx(compound_pct(august), rel=1e-13)
    whole = cdi_monthly(CDI, CAL.business_days_list(date(2026, 1, 1), T0))
    assert whole[-1].value_pct > months[-1].value_pct  # mais dias de setembro em T0


def test_t0_no_primeiro_dia_util_do_mes() -> None:
    """Sem dia útil do mês de t0 antes de t0: o mês não entra (o anterior sai inteiro)."""
    t0 = date(2026, 9, 1)
    months = cdi_monthly(CDI, CAL.business_days_list(date(2026, 1, 1), t0))
    assert [m.month for m in months] == list(range(1, 9))


def test_t0_em_2_de_janeiro_da_lista_vazia() -> None:
    t0 = date(2026, 1, 2)
    assert CAL.is_business_day(t0)
    assert CAL.business_days_list(date(2026, 1, 1), t0) == ()
    assert cdi_monthly(CDI, CAL.business_days_list(date(2026, 1, 1), t0)) == []


def test_dia_sem_cdi_e_erro() -> None:
    """Mesma regra do fator: dia útil sem observação nunca é preenchido em silêncio."""
    days = CAL.business_days_list(date(2026, 9, 1), date(2026, 10, 1))  # 30/09 fora do SGS
    with pytest.raises(ValueError, match="sem observação"):
        cdi_monthly(CDI, days)
