"""Monta os inputs do CORRIGIDO a partir das curvas, do calendário e do realizado (E8)."""

from collections.abc import Mapping, Sequence
from datetime import date

from curvas.calendar import BusinessCalendar
from curvas.engine.corrected import (
    CorrectedInputs,
    InflationGapRule,
    Interpolation,
    Ipca15Used,
    IpcaRelease,
    compound_daily_cdi,
    compound_monthly_ipca,
    last_published_month,
)
from curvas.engine.curves import VertexCurve

N_YEARS = 11


def build_corrected_inputs(
    *,
    as_of: date,
    calendar: BusinessCalendar,
    di_curve: VertexCurve,
    inflation_curve: VertexCurve,
    cds_curve: VertexCurve,
    cdi_daily_pct: Sequence[tuple[date, float]],
    ipca_monthly_pct: Mapping[tuple[int, int], float],
    ipca_releases: Sequence[IpcaRelease],
    interpolation: Interpolation = Interpolation.FLAT_FORWARD,
    gap_rule: InflationGapRule = InflationGapRule.CURVE,
    ipca15_monthly_pct: Mapping[tuple[int, int], float] | None = None,
    ipca15_releases: Sequence[IpcaRelease] | None = None,
    ipca_cutoff: date | None = None,
) -> CorrectedInputs:
    """E8.1 a E8.6 com uma única data-base ``as_of`` (t0).

    Com ``gap_rule = IPCA15_SAME_MONTH`` (Forma A, Q13), se o IPCA-15 do mês seguinte
    ao último IPCA já foi divulgado até t0 (inclusive) e esse mês é do ano corrente,
    ele entra no realizado no lugar do IPCA desse mês, e a curva cobre do mês seguinte
    em diante. Se ainda não saiu, vale a regra da curva.

    ``ipca_cutoff`` (padrão: t0) é a data até a qual as divulgações do IPCA e do
    IPCA-15 contam. O pipeline a antecipa quando o IBGE já divulgou um mês que ainda
    não chegou ao SGS, e registra isso em alerta (fonte defasada).
    """
    if not calendar.is_business_day(as_of):
        raise ValueError(f"t0 precisa ser dia útil ANBIMA: {as_of}")
    year = as_of.year
    du = calendar.year_end_business_days(as_of, range(year, year + N_YEARS))

    # CDI: dias úteis de 1º/jan até t0, exclusive (o dia t0 já está na curva).
    cdi_days = calendar.business_days_list(date(year, 1, 1), as_of)
    cdi_factor = compound_daily_cdi(dict(cdi_daily_pct), cdi_days)

    # IPCA: até o último mês divulgado até t0; o resto do ano vem da curva,
    # contando do 1º dia útil depois desse mês (E8.6).
    cutoff = as_of if ipca_cutoff is None else min(ipca_cutoff, as_of)
    ref_year, ref_month = last_published_month(ipca_releases, cutoff)
    _check_release_calendar(ipca_releases, cutoff, (ref_year, ref_month))
    if ref_year == year:
        last_month = ref_month
    elif (ref_year, ref_month) in ((year - 1, 11), (year - 1, 12)):
        # Começo do ano: nenhum mês do ano corrente divulgado ainda (o IPCA de
        # dezembro sai por volta de 10/jan; o de janeiro, por volta de 10/fev).
        last_month = 0
    else:
        raise ValueError(
            f"último IPCA divulgado ({ref_month:02d}/{ref_year}) defasado para {cutoff}"
        )
    release_date = max(
        r.release_date for r in ipca_releases if (r.ref_year, r.ref_month) == (ref_year, ref_month)
    )
    ipca_factor = compound_monthly_ipca(ipca_monthly_pct, year, last_month)
    covered = last_month

    ipca15_used: Ipca15Used | None = None
    ipca15_pending: date | None = None
    if gap_rule is InflationGapRule.IPCA15_SAME_MONTH:
        if ipca15_monthly_pct is None or ipca15_releases is None:
            raise ValueError("Forma A exige a série e a agenda do IPCA-15")
        month = last_month + 1  # M = L + 1 (L = 0 → janeiro do ano corrente)
        scheduled = [r for r in ipca15_releases if (r.ref_year, r.ref_month) == (year, month)]
        if month <= 12 and not scheduled:
            # Sem a entrada de M na agenda, a Forma A viraria a regra da curva em silêncio.
            raise ValueError(f"agenda do IPCA-15 sem o mês {month:02d}/{year} (Forma A)")
        released = [r for r in scheduled if r.release_date <= cutoff]
        if scheduled and not released:
            ipca15_pending = min(r.release_date for r in scheduled)
        if month <= 12 and released:
            if (year, month) not in ipca15_monthly_pct:
                raise ValueError(f"IPCA-15 de {month:02d}/{year} divulgado, mas sem valor")
            value = ipca15_monthly_pct[(year, month)]
            ipca_factor *= 1 + value / 100
            covered = month
            ipca15_used = Ipca15Used(year, month, value, max(r.release_date for r in released))

    gap_start = date(year, covered + 1, 1) if covered < 12 else date(year + 1, 1, 1)
    gap_days = calendar.business_days(gap_start, date(year + 1, 1, 1))

    return CorrectedInputs(
        as_of=as_of,
        first_year=year,
        di_curve=di_curve,
        inflation_curve=inflation_curve,
        cds_curve=cds_curve,
        year_end_business_days=du,
        cdi_realized_factor=cdi_factor,
        ipca_realized_factor=ipca_factor,
        ipca_last_month=last_month,
        inflation_gap_business_days=gap_days,
        interpolation=interpolation,
        ipca_last_published=(ref_year, ref_month),
        ipca_last_release_date=release_date,
        ipca15_used=ipca15_used,
        gap_rule=gap_rule,
        ipca15_pending_release=ipca15_pending,
    )


def _next_month(year: int, month: int) -> tuple[int, int]:
    return (year + 1, 1) if month == 12 else (year, month + 1)


def _check_release_calendar(
    releases: Sequence[IpcaRelease], as_of: date, last: tuple[int, int]
) -> None:
    """A agenda do IBGE precisa cobrir t0 sem buraco; senão o IPCA seria ignorado em silêncio."""
    after = [r for r in releases if r.release_date > as_of]
    if not after:
        raise ValueError(f"a agenda de divulgações do IPCA não cobre t0 = {as_of}")
    nxt = min(after, key=lambda r: r.release_date)
    if (nxt.ref_year, nxt.ref_month) != _next_month(*last):
        raise ValueError(
            f"agenda do IPCA com buraco: último divulgado {last[1]:02d}/{last[0]}, "
            f"próximo previsto {nxt.ref_month:02d}/{nxt.ref_year}"
        )
