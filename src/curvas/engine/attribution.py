"""Decomposição da diferença LEGADO → CORRIGIDO por causa (tabela da F2).

Não é metodologia nova: é uma cascata que troca uma causa por vez, numa ordem
fixa, do LEGADO (uso a) até o CORRIGIDO (E8). Cada etapa mede a variação
causada por uma única troca, e a soma das etapas é exatamente a diferença total.
A ordem importa (interações entre causas ficam com a etapa que vem depois) e
está documentada em ``STAGE_NAMES``.

Causas (Parte 1, seção 15, mais o erro operacional encontrado na F3):

0. ``erro de colagem`` (opcional, E6.12/Q14): curva de DI da planilha, com o
   vértice 378 pulado, → a mesma curva da ANBIMA alinhada, ainda no método legado.
1. ``anualização``: DI 2026 = ``DI!E4`` (anualizado por trimestre) → ano civil.
2. ``corte em 31/12``: 1º corte = YTG da planilha (231/62) → ``dU(Y₀)`` real.
3. ``realizado``: realizado da planilha (meses "Usar") → CDI até a véspera de t0 e
   IPCA até o último mês divulgado; na inflação, o 1º ano passa a usar os dias de
   curva desde o 1º dia útil após esse mês (E8.6), não só os dias a partir de t0.
4. ``calendário``: anos de 252 dias úteis → dias úteis ANBIMA de cada ano.
5. ``acumulação``: acumulação recursiva da taxa diária → fator spot ``(1+s(d))^(d/252)``.
6. ``interpolação``: linear nas taxas (19 vértices, taxa flat depois do último) →
   flat-forward com todos os vértices e extrapolação pela forward do último segmento.
"""

import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from itertools import pairwise

from curvas.engine.annual import cuts_fixed_252, product_of_one_plus
from curvas.engine.corrected import CorrectedInputs, FactorCurve, real_rate
from curvas.engine.curves import (
    BUSINESS_DAYS_PER_YEAR,
    VertexCurve,
    accumulate_recursive,
    linear_incremental_grid,
)
from curvas.engine.legacy import (
    CDS_VERTEX_DAYS,
    RATE_SHEET_STEP,
    RATE_SHEET_VERTEX_DAYS,
    LegacyInputs,
    SheetParams,
    compute_legacy,
    usage_matrix,
    ytg_days,
)

TYPO_STAGE = "erro de colagem"
STAGE_NAMES: tuple[str, ...] = (
    "legado",
    "anualização",
    "corte em 31/12",
    "realizado",
    "calendário",
    "acumulação",
    "interpolação",
)


class Basis(StrEnum):
    """Como o fator ``F(d)`` é obtido."""

    LEGACY_RECURSIVE = "legacy_recursive"  # grade linear da planilha + acumulação recursiva
    LEGACY_SPOT = "legacy_spot"  # grade linear da planilha como spot: (1+x(d))^(d/252)
    CORRECTED = "corrected"  # FactorCurve do CORRIGIDO (E8.3)


class Year1(StrEnum):
    CALENDAR = "calendar"  # realizado · F(n) − 1
    ANNUALIZED_REMAINING = "annualized_remaining"  # F(c₀)^(252/c₀) − 1 (CDS)


@dataclass(frozen=True)
class CurveSetup:
    """Uma curva nas duas formas: a da planilha e a do CORRIGIDO."""

    legacy_curve: VertexCurve
    legacy_step: float | None
    corrected: FactorCurve


@dataclass(frozen=True)
class StageSpec:
    basis: Basis
    cuts: tuple[int, ...]  # c₀ … c₁₀; os anos seguintes são razões entre cortes vizinhos
    first_year_days: int
    realized_factor: float
    year1: Year1


def _factor_fn(setup: CurveSetup, basis: Basis, max_day: int) -> Callable[[int], float]:
    if basis is Basis.CORRECTED:
        return setup.corrected.factor
    grid = linear_incremental_grid(setup.legacy_curve, max_day, step=setup.legacy_step)
    if basis is Basis.LEGACY_SPOT:
        return lambda d: math.pow(1 + grid[d - 1], d / BUSINESS_DAYS_PER_YEAR)
    acc = accumulate_recursive(grid)
    return lambda d: 1 + acc[d - 1]


def stage_rates(setup: CurveSetup, spec: StageSpec) -> tuple[float, ...]:
    """Taxas por ano (Y₀ … Y₁₀) de uma etapa da cascata."""
    factor = _factor_fn(setup, spec.basis, max(*spec.cuts, spec.first_year_days))
    if spec.year1 is Year1.CALENDAR:
        y0 = spec.realized_factor * factor(spec.first_year_days) - 1
    else:
        c0 = spec.cuts[0]
        y0 = math.pow(factor(c0), BUSINESS_DAYS_PER_YEAR / c0) - 1
    fs = [factor(c) for c in spec.cuts]
    return (y0, *(fs[i] / fs[i - 1] - 1 for i in range(1, len(fs))))


@dataclass(frozen=True)
class Stage:
    name: str
    di: tuple[float, ...]
    inflation: tuple[float, ...]
    cds: tuple[float, ...]
    real: tuple[float, ...]


def _real(di: Sequence[float], inflation: Sequence[float]) -> tuple[float, ...]:
    return tuple(real_rate(n, i) for n, i in zip(di, inflation, strict=True))


def _numbers(row: Sequence[float | None], what: str) -> tuple[float, ...]:
    if any(v is None for v in row):
        raise ValueError(f"LEGADO com #N/A em {what}: a cascata exige linhas completas")
    return tuple(v for v in row if v is not None)


def stage_names(with_typo: bool) -> tuple[str, ...]:
    """Nomes das etapas, com ou sem a etapa do erro de colagem."""
    return (STAGE_NAMES[0], TYPO_STAGE, *STAGE_NAMES[1:]) if with_typo else STAGE_NAMES


def _dashboard_stage(name: str, legacy: LegacyInputs) -> Stage:
    dash = compute_legacy(legacy).dashboard
    di, inflation = _numbers(dash.di, "DI"), _numbers(dash.inflation, "Inflação")
    return Stage(name, di, inflation, _numbers(dash.cds, "CDS"), _real(di, inflation))


def legacy_to_corrected(
    legacy: LegacyInputs,
    corrected: CorrectedInputs,
    *,
    di_curve_fix_pct: Sequence[float] | None = None,
) -> tuple[Stage, ...]:
    """Cascata do Dashboard da planilha (uso a) até ``compute_corrected`` (E8).

    ``di_curve_fix_pct``: curva de DI certa (19 vértices, em %), que entra numa
    etapa própria logo depois do LEGADO, para separar o erro de colagem (Q14).
    """
    stages = [_dashboard_stage("legado", legacy)]
    if di_curve_fix_pct is not None:
        legacy = replace(legacy, di_curve_pct=tuple(di_curve_fix_pct))
        stages.append(_dashboard_stage(TYPO_STAGE, legacy))

    setups = {
        "di": CurveSetup(
            VertexCurve(RATE_SHEET_VERTEX_DAYS, tuple(p / 100 for p in legacy.di_curve_pct)),
            RATE_SHEET_STEP,
            FactorCurve(corrected.di_curve, corrected.interpolation),
        ),
        "inflation": CurveSetup(
            VertexCurve(RATE_SHEET_VERTEX_DAYS, tuple(p / 100 for p in legacy.inflation_curve_pct)),
            RATE_SHEET_STEP,
            FactorCurve(corrected.inflation_curve, corrected.interpolation),
        ),
        "cds": CurveSetup(
            VertexCurve(CDS_VERTEX_DAYS, tuple(b / 10000 for b in legacy.cds_bps)),
            None,
            FactorCurve(corrected.cds_curve, corrected.interpolation),
        ),
    }

    def realized(monthly: Sequence[float], params_month: int, params_quarter: int) -> float:
        t, u = usage_matrix(monthly, SheetParams(params_month, params_quarter))
        return product_of_one_plus(t) * product_of_one_plus(u)

    legacy_specs = {
        "di": StageSpec(
            Basis.LEGACY_RECURSIVE,
            cuts_fixed_252(ytg_days(legacy.di_params.month), 11),
            ytg_days(legacy.di_params.month),
            realized(legacy.selic_monthly, legacy.di_params.month, legacy.di_params.quarter),
            Year1.CALENDAR,
        ),
        "inflation": StageSpec(
            Basis.LEGACY_RECURSIVE,
            cuts_fixed_252(ytg_days(legacy.inflation_params.month), 11),
            ytg_days(legacy.inflation_params.month),
            realized(
                legacy.ipca_monthly,
                legacy.inflation_params.month,
                legacy.inflation_params.quarter,
            ),
            Year1.CALENDAR,
        ),
        "cds": StageSpec(
            Basis.LEGACY_RECURSIVE,
            cuts_fixed_252(legacy.cds_ytg_days, 11),
            legacy.cds_ytg_days,
            1.0,
            Year1.ANNUALIZED_REMAINING,
        ),
    }
    du = corrected.year_end_business_days
    du0 = du[0]
    targets = {
        "di": (corrected.cdi_realized_factor, du0),
        "inflation": (corrected.ipca_realized_factor, corrected.inflation_gap_business_days),
        "cds": (1.0, du0),
    }

    def step(name: str, change: Callable[[str, StageSpec], StageSpec]) -> None:
        for key, spec in list(legacy_specs.items()):
            legacy_specs[key] = change(key, spec)
        di = stage_rates(setups["di"], legacy_specs["di"])
        inflation = stage_rates(setups["inflation"], legacy_specs["inflation"])
        cds = stage_rates(setups["cds"], legacy_specs["cds"])
        stages.append(Stage(name, di, inflation, cds, _real(di, inflation)))

    # 1. anualização: as specs já descrevem o ano civil (o DI!E4 só existe no Dashboard).
    step("anualização", lambda _k, s: s)
    # 2. corte em 31/12: 1º corte = dU(Y₀); anos seguintes ainda de 252.
    step(
        "corte em 31/12",
        lambda _k, s: StageSpec(s.basis, cuts_fixed_252(du0, 11), du0, s.realized_factor, s.year1),
    )
    # 3. realizado: CDI/IPCA reais; na inflação, o intervalo após o último IPCA (E8.6).
    step(
        "realizado",
        lambda k, s: StageSpec(s.basis, s.cuts, targets[k][1], targets[k][0], s.year1),
    )
    # 4. calendário: cortes em dU(Y) de cada ano.
    step(
        "calendário",
        lambda _k, s: StageSpec(s.basis, tuple(du), s.first_year_days, s.realized_factor, s.year1),
    )
    # 5. acumulação: fator spot sobre a mesma grade linear.
    step(
        "acumulação",
        lambda _k, s: StageSpec(
            Basis.LEGACY_SPOT, s.cuts, s.first_year_days, s.realized_factor, s.year1
        ),
    )
    # 6. interpolação: flat-forward com todos os vértices (= CORRIGIDO).
    step(
        "interpolação",
        lambda _k, s: StageSpec(
            Basis.CORRECTED, s.cuts, s.first_year_days, s.realized_factor, s.year1
        ),
    )
    assert tuple(s.name for s in stages) == stage_names(di_curve_fix_pct is not None)
    return tuple(stages)


def contributions(stages: Sequence[Stage], field: str) -> dict[str, tuple[float, ...]]:
    """Variação de cada etapa em relação à anterior, por ano (mesma unidade das taxas)."""
    out: dict[str, tuple[float, ...]] = {}
    for prev, cur in pairwise(stages):
        a, b = getattr(prev, field), getattr(cur, field)
        out[cur.name] = tuple(y - x for x, y in zip(a, b, strict=True))
    return out
