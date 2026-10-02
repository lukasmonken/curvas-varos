"""Tabela LEGADO × CORRIGIDO da F2 (Parte 1, seção 15).

Colunas DI, Inflação, CDS e Juro real, cada uma com o valor LEGADO, o CORRIGIDO
e a diferença em bps, para os inputs da planilha; e a decomposição de cada
diferença por causa (``curvas.engine.attribution``). Não julga metodologia.
"""

import csv
import io
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Any

from curvas.calendar import BusinessCalendar
from curvas.engine.attribution import TYPO_STAGE, Stage, contributions, legacy_to_corrected
from curvas.engine.corrected import (
    CorrectedInputs,
    CorrectedResult,
    FactorCurve,
    InflationGapRule,
    compute_corrected,
)
from curvas.engine.curves import VertexCurve
from curvas.engine.legacy import LegacyInputs, LegacyResult, SheetParams, compute_legacy
from curvas.normalize.anbima_ettj import corrected_curves, legacy_curves_pct, parse_anbima_ettj
from curvas.normalize.bcb_sgs import monthly_by_reference, parse_sgs
from curvas.normalize.corrected_inputs import build_corrected_inputs
from curvas.normalize.ibge import IPCA15_TITLE, parse_ipca_releases
from curvas.validate.checks import validate_anbima

BPS = 10_000
CURVES: tuple[tuple[str, str], ...] = (
    ("di", "DI"),
    ("inflation", "Inflação"),
    ("cds", "CDS"),
    ("real", "Juro real"),
)


def legacy_inputs_from_json(raw: dict[str, Any]) -> LegacyInputs:
    """``tests/fixtures/legacy/inputs_planilha.json`` → :class:`LegacyInputs`."""
    return LegacyInputs(
        first_year=raw["first_year"],
        inflation_curve_pct=tuple(raw["inflation_curve_pct"]),
        di_curve_pct=tuple(raw["di_curve_pct"]),
        cds_bps=tuple(raw["cds_bps"]),
        ipca_monthly=tuple(raw["ipca_monthly"]),
        selic_monthly=tuple(raw["selic_monthly"]),
        inflation_params=SheetParams.from_labels(*raw["inflation_params"]),
        di_params=SheetParams.from_labels(*raw["di_params"]),
        cds_ytg_days=int(raw["cds_ytg_days"]),
    )


@dataclass(frozen=True)
class RealizedFiles:
    """Respostas gravadas do BCB e do IBGE usadas no realizado do CORRIGIDO."""

    cdi: Path  # SGS 12
    ipca: Path  # SGS 433
    ibge: Path  # agenda de divulgações
    ipca15: Path | None = None  # SGS 7478 (Forma A, Q13)

    @classmethod
    def in_dir(cls, folder: Path, cdi_name: str = "bcb_sgs_12_cdi_diario.json") -> "RealizedFiles":
        ipca15 = folder / "bcb_sgs_7478_ipca15_mensal.json"
        return cls(
            cdi=folder / cdi_name,
            ipca=folder / "bcb_sgs_433_ipca_mensal.json",
            ibge=folder / "ibge_calendario_2026.json",
            ipca15=ipca15 if ipca15.exists() else None,
        )


def _pct(values: Sequence[float]) -> tuple[float, ...]:
    return tuple(v / 100 for v in values)


def planilha_curves(raw: dict[str, Any]) -> tuple[VertexCurve, VertexCurve]:
    """Curvas (DI, inflação) da planilha com todos os vértices digitados."""
    return (
        VertexCurve(tuple(raw["di_curve_days_full"]), _pct(raw["di_curve_pct"])),
        VertexCurve(tuple(raw["inflation_curve_days_full"]), _pct(raw["inflation_curve_pct_full"])),
    )


def corrected_inputs_for(
    raw: dict[str, Any],
    files: RealizedFiles,
    calendar: BusinessCalendar,
    as_of: date,
    *,
    curves: tuple[VertexCurve, VertexCurve],
    gap_rule: InflationGapRule = InflationGapRule.CURVE,
) -> CorrectedInputs:
    """Curvas (DI, inflação) dadas + CDS da planilha + realizado gravado em ``files``."""
    di_curve, inflation_curve = curves
    ibge = files.ibge.read_bytes()
    ipca15 = monthly_by_reference(parse_sgs(files.ipca15.read_bytes())) if files.ipca15 else None
    return build_corrected_inputs(
        as_of=as_of,
        calendar=calendar,
        di_curve=di_curve,
        inflation_curve=inflation_curve,
        cds_curve=VertexCurve(tuple(raw["cds_days"]), tuple(b / BPS for b in raw["cds_bps"])),
        cdi_daily_pct=parse_sgs(files.cdi.read_bytes()),
        ipca_monthly_pct=monthly_by_reference(parse_sgs(files.ipca.read_bytes())),
        ipca_releases=parse_ipca_releases(ibge),
        gap_rule=gap_rule,
        ipca15_monthly_pct=ipca15,
        ipca15_releases=parse_ipca_releases(ibge, IPCA15_TITLE),
    )


@dataclass(frozen=True)
class F2Report:
    as_of: date
    legacy: LegacyResult
    corrected_inputs: CorrectedInputs
    corrected: CorrectedResult
    stages: tuple[Stage, ...]
    anbima_date: date | None = None  # curvas do CORRIGIDO vindas da ANBIMA desse dia
    ipca15: CorrectedResult | None = None  # sensibilidade: Forma A (Q13)


def build_report(
    inputs_json: Path,
    files: RealizedFiles,
    calendar: BusinessCalendar,
    as_of: date,
    *,
    anbima_csv: Path | None = None,
) -> F2Report:
    """Monta a comparação.

    Sem ``anbima_csv``, o CORRIGIDO usa as curvas da planilha com todos os vértices
    digitados. Com ``anbima_csv`` (Q8/Q14/Q15), usa as curvas da ANBIMA como
    publicadas, e a cascata ganha a etapa do erro de colagem do DI.
    """
    raw = json.loads(inputs_json.read_text(encoding="utf-8"))
    legacy_inputs = legacy_inputs_from_json(raw)
    di_fix: tuple[float, ...] | None = None
    anbima_date: date | None = None
    if anbima_csv is None:
        curves = planilha_curves(raw)
    else:
        ettj = parse_anbima_ettj(anbima_csv.read_bytes())
        validate_anbima(ettj, as_of)
        anbima_date = ettj.reference_date
        di_aligned, inflation = legacy_curves_pct(ettj)
        if inflation != legacy_inputs.inflation_curve_pct:
            raise ValueError("a inflação da planilha não é a da ANBIMA dessa data")
        if di_aligned != legacy_inputs.di_curve_pct:
            di_fix = di_aligned
        curves = corrected_curves(ettj)

    corrected_inputs = corrected_inputs_for(raw, files, calendar, as_of, curves=curves)
    sensitivity = None
    if files.ipca15 is not None:
        sensitivity = compute_corrected(
            corrected_inputs_for(
                raw,
                files,
                calendar,
                as_of,
                curves=curves,
                gap_rule=InflationGapRule.IPCA15_SAME_MONTH,
            )
        )
    return F2Report(
        as_of=as_of,
        legacy=compute_legacy(legacy_inputs),
        corrected_inputs=corrected_inputs,
        corrected=compute_corrected(corrected_inputs),
        stages=legacy_to_corrected(legacy_inputs, corrected_inputs, di_curve_fix_pct=di_fix),
        anbima_date=anbima_date,
        ipca15=sensitivity,
    )


def _fmt_pct(x: float) -> str:
    return f"{100 * x:.4f}%".replace(".", ",")


def _bps(x: float) -> str:
    s = f"{BPS * x:+.1f}".replace(".", ",")
    return "0,0" if s in ("+0,0", "-0,0") else s


def _causes(contrib: dict[str, tuple[float, ...]], i: int, threshold_bps: float = 0.5) -> str:
    items = [(name, BPS * c[i]) for name, c in contrib.items() if abs(BPS * c[i]) >= threshold_bps]
    items.sort(key=lambda t: -abs(t[1]))
    return "; ".join(f"{n} {v:+.1f}".replace(".", ",") for n, v in items) or "—"


def _header(report: F2Report) -> list[str]:
    ci = report.corrected_inputs
    du = ci.year_end_business_days
    year_lengths = ", ".join(str(b - a) for a, b in pairwise(du))
    if report.anbima_date is None:
        source = "as curvas da planilha, com todos os vértices digitados"
    else:
        source = (
            f"as curvas da ANBIMA de {report.anbima_date:%d/%m/%Y} como publicadas (Q15): "
            "inflação implícita de 252 a 2520 d.u.; DI = ETTJ PREF + Circular 3.361 abaixo de "
            "252 (21, 42, 63 e 126 d.u.)"
        )
    lines = [
        "# F2: LEGADO × CORRIGIDO com os inputs da planilha",
        "",
        f"Data-base (t0): {report.as_of:%d/%m/%Y} (Q8). LEGADO = uso (a), a planilha "
        "exatamente como está (abas em Janeiro/1º Tri, YTG do CDS = 62). CORRIGIDO = E8 com "
        f"{source}; CDS da planilha; calendário ANBIMA; realizado do BCB (CDI SGS 12, IPCA "
        "SGS 433) e datas de divulgação do IBGE.",
        "",
        f"- dU(2026) a partir de t0: {du[0]} dias úteis; anos seguintes: {year_lengths}.",
        f"- CDI realizado em 2026 até t0 (exclusive): {_fmt_pct(ci.cdi_realized_factor - 1)}.",
        f"- {report.corrected.inflation_gap_rule} IPCA realizado no ano: "
        f"{_fmt_pct(ci.ipca_realized_factor - 1)}.",
        "- Convenção de t0 (Q11, a confirmar): o dia t0 fica na curva (dU conta de t0 a "
        "31/12, inclusive) e o CDI realizado vai até a véspera de t0; é a contagem de DU da B3.",
        "- Alcance da regra do IPCA (Q12, a confirmar): o intervalo vale só para o ano "
        "corrente; os anos seguintes usam dU contado de t0 (E8.5).",
    ]
    if report.anbima_date is not None:
        lines.append(
            f"- As curvas digitadas na planilha são a publicação da ANBIMA de "
            f"{report.anbima_date:%d/%m/%Y} (`docs/F3_RECONCILIACAO_ANBIMA.md`). A de DI tem um "
            "erro de colagem (o vértice 378 foi pulado e os seguintes subiram uma posição); o "
            "efeito dele aparece separado, na coluna **erro de colagem**."
        )
    if report.ipca15 is not None:
        s, c = report.ipca15, report.corrected
        lines.append(
            "- Sensibilidade, IPCA-15 no lugar do IPCA não divulgado (Forma A, Q13, desligada "
            f"por padrão): Inflação {c.years[0]} = {_fmt_pct(s.inflation[0])} "
            f"({_bps(s.inflation[0] - c.inflation[0])} bps sobre o CORRIGIDO); Juro real "
            f"{c.years[0]} = {_fmt_pct(s.real[0])} ({_bps(s.real[0] - c.real[0])} bps). "
            f"{s.inflation_gap_rule}"
        )
    return lines


def render_markdown(report: F2Report) -> str:
    first, last = report.stages[0], report.stages[-1]
    years = report.corrected.years
    ci = report.corrected_inputs
    lines = [
        *_header(report),
        "",
        "## Tabela principal",
        "",
        "Valores em % ao ano; diferenças (CORRIGIDO − LEGADO) em bps. Causas com |efeito| ≥ "
        "0,5 bp, em bps, da maior para a menor.",
        "",
    ]
    for key, label in CURVES:
        contrib = contributions(report.stages, key)
        lines += [
            f"### {label}",
            "",
            "| Ano | LEGADO | CORRIGIDO | Dif. (bps) | Causas (bps) |",
            "|---|---:|---:|---:|---|",
        ]
        a, b = getattr(first, key), getattr(last, key)
        for i, year in enumerate(years):
            lines.append(
                f"| {year} | {_fmt_pct(a[i])} | {_fmt_pct(b[i])} | {_bps(b[i] - a[i])} | "
                f"{_causes(contrib, i)} |"
            )
        lines.append("")

    cds_now = report.corrected.cds_current_year
    legacy_ytg = report.legacy.dashboard.cds_ytg or 0.0
    du0, gap = ci.year_end_business_days[0], ci.inflation_gap_business_days
    inf_curve = FactorCurve(ci.inflation_curve, ci.interpolation)
    # Variação da Inflação do ano corrente ao trocar dU(Y₀) dias de curva pelos do intervalo.
    gap_effect = ci.ipca_realized_factor * (inf_curve.factor(gap) - inf_curve.factor(du0))
    cds_cut = f"corte em 31/12 (YTG digitado do CDS: {report.legacy.cds.cuts[0]} → {du0})"
    has_typo = any(s.name == TYPO_STAGE for s in report.stages)
    lines += [
        "### CDS no ano corrente (E8.7)",
        "",
        "| Campo | LEGADO | CORRIGIDO | Dif. (bps) | Causa |",
        "|---|---:|---:|---:|---|",
        f"| annualized_rate (coluna 2026) | {_fmt_pct(first.cds[0])} | "
        f"{_fmt_pct(cds_now.annualized_rate)} | {_bps(cds_now.annualized_rate - first.cds[0])} | "
        f"{cds_cut}; antes do 1º vértice a taxa é a mesma |",
        f"| remaining_period_accumulated (coluna YTG) | {_fmt_pct(legacy_ytg)} | "
        f"{_fmt_pct(cds_now.remaining_period_accumulated)} | "
        f"{_bps(cds_now.remaining_period_accumulated - legacy_ytg)} | "
        f"{cds_cut}; mesmo conceito, acumulado sem anualizar (E6.7) |",
        "",
        "## Decomposição por causa (bps)",
        "",
        "Cascata em ordem fixa; cada coluna é o efeito de trocar só aquela causa, mantidas "
        "as trocas anteriores. A soma das colunas é a diferença total.",
        "",
        "Como ler:",
        "",
    ]
    if has_typo:
        lines.append(
            "- **erro de colagem** (E6.12, Q14): troca a curva de DI digitada pela mesma curva "
            "da ANBIMA alinhada, ainda no método da planilha. Mexe só no DI e no juro real."
        )
    lines += [
        "- **corte em 31/12** e **realizado** são as duas metades do mesmo erro de "
        "data-base (E6.2): a planilha soma o realizado de janeiro a 231 dias de curva; o "
        "CORRIGIDO soma o realizado do ano aos dias de curva até 31/12. No ano corrente, os "
        "dois efeitos são grandes e de sinais opostos; o que importa é a soma.",
        f"- No DI, **realizado** = CDI até a véspera de t0 + {du0} dias de curva. Na "
        f"inflação, = IPCA até o último mês divulgado + {gap} dias de curva desde o 1º dia "
        f"útil seguinte (E8.6); desses, {gap - du0} dias são curva no lugar do IPCA ainda "
        f"não divulgado, e respondem por cerca de {_bps(gap_effect)} bps do efeito.",
        "- **anualização** é zero aqui porque as abas estão no 1º Tri (expoente 4/(5−1) = 1). "
        "Com a planilha em outro trimestre, ela deixa de ser zero (ver F0, D2).",
        "- **acumulação** é o E6.1: a planilha trata a taxa spot de cada dia como forward.",
    ]
    if report.anbima_date is None:
        lines.append(
            "- **interpolação** inclui a extrapolação depois do último vértice (E8.3: forward do "
            "último segmento, contra taxa flat na planilha) e, na inflação, os vértices 2520 e "
            "2646, que a planilha ignora (E6.8)."
        )
    else:
        lines.append(
            "- **interpolação** inclui a extrapolação depois do último vértice (E8.3: forward do "
            "último segmento, contra taxa flat na planilha) e a troca de vértices: o CORRIGIDO "
            "usa só os publicados pela ANBIMA (sem os remendos 126 e 2646 da inflação; com os "
            "vértices curtos 21 a 126 e o 2520 do DI)."
        )
    lines += [
        "- A ordem da cascata importa só na divisão entre causas que interagem, sobretudo "
        "**acumulação** e **interpolação**: a soma das duas não depende da ordem, mas a "
        "divisão entre elas sim (aqui, a interação fica com a interpolação, que vem depois).",
        "",
    ]
    names = [s.name for s in report.stages[1:]]
    for key, label in CURVES:
        contrib = contributions(report.stages, key)
        lines += [
            f"### {label}",
            "",
            "| Ano | " + " | ".join(names) + " | Total |",
            "|---|" + "---:|" * (len(names) + 1),
        ]
        for i, year in enumerate(years):
            cells = [_bps(contrib[n][i]) for n in names]
            total = getattr(last, key)[i] - getattr(first, key)[i]
            lines.append(f"| {year} | " + " | ".join(cells) + f" | {_bps(total)} |")
        lines.append("")
    return "\n".join(lines)


def render_csv(report: F2Report) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    names = [s.name for s in report.stages[1:]]
    writer.writerow(
        ["curva", "ano", "legado", "corrigido", "dif_bps", *[f"bps_{n}" for n in names]]
    )
    first, last = report.stages[0], report.stages[-1]
    for key, _label in CURVES:
        contrib = contributions(report.stages, key)
        for i, year in enumerate(report.corrected.years):
            a, b = getattr(first, key)[i], getattr(last, key)[i]
            writer.writerow(
                [
                    key,
                    year,
                    repr(a),
                    repr(b),
                    f"{BPS * (b - a):.6f}",
                    *[f"{BPS * contrib[n][i]:.6f}" for n in names],
                ]
            )
    return buf.getvalue()
