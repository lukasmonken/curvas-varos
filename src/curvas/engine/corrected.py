"""Modo CORRIGIDO (E8). Funções puras; o calendário entra como contagens de dias úteis.

Implementa exatamente E8, sem correções adicionais:

- fatores a partir da curva spot: ``F(v) = (1 + s(v))^(v/252)`` (E8.2);
- interpolação flat-forward; antes do 1º vértice, spot constante; depois do
  último, a forward do último segmento (E8.3). A interpolação linear nas taxas
  existe só como parâmetro de comparação;
- cortes por ano civil ``dU(Y)`` (E8.4) e taxas por ano (E8.5);
- realizado: CDI diário até t0 e IPCA até o último mês divulgado, com o intervalo
  coberto pela curva (E8.6);
- CDS com ``annualized_rate`` e ``remaining_period_accumulated`` (E8.7);
- juro real ``(1 + DI)/(1 + Inflação) − 1`` (E8.8).
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from itertools import pairwise

from curvas.engine.annual import forward_rate, product_of_one_plus
from curvas.engine.curves import BUSINESS_DAYS_PER_YEAR, VertexCurve


class Interpolation(StrEnum):
    """Método de interpolação dos fatores (E8.3)."""

    FLAT_FORWARD = "flat_forward"
    LINEAR = "linear"  # só para comparação


def vertex_factor(rate: float, days: int) -> float:
    """``F(v) = (1 + s(v))^(v/252)`` (E8.2)."""
    return math.pow(1 + rate, days / BUSINESS_DAYS_PER_YEAR)


@dataclass(frozen=True)
class FactorCurve:
    """Fator acumulado ``F(d)`` de t0 até ``d`` dias úteis (E8.2, E8.3)."""

    curve: VertexCurve
    interpolation: Interpolation = Interpolation.FLAT_FORWARD

    def factor(self, d: int) -> float:
        """``F(d)``; ``F(0) = 1``. Nos vértices devolve exatamente ``F(v)`` (reprecificação)."""
        if d < 0:
            raise ValueError(f"prazo negativo: {d}")
        if d == 0:
            return 1.0
        if self.interpolation is Interpolation.LINEAR:
            return vertex_factor(self._linear_rate(d), d)
        return self._flat_forward(d)

    def rate(self, d: int) -> float:
        """Taxa spot implícita em ``F(d)``, base 252: ``F(d)^(252/d) − 1``."""
        if d <= 0:
            raise ValueError(f"prazo precisa ser positivo: {d}")
        return math.pow(self.factor(d), BUSINESS_DAYS_PER_YEAR / d) - 1

    def _flat_forward(self, d: int) -> float:
        days, rates = self.curve.days, self.curve.rates
        if d <= days[0]:
            # Antes do 1º vértice: spot constante, F(d) = (1+s(v₁))^(d/252).
            return vertex_factor(rates[0], d)
        k = _segment(days, d)
        if k < len(days):
            if d == days[k]:
                return vertex_factor(rates[k], days[k])
            left, right = days[k - 1], days[k]
            f_left = vertex_factor(rates[k - 1], left)
            f_right = vertex_factor(rates[k], right)
            # F(d) = F(v1) · (F(v2)/F(v1))^((d − v1)/(v2 − v1))
            return f_left * math.pow(f_right / f_left, (d - left) / (right - left))
        # Depois do último vértice: mantém a forward do último segmento.
        last = days[-1]
        f_last = vertex_factor(rates[-1], last)
        if len(days) == 1:
            return vertex_factor(rates[0], d)  # o único segmento é [0, v₁]: spot constante
        prev = days[-2]
        f_prev = vertex_factor(rates[-2], prev)
        return f_last * math.pow(f_last / f_prev, (d - last) / (last - prev))

    def _linear_rate(self, d: int) -> float:
        days, rates = self.curve.days, self.curve.rates
        if d <= days[0]:
            return rates[0]
        if d >= days[-1]:
            return rates[-1]
        k = _segment(days, d)
        left, right = days[k - 1], days[k]
        return rates[k - 1] + (rates[k] - rates[k - 1]) * (d - left) / (right - left)


def _segment(days: Sequence[int], d: int) -> int:
    """Índice do primeiro vértice ``>= d`` (``len(days)`` se ``d`` passa do último)."""
    for i, v in enumerate(days):
        if v >= d:
            return i
    return len(days)


@dataclass(frozen=True)
class CalendarYearRates:
    """Taxas por ano civil de uma curva (E8.5)."""

    years: tuple[int, ...]
    rates: tuple[float, ...]
    first_year_curve_days: int  # dias úteis usados na curva no ano corrente
    realized_factor: float


def calendar_year_rates(
    curve: FactorCurve,
    first_year: int,
    year_end_days: Sequence[int],
    *,
    realized_factor: float = 1.0,
    first_year_curve_days: int | None = None,
) -> CalendarYearRates:
    """Taxas por ano civil (E8.5).

    - Ano corrente: ``(1 + realizado_YTD) · F(n) − 1``, com ``n = dU(Y₀)`` ou,
      na inflação, os dias contados desde o primeiro dia útil depois do último
      mês realizado (E8.6).
    - Anos seguintes: ``F(dU(Y)) / F(dU(Y−1)) − 1``.
    """
    if not year_end_days:
        raise ValueError("year_end_days vazio")
    if any(b <= a for a, b in pairwise(year_end_days)):
        raise ValueError("dU(Y) precisa ser estritamente crescente")
    n0 = year_end_days[0] if first_year_curve_days is None else first_year_curve_days
    rates = [realized_factor * curve.factor(n0) - 1]
    factors = [curve.factor(d) for d in year_end_days]
    for i in range(1, len(year_end_days)):
        rates.append(factors[i] / factors[i - 1] - 1)
    return CalendarYearRates(
        years=tuple(first_year + i for i in range(len(year_end_days))),
        rates=tuple(rates),
        first_year_curve_days=n0,
        realized_factor=realized_factor,
    )


@dataclass(frozen=True)
class CdsCurrentYear:
    """CDS no ano corrente, com os dois campos rotulados (E8.7)."""

    annualized_rate: float  # F(dU(Y₀))^(252/dU(Y₀)) − 1
    remaining_period_accumulated: float  # F(dU(Y₀)) − 1, sem anualizar
    business_days: int  # dU(Y₀)


def cds_current_year(curve: FactorCurve, business_days: int) -> CdsCurrentYear:
    """Campos do CDS no ano corrente (E8.7)."""
    if business_days <= 0:
        raise ValueError("dU(Y₀) precisa ser positivo")
    f = curve.factor(business_days)
    return CdsCurrentYear(
        annualized_rate=math.pow(f, BUSINESS_DAYS_PER_YEAR / business_days) - 1,
        remaining_period_accumulated=f - 1,
        business_days=business_days,
    )


def real_rate(nominal: float, inflation: float) -> float:
    """``Juro real = (1 + DI)/(1 + Inflação) − 1`` (E8.8)."""
    return forward_rate(nominal, inflation)


# ---------------------------------------------------------------- realizado (E8.6)


def compound_daily_cdi(observations: Mapping[date, float], business_days: Sequence[date]) -> float:
    """Fator ``Π(1 + CDI_d/100)`` nos dias úteis dados (E8.6).

    ``observations`` traz o CDI diário em % a.d. (SGS 12). Todo dia útil precisa
    ter observação; faltar um é erro, nunca preenchimento silencioso.
    """
    missing = [d for d in business_days if d not in observations]
    if missing:
        raise ValueError(f"CDI sem observação em {len(missing)} dia(s) útil(eis): {missing[:5]}")
    return product_of_one_plus([observations[d] / 100 for d in business_days])


class InflationGapRule(StrEnum):
    """Como cobrir o intervalo entre o último IPCA divulgado e t0 (E8.6, Q13)."""

    CURVE = "curve"  # padrão: a curva cobre desde o 1º dia útil após o último IPCA
    IPCA15_SAME_MONTH = "ipca15_same_month"  # Forma A: IPCA-15(M) no lugar do IPCA(M)


@dataclass(frozen=True)
class Ipca15Used:
    """IPCA-15 usado no lugar do IPCA do mesmo mês (Forma A), para o registro no output."""

    ref_year: int
    ref_month: int
    value_pct: float
    release_date: date


@dataclass(frozen=True)
class IpcaRelease:
    """Divulgação do IPCA (ou do IPCA-15) de ``ref_year/ref_month`` em ``release_date``."""

    ref_year: int
    ref_month: int
    release_date: date


def last_published_month(releases: Sequence[IpcaRelease], as_of: date) -> tuple[int, int]:
    """Último mês de referência do IPCA divulgado até ``as_of``, inclusive (E6.6, E8.6)."""
    published = [r for r in releases if r.release_date <= as_of]
    if not published:
        raise ValueError(f"nenhuma divulgação de IPCA até {as_of}")
    last = max(published, key=lambda r: (r.ref_year, r.ref_month))
    return last.ref_year, last.ref_month


def compound_monthly_ipca(
    monthly: Mapping[tuple[int, int], float], year: int, last_month: int
) -> float:
    """Fator ``Π(1 + IPCA_m/100)`` de janeiro até ``last_month`` de ``year`` (E8.6).

    ``last_month = 0`` (nenhum mês do ano divulgado) dá fator 1.
    """
    factors = []
    for m in range(1, last_month + 1):
        if (year, m) not in monthly:
            raise ValueError(f"IPCA de {m:02d}/{year} ausente")
        factors.append(monthly[(year, m)] / 100)
    return product_of_one_plus(factors)


# ---------------------------------------------------------------- resultado


@dataclass(frozen=True)
class CorrectedInputs:
    """Inputs do modo CORRIGIDO. Contagens de dias vêm do calendário ANBIMA."""

    as_of: date
    first_year: int
    di_curve: VertexCurve
    inflation_curve: VertexCurve
    cds_curve: VertexCurve
    year_end_business_days: tuple[int, ...]  # dU(Y) para Y = first_year, …
    cdi_realized_factor: float  # Π(1 + CDI) de 1º/jan até t0 (exclusive)
    ipca_realized_factor: float  # Π(1 + IPCA) de jan até o último mês divulgado
    ipca_last_month: int  # 0 = nenhum mês do ano corrente divulgado
    inflation_gap_business_days: int  # dias úteis do 1º dia útil após esse mês até 31/12
    interpolation: Interpolation = Interpolation.FLAT_FORWARD
    # Último IPCA divulgado até t0 (ano, mês) e a data dessa divulgação; só para o registro.
    ipca_last_published: tuple[int, int] | None = None
    ipca_last_release_date: date | None = None
    # Forma A (Q13): IPCA-15 do mês seguinte ao último IPCA, já incluído em
    # ipca_realized_factor; o intervalo de curva começa no mês depois dele.
    ipca15_used: Ipca15Used | None = None
    gap_rule: InflationGapRule = InflationGapRule.CURVE  # regra pedida (registro no output)
    ipca15_pending_release: date | None = None  # Forma A ligada, IPCA-15 de M ainda não saiu

    def __post_init__(self) -> None:
        if not 0 <= self.ipca_last_month <= 12:
            raise ValueError("ipca_last_month fora de 0..12")
        if self.inflation_gap_business_days < 0:
            raise ValueError("intervalo da inflação negativo")
        if (
            self.ipca15_used is None
            and self.inflation_gap_business_days < self.year_end_business_days[0]
        ):
            # Sem IPCA-15, o intervalo começa antes de t0 e não pode ser menor que dU(Y₀).
            raise ValueError("o intervalo da inflação não pode ser menor que dU(Y₀)")
        for name in ("cdi_realized_factor", "ipca_realized_factor"):
            value = getattr(self, name)
            if not (math.isfinite(value) and value > 0):
                raise ValueError(f"{name} inválido: {value}")


@dataclass(frozen=True)
class CorrectedResult:
    """Saídas do CORRIGIDO por ano civil."""

    years: tuple[int, ...]
    di: tuple[float, ...]
    inflation: tuple[float, ...]
    cds: tuple[float, ...]  # ano corrente = annualized_rate
    real: tuple[float, ...]
    cds_current_year: CdsCurrentYear
    inflation_gap_rule: str


def inflation_gap_rule(inputs: CorrectedInputs) -> str:
    """Texto da regra aplicada ao IPCA ainda não divulgado, gravado no output (E8.6, E11)."""
    year, m, gap = inputs.first_year, inputs.ipca_last_month, inputs.inflation_gap_business_days
    last = ""
    if inputs.ipca_last_published is not None:
        ly, lm = inputs.ipca_last_published
        last = f"último IPCA divulgado até t0: {lm:02d}/{ly}"
        if inputs.ipca_last_release_date is not None:
            last += f", em {inputs.ipca_last_release_date:%d/%m/%Y}"
        last = f" ({last})"
    if inputs.ipca15_used is not None:
        u = inputs.ipca15_used
        base = (
            f"IPCA realizado de 01/{year} a {m:02d}/{year}{last}"
            if m
            else (f"Nenhum IPCA de {year} divulgado até t0{last}")
        )
        nxt = u.ref_month + 1
        tail = (
            f"De 01/{nxt:02d}/{year} a 31/12/{year}, coberto pela curva: {gap} dias úteis"
            if u.ref_month < 12
            else "nada coberto pela curva"
        )
        value = f"{u.value_pct:+.2f}".replace(".", ",").replace("-", "−")
        return (
            f"{base}. IPCA-15 de {u.ref_month:02d}/{u.ref_year} ({value}%, divulgado "
            f"em {u.release_date:%d/%m/%Y}) no lugar do IPCA desse mês (Forma A, Q13). {tail} "
            f"(E8.6)."
        )
    pending = ""
    if inputs.gap_rule is InflationGapRule.IPCA15_SAME_MONTH:
        when = inputs.ipca15_pending_release
        pending = (
            f" Forma A (IPCA-15) ligada, mas o IPCA-15 de {m + 1:02d}/{year} só sai em "
            f"{when:%d/%m/%Y}: vale a curva."
            if when is not None
            else " Forma A (IPCA-15) ligada, sem IPCA-15 aplicável: vale a curva."
        )
    if m == 0:
        return (
            f"Nenhum IPCA de {year} divulgado até t0{last}. Ano inteiro coberto pela curva: "
            f"{gap} dias úteis de 01/01/{year} a 31/12/{year} (E8.6).{pending}"
        )
    if m == 12:
        return (
            f"IPCA realizado de 01/{year} a 12/{year}{last}; nada coberto pela curva (E8.6)."
            f"{pending}"
        )
    return (
        f"IPCA realizado de 01/{year} a {m:02d}/{year}{last}. De 01/{m + 1:02d}/{year} a "
        f"31/12/{year}, coberto pela curva: {gap} dias úteis contados do 1º dia útil após o "
        f"último mês realizado (E8.6).{pending}"
    )


def compute_corrected(inputs: CorrectedInputs) -> CorrectedResult:
    """Calcula DI, Inflação, CDS e juro real por ano civil (E8)."""
    du = inputs.year_end_business_days
    di_curve = FactorCurve(inputs.di_curve, inputs.interpolation)
    inf_curve = FactorCurve(inputs.inflation_curve, inputs.interpolation)
    cds_curve = FactorCurve(inputs.cds_curve, inputs.interpolation)

    di = calendar_year_rates(
        di_curve, inputs.first_year, du, realized_factor=inputs.cdi_realized_factor
    )
    inflation = calendar_year_rates(
        inf_curve,
        inputs.first_year,
        du,
        realized_factor=inputs.ipca_realized_factor,
        first_year_curve_days=inputs.inflation_gap_business_days,
    )
    cds = calendar_year_rates(cds_curve, inputs.first_year, du)
    cds_now = cds_current_year(cds_curve, du[0])
    cds_rates = (cds_now.annualized_rate, *cds.rates[1:])
    real = tuple(real_rate(n, i) for n, i in zip(di.rates, inflation.rates, strict=True))

    rule = inflation_gap_rule(inputs)
    return CorrectedResult(
        years=di.years,
        di=di.rates,
        inflation=inflation.rates,
        cds=cds_rates,
        real=real,
        cds_current_year=cds_now,
        inflation_gap_rule=rule,
    )
