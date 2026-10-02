"""Modo LEGADO: reprodução fórmula a fórmula da planilha ``Query-Avila.xlsx``.

O modo tem dois usos (Parte 1, seção 8):

- (a) validação: parâmetros exatamente como na planilha (Inflação e DI em
  Janeiro/1º Tri, YTG do CDS digitado = 62). Esse uso existe só nos testes.
- (b) execução diária: as mesmas fórmulas, com mês, trimestre e YTG derivados
  de t0 e iguais nas três curvas. A derivação fica fora deste módulo (fase F4,
  questão Q6 em ``OPEN_QUESTIONS.md``).

Este módulo não sabe qual uso está rodando: recebe os parâmetros prontos. Cada
passo cita a célula de origem; a ordem das operações é a mesma da planilha.
As divergências em relação à especificação (D1 a D7) estão em
``docs/F0_AUDITORIA.md``.

Erros da planilha:

- ``#N/A`` de ``VLOOKUP`` exato (corte fora da grade, como YTG = 0 em Dezembro)
  vira ``None`` e se propaga só para as células que dependem dele, como na
  planilha. As três abas continuam independentes.
- ``#NUM!`` e ``#DIV/0!`` (só com taxas ≤ −100%) levantam ``ValueError`` e
  ``ZeroDivisionError``. É a única divergência de comportamento de erro.
"""

import math
from collections.abc import Sequence
from dataclasses import dataclass

from curvas.engine.annual import (
    annualize,
    compound,
    cuts_fixed_252,
    forward_rate,
    product_of_one_plus,
)
from curvas.engine.curves import (
    BUSINESS_DAYS_PER_YEAR,
    GridLookupError,
    VertexCurve,
    accumulate_recursive,
    grid_value,
    linear_incremental_grid,
)

Cell = float | None
"""Valor de uma célula de saída. ``None`` representa ``#N/A``."""

# Listas de validação da planilha.
MONTH_LABELS: tuple[str, ...] = (  # DI!E9:E20 e Inflação!E9:E20
    "Janeiro",
    "Fevereiro",
    "Março",
    "Abril",
    "Maio",
    "Junho",
    "Julho",
    "Agosto",
    "Setembro",
    "Outubro",
    "Novembro",
    "Dezembro",
)
QUARTER_LABELS: tuple[str, ...] = ("1º Tri", "2º Tri", "3º Tri", "4º Tri")  # DI!Q3:Q6
QUARTER_OF_MONTH: tuple[int, ...] = (1, 1, 1, 2, 2, 2, 3, 3, 3, 4, 4, 4)  # DI!R11:R22

# Geometria das abas Inflação e DI. O vértice k fica na linha 126·k + 2
# (DI!X128 = C7, X254 = C8, …, X2396 = C25): 19 vértices de 126 a 2394.
# Dashboard!C30:C31 (2520 e 2646) não são lidos por nenhuma fórmula.
RATE_SHEET_VERTEX_DAYS: tuple[int, ...] = tuple(126 * k for k in range(1, 20))
RATE_SHEET_STEP = 126.0  # divisor literal em DI!X129 = X128+($C$8-$C$7)/126
DI_GRID_LAST_DAY = 2998  # DI!W3000
INFLATION_GRID_LAST_DAY = 3000  # Inflação!W3002

# Geometria da aba CDS: CDS!C8:C16 (=126, =252, =252*2, …, =252*20).
CDS_VERTEX_DAYS: tuple[int, ...] = (126, 252, 504, 756, 1008, 1260, 1764, 2520, 5040)
CDS_GRID_LAST_DAY = 5040  # CDS!L5047

N_YEARS = 11  # colunas E:O das abas e F:P do Dashboard


def _lookup_label(label: str, labels: Sequence[str], what: str) -> int:
    # VLOOKUP exato do Excel: ignora maiúsculas/minúsculas, mas não espaços.
    wanted = label.casefold()
    for i, name in enumerate(labels, start=1):
        if name.casefold() == wanted:
            return i
    raise ValueError(f"{what} desconhecido: {label!r}")


def month_number(label: str) -> int:
    """Campo "Mês Atual" (E4.3): ``VLOOKUP($C$2,$E$9:$F$20,2,FALSE)``, nome → 1..12."""
    return _lookup_label(label, MONTH_LABELS, "mês")


def quarter_number(label: str) -> int:
    """Campo "Trimestre Atual" (E4.3): ``VLOOKUP($C$3,$Q$3:$R$6,2,FALSE)``, rótulo → 1..4."""
    return _lookup_label(label, QUARTER_LABELS, "trimestre")


def _require_int(value: object, name: str) -> None:
    if type(value) is not int:
        raise TypeError(f"{name} precisa ser int, recebeu {type(value).__name__}")


def _require_finite(values: Sequence[float], name: str) -> None:
    if not all(math.isfinite(v) for v in values):
        raise ValueError(f"{name} contém valor não finito")


@dataclass(frozen=True)
class SheetParams:
    """Campos "Mês Atual" (``C2``) e "Trimestre Atual" (``C3``) de uma aba (E4.3, E6.2)."""

    month: int
    quarter: int

    def __post_init__(self) -> None:
        _require_int(self.month, "month")
        _require_int(self.quarter, "quarter")
        # month = 0 é a extensão do uso (b) para "nenhum mês do ano realizado" (virada
        # do ano, Q6): YTG = 252, sem realizado. A planilha não representa esse caso.
        if not 0 <= self.month <= 12:
            raise ValueError(f"mês fora de 0..12: {self.month}")
        if self.month == 0 and self.quarter != 1:
            raise ValueError("mês 0 (nenhum realizado) exige o 1º trimestre")
        if not 1 <= self.quarter <= 4:
            raise ValueError(f"trimestre fora de 1..4: {self.quarter}")

    @classmethod
    def from_labels(cls, month_label: str, quarter_label: str) -> "SheetParams":
        """Parâmetros a partir dos rótulos da planilha ("Janeiro", "1º Tri") (E4.3)."""
        return cls(month_number(month_label), quarter_number(quarter_label))


@dataclass(frozen=True)
class LegacyInputs:
    """Inputs no formato do Dashboard da planilha (E3.2).

    As taxas das curvas ficam em % (como digitadas) e o CDS em bps. A conversão
    para decimal acontece dentro do cálculo, como nas abas (``DI!C7 =
    Dashboard!F11/100``, ``CDS!F8 = E8/10000``).
    """

    first_year: int  # Dashboard!F3
    inflation_curve_pct: tuple[float, ...]  # Dashboard!C11:C29
    di_curve_pct: tuple[float, ...]  # Dashboard!F11:F29
    cds_bps: tuple[float, ...]  # Dashboard!I9:I17
    ipca_monthly: tuple[float, ...]  # Dashboard!I20:I31 (Jan…Dez, decimal)
    selic_monthly: tuple[float, ...]  # Dashboard!L20:L31 (Jan…Dez, decimal)
    inflation_params: SheetParams  # Inflação!C2:C3
    di_params: SheetParams  # DI!C2:C3
    cds_ytg_days: int  # CDS!I9 (digitado, "<- Mudar")

    def __post_init__(self) -> None:
        _require_int(self.first_year, "first_year")
        _require_int(self.cds_ytg_days, "cds_ytg_days")
        n_rate = len(RATE_SHEET_VERTEX_DAYS)
        if len(self.inflation_curve_pct) != n_rate or len(self.di_curve_pct) != n_rate:
            raise ValueError(f"as curvas de inflação e DI precisam de {n_rate} vértices")
        if len(self.cds_bps) != len(CDS_VERTEX_DAYS):
            raise ValueError(f"o CDS precisa de {len(CDS_VERTEX_DAYS)} vértices")
        if len(self.ipca_monthly) != 12 or len(self.selic_monthly) != 12:
            raise ValueError("o realizado mensal precisa de 12 valores (Jan…Dez)")
        # A planilha não tem NaN (célula vazia vale 0); no pipeline, NaN é dado faltando.
        for name in (
            "inflation_curve_pct",
            "di_curve_pct",
            "cds_bps",
            "ipca_monthly",
            "selic_monthly",
        ):
            _require_finite(getattr(self, name), name)


@dataclass(frozen=True)
class RateSheetResult:
    """Saídas de uma aba Inflação ou DI. ``None`` = ``#N/A``."""

    daily_rate: tuple[float, ...]  # X3:X…
    accumulated: tuple[float, ...]  # Y3:Y…
    usage_current: tuple[float, ...]  # T11:T22 ("Usar")
    usage_previous: tuple[float, ...]  # U11:U22 ("Usar")
    quarterly: tuple[float | None, ...]  # S3:S6 (None = "-")
    ytg_days: int  # R26
    cuts: tuple[int, ...]  # R26, R28:R37
    ytg_accumulated: Cell  # S26
    calendar_year1: Cell  # S27 (= H6)
    forwards: tuple[Cell, ...]  # S28:S37
    headline: tuple[Cell, ...]  # E4:O4


@dataclass(frozen=True)
class CdsSheetResult:
    """Saídas da aba CDS. ``None`` = ``#N/A``."""

    vertex_rates: tuple[float, ...]  # F8:F16
    daily_rate: tuple[float, ...]  # M8:M5047
    accumulated: tuple[float, ...]  # N8:N5047
    cuts: tuple[int, ...]  # I9:I19
    ytg_accumulated: Cell  # J9
    forwards: tuple[Cell, ...]  # J10:J19
    headline: tuple[Cell, ...]  # E4:O4


@dataclass(frozen=True)
class LegacyDashboard:
    """Bloco de projeções do Dashboard (``F3:Q6``). ``None`` = ``#N/A``."""

    years: tuple[int, ...]  # F3:P3
    di: tuple[Cell, ...]  # F4:P4
    cds: tuple[Cell, ...]  # F5:P5
    inflation: tuple[Cell, ...]  # F6:P6
    di_ytg: Cell  # Q4 = DI!S26
    cds_ytg: Cell  # Q5 = CDS!J9
    inflation_ytg: Cell  # Q6 = Inflação!E4 (= S26)


@dataclass(frozen=True)
class LegacyResult:
    """Resultado completo do LEGADO: as três abas e o Dashboard (E3.3)."""

    inflation: RateSheetResult
    di: RateSheetResult
    cds: CdsSheetResult
    dashboard: LegacyDashboard


def vlookup_exact(grid: Sequence[float], day: int) -> Cell:
    """``VLOOKUP(dia, grade, n, FALSE)`` com ``#N/A`` → ``None`` (E4.4)."""
    try:
        return grid_value(grid, day)
    except GridLookupError:
        return None


def _forward(acc_end: Cell, acc_start: Cell) -> Cell:
    # (1+VLOOKUP(fim))/(1+VLOOKUP(início))-1; #N/A em qualquer lado propaga.
    if acc_end is None or acc_start is None:
        return None
    return forward_rate(acc_end, acc_start)


def _forwards_at_cuts(accumulated: Sequence[float], cuts: Sequence[int]) -> tuple[Cell, ...]:
    values = [vlookup_exact(accumulated, c) for c in cuts]
    return tuple(_forward(values[i], values[i - 1]) for i in range(1, len(values)))


def usage_matrix(
    monthly: Sequence[float], params: SheetParams
) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Matriz "Usar" do realizado (E4.3; divergência D1 da F0).

    - ``T_i`` (``DI!T11 = IF(AND(R11>q−1, S11<=m), G9, 0)``): meses do trimestre
      ``q`` em diante, até o mês ``m``. Entram no dia 1 da acumulação.
    - ``U_i`` (``DI!U11 = IF(R11<q, G9, 0)``): meses dos trimestres anteriores a
      ``q``, independentemente de ``m``. Entram só no ano 1 (``S27``).
    """
    if len(monthly) != 12:
        raise ValueError("o realizado mensal precisa de 12 valores")
    current: list[float] = []
    previous: list[float] = []
    for i, value in enumerate(monthly):
        month_index = i + 1  # DI!S11:S22
        quarter = QUARTER_OF_MONTH[i]  # DI!R11:R22
        in_current = quarter > params.quarter - 1 and month_index <= params.month
        current.append(value if in_current else 0.0)
        previous.append(value if quarter < params.quarter else 0.0)
    return tuple(current), tuple(previous)


def ytg_days(month: int) -> int:
    """``DI!R26 = (12 − m)·(252/12)``: dias úteis restantes no ano (E4.4).

    Com ``m = 12`` o resultado é 0 e o ``VLOOKUP`` seguinte dá ``#N/A``. ``m = 0``
    (extensão do uso b, Q6) dá 252: o ano inteiro vem da curva.
    """
    if not 0 <= month <= 12:
        raise ValueError(f"mês fora de 0..12: {month}")
    value = (12 - month) * (BUSINESS_DAYS_PER_YEAR / 12)
    if value != int(value):
        raise ValueError(f"YTG não inteiro para o mês {month}: {value}")
    return int(value)


def quarterly_accumulated(monthly: Sequence[float]) -> tuple[float | None, ...]:
    """Acumulados trimestrais auxiliares (E4.3), sem uso nas saídas.

    ``DI!S3 = IF(G11<>0, PRODUCT(1+G9:G11)-1, "-")``: o teste olha só o último mês
    do trimestre. ``"-"`` vira ``None``.
    """
    out: list[float | None] = []
    for q in range(4):
        months = monthly[3 * q : 3 * q + 3]
        out.append(compound(months) if months[2] != 0 else None)
    return tuple(out)


def _rate_sheet(
    curve_pct: Sequence[float],
    monthly: Sequence[float],
    params: SheetParams,
    grid_last_day: int,
    *,
    annualize_year1: bool,
) -> RateSheetResult:
    """Lógica comum às abas Inflação e DI (E4.1 a E4.4)."""
    rates = tuple(p / 100 for p in curve_pct)  # DI!C7 = Dashboard!F11/100
    curve = VertexCurve(RATE_SHEET_VERTEX_DAYS, rates)
    daily_rate = linear_incremental_grid(curve, grid_last_day, step=RATE_SHEET_STEP)  # X

    current, previous = usage_matrix(monthly, params)  # T11:T22, U11:U22
    # DI!Y3 = (PRODUCT(1+T11:T22)*(1+X3)^(1/252))-1 ; Y4 = (1+Y3)*(1+X4)^(1/252) - 1
    accumulated = accumulate_recursive(daily_rate, product_of_one_plus(current))

    ytg = ytg_days(params.month)  # R26
    cuts = cuts_fixed_252(ytg, N_YEARS)  # R26, R28 = R26+252, …, R37
    s26 = vlookup_exact(accumulated, ytg)  # S26 = VLOOKUP(R26,$W$3:$Y$3000,3,FALSE)
    # S27 = (1+S26)*PRODUCT(1+U11:U22)-1
    s27 = None if s26 is None else (1 + s26) * product_of_one_plus(previous) - 1
    forwards = _forwards_at_cuts(accumulated, cuts)  # S28:S37

    e4: Cell
    if s26 is None:
        e4 = None
    elif annualize_year1:
        # DI!E4 = (1+S26)^(4/(5-VLOOKUP(C3,Q3:R6,2,FALSE)))-1 (E4.6, divergência D2)
        e4 = annualize(s26, 4 / (5 - params.quarter))
    else:
        e4 = s26  # Inflação!E4 = S26
    headline = (e4, *forwards)  # E4, F4 = S28, …, O4 = S37

    return RateSheetResult(
        daily_rate=daily_rate,
        accumulated=accumulated,
        usage_current=current,
        usage_previous=previous,
        quarterly=quarterly_accumulated(monthly),
        ytg_days=ytg,
        cuts=cuts,
        ytg_accumulated=s26,
        calendar_year1=s27,
        forwards=forwards,
        headline=headline,
    )


def inflation_sheet(inputs: LegacyInputs) -> RateSheetResult:
    """Aba Inflação (E4). O ano 1 sai sem anualização (``Inflação!E4 = S26``)."""
    return _rate_sheet(
        inputs.inflation_curve_pct,
        inputs.ipca_monthly,  # Inflação!G9 = Dashboard!I20
        inputs.inflation_params,
        INFLATION_GRID_LAST_DAY,
        annualize_year1=False,
    )


def di_sheet(inputs: LegacyInputs) -> RateSheetResult:
    """Aba DI (E4). O ano 1 é anualizado em ``DI!E4`` (E4.6)."""
    return _rate_sheet(
        inputs.di_curve_pct,
        inputs.selic_monthly,  # DI!G9 = Dashboard!L20
        inputs.di_params,
        DI_GRID_LAST_DAY,
        annualize_year1=True,
    )


def cds_sheet(inputs: LegacyInputs) -> CdsSheetResult:
    """Aba CDS (E4.5; divergência D3)."""
    vertex_rates = tuple(b / 10000 for b in inputs.cds_bps)  # CDS!F8 = E8/10000
    curve = VertexCurve(CDS_VERTEX_DAYS, vertex_rates)
    # CDS!M134 = M133+($F$9-$F$8)/($C$9-$C$8): passo = espaçamento real.
    daily_rate = linear_incremental_grid(curve, CDS_GRID_LAST_DAY)
    # CDS!N8 = (1+$M$8)^(1/252) - 1 ; N9 = (1+N8)*((1+M9)^(1/252)) - 1
    accumulated = accumulate_recursive(daily_rate)

    ytg = inputs.cds_ytg_days  # CDS!I9
    cuts = cuts_fixed_252(ytg, N_YEARS)  # I9, I10 = I9+252, …, I19
    j9 = vlookup_exact(accumulated, ytg)  # J9 = VLOOKUP(I9,L8:N5047,3,FALSE)
    forwards = _forwards_at_cuts(accumulated, cuts)  # J10:J19
    # E4 = (1+J9)^(252/I9) - 1. Com I9 <= 0 o VLOOKUP já deu #N/A antes da divisão.
    e4 = None if j9 is None else annualize(j9, BUSINESS_DAYS_PER_YEAR / ytg)
    return CdsSheetResult(
        vertex_rates=vertex_rates,
        daily_rate=daily_rate,
        accumulated=accumulated,
        cuts=cuts,
        ytg_accumulated=j9,
        forwards=forwards,
        headline=(e4, *forwards),  # E4, F4 = J10, …, O4 = J19
    )


def compute_legacy(inputs: LegacyInputs) -> LegacyResult:
    """Calcula as três abas e monta o Dashboard (E3.3 e E4)."""
    inflation = inflation_sheet(inputs)
    di = di_sheet(inputs)
    cds = cds_sheet(inputs)
    dashboard = LegacyDashboard(
        years=tuple(inputs.first_year + i for i in range(N_YEARS)),  # F3, G3 = F3+1, …
        di=di.headline,  # F4 = DI!E4, G4:P4 = DI!F4:O4
        cds=cds.headline,  # F5 = CDS!E4, G5:P5 = CDS!F4:O4
        # F6 = 'Inflação'!H6 (= S27, ano civil); G6:P6 = 'Inflação'!F4:O4
        inflation=(inflation.calendar_year1, *inflation.forwards),
        di_ytg=di.ytg_accumulated,  # Q4 = DI!S26
        cds_ytg=cds.ytg_accumulated,  # Q5 = CDS!J9
        inflation_ytg=inflation.headline[0],  # Q6 = 'Inflação'!E4
    )
    return LegacyResult(inflation=inflation, di=di, cds=cds, dashboard=dashboard)
