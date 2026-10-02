"""Calendário ANBIMA (Parte 1, seção 10.6)."""

from datetime import date, timedelta
from functools import cache

import bizdays
import pytest

from conftest import ROOT
from curvas.calendar import BusinessCalendar, CalendarRangeError, load_anbima_calendar
from curvas.normalize.bcb_sgs import parse_sgs


@cache
def anbima() -> BusinessCalendar:
    return load_anbima_calendar()


@cache
def bz() -> bizdays.Calendar:
    return bizdays.Calendar.load("ANBIMA")


def test_cobertura() -> None:
    cal = anbima()
    assert cal.start == date(2001, 1, 1)
    assert cal.end == date(2099, 12, 31)


def test_dia_a_dia_igual_ao_bizdays() -> None:
    """Conferência cruzada com o calendário ANBIMA embutido no pacote ``bizdays``."""
    cal, ref = anbima(), bz()
    d, diffs = cal.start, []
    while d <= date(2099, 12, 25):  # fim da cobertura do bizdays
        if cal.is_business_day(d) != ref.isbizday(d):
            diffs.append(d)
        d += timedelta(days=1)
    assert diffs == []


@pytest.mark.parametrize("year", range(2026, 2037))
def test_dias_uteis_por_ano(year: int) -> None:
    """Dias úteis entre cortes (31/12) = contagem dia a dia do ``bizdays``."""
    expected = len(list(bz().seq(date(year, 1, 1), date(year, 12, 31))))
    assert anbima().business_days(date(year, 1, 1), date(year + 1, 1, 1)) == expected


@pytest.mark.parametrize(
    "t0",
    [date(2026, 9, 4), date(2026, 1, 2), date(2026, 12, 30), date(2027, 1, 4), date(2027, 3, 15)],
)
def test_cortes_do_corrigido(t0: date) -> None:
    """Item 10.6: dU(Y) de cada corte = contagem dia a dia do bizdays de t0 a 31/12/Y."""
    years = range(t0.year, t0.year + 11)
    expected = tuple(len(list(bz().seq(t0, date(y, 12, 31)))) for y in years)
    assert anbima().year_end_business_days(t0, years) == expected


def test_2026() -> None:
    cal = anbima()
    assert cal.business_days(date(2026, 1, 1), date(2027, 1, 1)) == 249
    assert not cal.is_business_day(date(2026, 11, 20))  # Consciência Negra (Lei 14.759/2023)
    assert cal.is_business_day(date(2026, 12, 31))  # nota 4 do arquivo ANBIMA
    assert not cal.is_business_day(date(2026, 9, 7))


def test_convencao_inclui_inicio_exclui_fim() -> None:
    cal = anbima()
    t0 = date(2026, 9, 4)  # sexta
    assert cal.business_days(t0, t0) == 0
    assert cal.business_days(t0, date(2026, 9, 5)) == 1  # conta t0
    assert cal.business_days(t0, date(2026, 9, 8)) == 1  # 07/09 é feriado
    assert cal.business_days(date(2026, 9, 8), t0) == -1
    assert cal.year_end_business_days(t0, [2026, 2027]) == (80, 80 + 251)


def test_datas_do_cdi_real_sao_os_dias_uteis() -> None:
    """As 170 observações do CDI (SGS 12) de 2026 caem exatamente nos dias úteis ANBIMA."""
    raw = (ROOT / "tests" / "fixtures" / "f2" / "bcb_sgs_12_cdi_diario.json").read_bytes()
    dates = [d for d, _ in parse_sgs(raw)]
    assert dates == list(anbima().business_days_list(date(2026, 1, 1), date(2026, 9, 5)))


def test_following_preceding() -> None:
    cal = anbima()
    assert cal.following(date(2026, 9, 5)) == date(2026, 9, 8)
    assert cal.preceding(date(2026, 9, 7)) == date(2026, 9, 4)
    assert cal.following(date(2026, 9, 4)) == date(2026, 9, 4)


def test_fora_da_cobertura() -> None:
    with pytest.raises(CalendarRangeError):
        anbima().business_days(date(2000, 12, 29), date(2001, 1, 3))
    with pytest.raises(CalendarRangeError):
        anbima().is_business_day(date(2100, 1, 1))


def test_calendario_sintetico() -> None:
    cal = BusinessCalendar(frozenset({date(2026, 1, 1)}), date(2026, 1, 1), date(2026, 1, 31))
    assert cal.business_days(date(2026, 1, 1), date(2026, 1, 31)) == 21
    with pytest.raises(ValueError, match="end < start"):
        BusinessCalendar(frozenset(), date(2026, 2, 1), date(2026, 1, 1))
