"""Checagens que bloqueiam o uso de um dado coletado (seção 12)."""

from collections.abc import Sequence
from datetime import date
from itertools import pairwise

from curvas.config import DEFAULT, PlausibleRanges
from curvas.normalize.anbima_ettj import AnbimaEttj


class ValidationError(ValueError):
    """Dado coletado inválido: não pode alimentar o cálculo."""


def _in_range(values: Sequence[tuple[int, float]], bounds: tuple[float, float], what: str) -> None:
    lo, hi = bounds
    bad = [(d, v) for d, v in values if not lo <= v <= hi]
    if bad:
        raise ValidationError(f"{what} fora de [{lo}, {hi}]: {bad[:5]}")


def validate_anbima(
    ettj: AnbimaEttj, requested: date, ranges: PlausibleRanges = DEFAULT.ranges
) -> None:
    """Data certa, vértices crescentes, contagem mínima, faixas e coerência de Fisher."""
    if ettj.reference_date != requested:
        raise ValidationError(f"ANBIMA devolveu {ettj.reference_date}, pedido {requested}")
    days = [r.days for r in ettj.rows]
    if any(b <= a for a, b in pairwise(days)):
        raise ValidationError("vértices da ETTJ fora de ordem")
    for name, col in (("pre", ettj.pre()), ("implied", ettj.implied_inflation())):
        if len(col) < ranges.min_ettj_vertices:
            raise ValidationError(f"ETTJ {name} com {len(col)} vértices")
        # Grade contínua de 126 em 126 (sem buraco nem corte no meio).
        col_days = [d for d, _ in col]
        if col_days != list(range(col_days[0], col_days[0] + 126 * len(col_days), 126)):
            raise ValidationError(f"ETTJ {name} com grade de vértices irregular: {col_days}")
    circ_days = [d for d, _ in ettj.pre_circular_3361]
    if any(b <= a for a, b in pairwise(circ_days)):
        raise ValidationError("vértices da Circular 3.361 fora de ordem ou repetidos")
    pre = dict(ettj.pre())
    for d, v in ettj.pre_circular_3361:
        # Premissa da Q15: a Circular 3.361 é a mesma curva que a ETTJ PREF.
        if d in pre and abs(pre[d] - v) > 1e-9:
            raise ValidationError(f"Circular 3.361 difere da ETTJ PREF no vértice {d}")
    _in_range(ettj.pre(), ranges.pre_pct, "ETTJ PREF")
    _in_range(ettj.real(), ranges.real_pct, "ETTJ IPCA")
    _in_range(ettj.implied_inflation(), ranges.implied_inflation_pct, "inflação implícita")
    _in_range(ettj.pre_circular_3361, ranges.pre_pct, "Circular 3.361")
    # Fisher: (1+pre)/(1+real) − 1 = implícita, a menos do arredondamento de 4 casas.
    for r in ettj.rows:
        if r.pre_pct is not None and r.real_pct is not None and r.implied_pct is not None:
            fisher = ((1 + r.pre_pct / 100) / (1 + r.real_pct / 100) - 1) * 100
            if abs(fisher - r.implied_pct) > 0.002:
                raise ValidationError(f"Fisher não fecha no vértice {r.days}: {fisher:.4f}")


def validate_daily_series(
    rows: Sequence[tuple[date, float]],
    expected_days: Sequence[date],
    bounds: tuple[float, float],
    what: str,
) -> None:
    """Série diária: exatamente os dias úteis esperados e valores na faixa."""
    got = [d for d, _ in rows]
    missing = sorted(set(expected_days) - set(got))
    extra = sorted(set(got) - set(expected_days))
    if missing or extra:
        raise ValidationError(f"{what}: faltam {missing[:5]}, sobram {extra[:5]}")
    lo, hi = bounds
    bad = [(d, v) for d, v in rows if not lo <= v <= hi]
    if bad:
        raise ValidationError(f"{what} fora de [{lo}, {hi}]: {bad[:5]}")
