"""Monta a saída JSON da execução (Parte 1, seção 11) a partir dos resultados do motor."""

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any

from curvas.engine.corrected import (
    CorrectedInputs,
    CorrectedResult,
    FactorCurve,
    IpcaRelease,
    compound_daily_cdi,
    real_rate,
)
from curvas.engine.curves import VertexCurve, accumulate_recursive
from curvas.engine.legacy import (
    CDS_VERTEX_DAYS,
    RATE_SHEET_VERTEX_DAYS,
    LegacyResult,
    ytg_days,
)
from curvas.models import (
    Alert,
    AnnualOut,
    AnnualRow,
    CdiRealized,
    CdsCurrentYear,
    ComparisonRow,
    CorrectedInputsOut,
    CurveOut,
    CurvePoint,
    InputsOut,
    LegacyInputsOut,
    LegacyYtg,
    Metadata,
    MonthlyValue,
    RealizedOut,
    RunOutput,
    SourceRecord,
    Vertex,
)
from curvas.normalize.anbima_ettj import AnbimaEttj
from curvas.normalize.legacy_inputs import LegacyDaily

BPS = 10_000
SAMPLE_DAYS: tuple[int, ...] = (1, *range(21, 2647, 21))


@dataclass(frozen=True)
class ComputeBundle:
    as_of: date
    ettj: AnbimaEttj
    corrected_inputs: CorrectedInputs
    corrected: CorrectedResult
    legacy_daily: LegacyDaily
    legacy: LegacyResult
    cdi: Sequence[tuple[date, float]]
    cdi_days: Sequence[date]  # dias úteis de 1º/jan até t0 (exclusive), os do fator do CDI
    cdi_last_observed: date | None  # última observação real (antes do preenchimento da Q18)
    ipca: dict[tuple[int, int], float]
    selic: dict[tuple[int, int], float]
    releases: Sequence[IpcaRelease]
    cds_source: str


def _discount(di: float | None, cds: float | None) -> float | None:
    """Q4: (1 + DI)(1 + CDS) − 1."""
    return None if di is None or cds is None else (1 + di) * (1 + cds) - 1


def _real(di: float | None, inflation: float | None) -> float | None:
    return None if di is None or inflation is None else real_rate(di, inflation)


def _rows(
    years: Sequence[int],
    di: Sequence[float | None],
    inflation: Sequence[float | None],
    cds: Sequence[float | None],
) -> list[AnnualRow]:
    return [
        AnnualRow(
            year=y,
            di=d,
            inflation=i,
            cds=c,
            real=_real(d, i),
            discount=_discount(d, c),
        )
        for y, d, i, c in zip(years, di, inflation, cds, strict=True)
    ]


def _corrected_sample(curve: VertexCurve, days: Sequence[int]) -> list[CurvePoint]:
    fc = FactorCurve(curve)
    return [CurvePoint(days=d, rate=fc.rate(d), factor=fc.factor(d)) for d in days]


def _legacy_sample(daily_rate: Sequence[float], days: Sequence[int]) -> list[CurvePoint]:
    acc = accumulate_recursive(daily_rate)  # só a curva, sem o realizado do dia 1
    return [
        CurvePoint(days=d, rate=daily_rate[d - 1], factor=1 + acc[d - 1])
        for d in days
        if d <= len(daily_rate)
    ]


def _vertices(curve: VertexCurve) -> list[Vertex]:
    return [Vertex(days=d, rate=r) for d, r in zip(curve.days, curve.rates, strict=True)]


def _curves(b: ComputeBundle) -> list[CurveOut]:
    ci, legacy_in = b.corrected_inputs, b.legacy_daily.inputs
    cds_days = sorted({*SAMPLE_DAYS, *CDS_VERTEX_DAYS})
    specs = [
        (
            "di",
            f"ANBIMA ETTJ PREF + Circular 3.361 de {b.ettj.reference_date:%d/%m/%Y}",
            ci.di_curve,
            VertexCurve(RATE_SHEET_VERTEX_DAYS, tuple(p / 100 for p in legacy_in.di_curve_pct)),
            b.legacy.di.daily_rate,
            SAMPLE_DAYS,
        ),
        (
            "inflation",
            f"ANBIMA inflação implícita de {b.ettj.reference_date:%d/%m/%Y}",
            ci.inflation_curve,
            VertexCurve(
                RATE_SHEET_VERTEX_DAYS, tuple(p / 100 for p in legacy_in.inflation_curve_pct)
            ),
            b.legacy.inflation.daily_rate,
            SAMPLE_DAYS,
        ),
        (
            "cds",
            b.cds_source,
            ci.cds_curve,
            VertexCurve(CDS_VERTEX_DAYS, tuple(x / BPS for x in legacy_in.cds_bps)),
            b.legacy.cds.daily_rate,
            cds_days,
        ),
    ]
    return [
        CurveOut(
            name=name,  # type: ignore[arg-type]
            source=source,
            corrected_vertices=_vertices(corrected),
            legacy_vertices=_vertices(legacy),
            corrected_sample=_corrected_sample(corrected, days),
            legacy_sample=_legacy_sample(daily, days),
        )
        for name, source, corrected, legacy, daily, days in specs
    ]


def _annual(b: ComputeBundle) -> tuple[AnnualOut, list[Alert]]:
    c, dash = b.corrected, b.legacy.dashboard
    alerts: list[Alert] = []
    legacy_di, legacy_inf, legacy_cds = list(dash.di), list(dash.inflation), list(dash.cds)
    ytg = LegacyYtg(di=dash.di_ytg, inflation=dash.inflation_ytg, cds=dash.cds_ytg)
    if b.legacy_daily.turn_of_year:
        # Q6: na virada do ano, o ano corrente do LEGADO sai indisponível.
        legacy_di[0] = legacy_inf[0] = legacy_cds[0] = None
        ytg = LegacyYtg(di=None, inflation=None, cds=None)
        alerts.append(
            Alert(
                level="warning",
                code="legado_virada_do_ano",
                message=(
                    f"LEGADO: nenhum IPCA de {b.as_of.year} divulgado até t0; o ano "
                    f"{b.as_of.year} sai indisponível e os seguintes saem normais (Q6)"
                ),
            )
        )
    for name, row in (("DI", legacy_di), ("Inflação", legacy_inf), ("CDS", legacy_cds)):
        missing = [c.years[i] for i, v in enumerate(row) if v is None]
        if missing and not (b.legacy_daily.turn_of_year and missing == [c.years[0]]):
            alerts.append(
                Alert(
                    level="warning",
                    code="legado_indisponivel",
                    message=f"LEGADO {name}: #N/A em {missing}",
                )
            )
    now = c.cds_current_year
    annual = AnnualOut(
        corrected=_rows(c.years, c.di, c.inflation, c.cds),
        legacy=_rows(c.years, legacy_di, legacy_inf, legacy_cds),
        corrected_cds_current_year=CdsCurrentYear(
            annualized_rate=now.annualized_rate,
            remaining_period_accumulated=now.remaining_period_accumulated,
            business_days=now.business_days,
        ),
        legacy_ytg=ytg,
    )
    return annual, alerts


def cdi_monthly(cdi: Sequence[tuple[date, float]], days: Sequence[date]) -> list[MonthlyValue]:
    """CDI realizado de cada mês, em % no mês: ``(Π(1 + CDI_d/100) − 1)·100``.

    Usa os mesmos dias e taxas do fator ``realized.cdi.factor`` (1º/jan até a véspera
    de t0, Q11-B, com o preenchimento da Q18). O mês de t0 sai parcial; mês sem dia
    útil antes de t0 não entra (t0 no 1º dia útil do ano: lista vazia).
    """
    rates = dict(cdi)
    months: dict[tuple[int, int], list[date]] = {}
    for d in days:
        months.setdefault((d.year, d.month), []).append(d)
    return [
        MonthlyValue(year=y, month=m, value_pct=(compound_daily_cdi(rates, ds) - 1) * 100)
        for (y, m), ds in months.items()
    ]


def _realized(b: ComputeBundle) -> RealizedOut:
    ci, year = b.corrected_inputs, b.as_of.year
    release = {(r.ref_year, r.ref_month): r.release_date for r in b.releases}
    ipca_months = [
        MonthlyValue(
            year=year, month=m, value_pct=b.ipca[(year, m)], release_date=release.get((year, m))
        )
        for m in range(1, ci.ipca_last_month + 1)
    ]
    used15 = ci.ipca15_used
    month = b.legacy_daily.month
    cdi_days = [d for d, _ in b.cdi if date(year, 1, 1) <= d < b.as_of]
    return RealizedOut(
        ipca_monthly=ipca_months,
        ipca_ytd=ci.ipca_realized_factor - 1,
        ipca_rule=b.corrected.inflation_gap_rule,
        ipca15_used=None
        if used15 is None
        else MonthlyValue(
            year=used15.ref_year,
            month=used15.ref_month,
            value_pct=used15.value_pct,
            release_date=used15.release_date,
        ),
        cdi=CdiRealized(
            start=date(year, 1, 1),
            end_exclusive=b.as_of,
            business_days=len(cdi_days),
            factor=ci.cdi_realized_factor,
            last_observation=b.cdi_last_observed,
        ),
        cdi_monthly=cdi_monthly(b.cdi, b.cdi_days),
        selic_monthly_legacy=[
            MonthlyValue(year=year, month=m, value_pct=b.selic[(year, m)])
            for m in range(1, month + 1)
        ],
    )


def _inputs(b: ComputeBundle) -> InputsOut:
    li, ci = b.legacy_daily.inputs, b.corrected_inputs
    month = b.legacy_daily.month
    return InputsOut(
        legacy=LegacyInputsOut(
            first_year=li.first_year,
            month=month or None,
            quarter=li.di_params.quarter if month else None,
            ytg_days=ytg_days(month),
            cds_ytg_days=li.cds_ytg_days,
            inflation_curve_pct=list(li.inflation_curve_pct),
            di_curve_pct=list(li.di_curve_pct),
            cds_bps=list(li.cds_bps),
        ),
        corrected=CorrectedInputsOut(
            year_end_business_days=list(ci.year_end_business_days),
            inflation_gap_business_days=ci.inflation_gap_business_days,
            interpolation=ci.interpolation.value,
            gap_rule=ci.gap_rule.value,
            cdi_realized_factor=ci.cdi_realized_factor,
            ipca_realized_factor=ci.ipca_realized_factor,
        ),
    )


def _comparison(annual: AnnualOut) -> list[ComparisonRow]:
    def diff(a: float | None, b: float | None) -> float | None:
        return None if a is None or b is None else (a - b) * BPS

    return [
        ComparisonRow(
            year=c.year,
            di_bps=diff(c.di, lg.di),
            inflation_bps=diff(c.inflation, lg.inflation),
            cds_bps=diff(c.cds, lg.cds),
            real_bps=diff(c.real, lg.real),
            discount_bps=diff(c.discount, lg.discount),
        )
        for c, lg in zip(annual.corrected, annual.legacy, strict=True)
    ]


def assemble_output(
    b: ComputeBundle,
    *,
    sources: Sequence[SourceRecord],
    alerts: Sequence[Alert],
    code_version: str,
    git_commit: str | None,
) -> RunOutput:
    annual, annual_alerts = _annual(b)
    return RunOutput(
        metadata=Metadata(as_of_date=b.as_of, code_version=code_version, git_commit=git_commit),
        sources=list(sources),
        inputs=_inputs(b),
        curves=_curves(b),
        annual=annual,
        realized=_realized(b),
        comparison=_comparison(annual),
        alerts=[*alerts, *annual_alerts],
    )


FIELDS = ("di", "inflation", "cds", "real", "discount")


def daily_change_alerts(
    previous: dict[str, Any], current: RunOutput, max_bps: float
) -> list[Alert]:
    """Seção 12: taxa anual que variou mais que ``max_bps`` desde a saída anterior (alerta)."""
    prev_date = previous["metadata"]["as_of_date"]
    alerts: list[Alert] = []
    for mode in ("corrected", "legacy"):
        before = {row["year"]: row for row in previous["annual"][mode]}
        for row in getattr(current.annual, mode):
            old = before.get(row.year)
            if old is None:
                continue
            for f in FIELDS:
                a, b = old.get(f), getattr(row, f)
                if a is None or b is None:
                    continue
                change = (b - a) * BPS
                if abs(change) > max_bps:
                    alerts.append(
                        Alert(
                            level="warning",
                            code="variacao_diaria",
                            message=(
                                f"{mode} {f} {row.year}: {change:+.1f} bps desde {prev_date} "
                                f"(limite {max_bps:.0f} bps)"
                            ),
                        )
                    )
    return alerts


# Mensagem de ``daily_change_alerts``: "<modo> <campo> <ano>: ...".
CHANGE = re.compile(r"^(?P<mode>\w+) (?P<field>\w+) (?P<year>\d{4}):")
CHANGE_HIDDEN = "variação acima do limite"  # o que fica no lugar do valor (Q17)
CDS_FIELDS = frozenset({"cds", "discount"})


def hide_cds_change(alert: Alert) -> Alert:
    """Q17: variação diária do CDS ou da taxa de desconto sem o valor em bps (fica o fato).

    Regra única do site e dos downloads; qualquer outro alerta volta igual.
    """
    match = CHANGE.match(alert.message) if alert.code == "variacao_diaria" else None
    if match is None or match["field"] not in CDS_FIELDS:
        return alert
    message = f"{match['mode']} {match['field']} {match['year']}: {CHANGE_HIDDEN}"
    return alert.model_copy(update={"message": message})
