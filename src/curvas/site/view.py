"""Tudo o que vira texto no site: formatação pt-BR e o contexto de cada página.

Nenhuma regra de negócio aqui (seção 5): os números vêm prontos do ``RunOutput``; esta
camada escolhe, rotula e formata. O único cálculo é o fator de cada vértice,
F(v) = (1 + s)^(v/252) (E8.2), mostrado ao lado da taxa.

Chave Q17 (``show_cds``): com ``False``, nenhum valor de CDS nem de taxa de desconto
entra no contexto das páginas; os links de coleta continuam.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from curvas.calendar import t0_eve
from curvas.models import Alert, AnnualRow, CurveOut, RunOutput, SourceRecord, Vertex
from curvas.output.json_out import CHANGE, CHANGE_HIDDEN, hide_cds_change

DASH = "—"
MINUS = "−"
MONTHS = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")
MODES: tuple[tuple[str, str], ...] = (("corrected", "CORRIGIDO"), ("legacy", "LEGADO"))
CDS_KEYS = frozenset({"cds", "discount"})


# Formatação -------------------------------------------------------------------------


def num(x: float, digits: int) -> str:
    """``1234.5`` → ``"1.234,50"``; negativo com o sinal de menos tipográfico."""
    text = f"{abs(x):,.{digits}f}".replace(",", "\0").replace(".", ",").replace("\0", ".")
    return MINUS + text if x < 0 and any(c in "123456789" for c in text) else text


def pct(x: float | None, digits: int = 2) -> str:
    """Taxa em decimal → ``"13,97%"``."""
    return DASH if x is None else num(100 * x, digits) + "%"


def pct_points(x: float | None, digits: int = 2) -> str:
    """Valor já em % (IPCA, CDI e Selic mensais) → ``"0,33%"``."""
    return DASH if x is None else num(x, digits) + "%"


def bps(x: float | None, digits: int = 1) -> str:
    """Diferença em bps → ``"+15,2"``, ``"−2,6"`` ou ``"0,0"``."""
    if x is None:
        return DASH
    text = num(x, digits)
    return "+" + text if x > 0 and any(c in "123456789" for c in text) else text


def factor(x: float | None, digits: int = 6) -> str:
    return DASH if x is None else num(x, digits)


def day(d: date | datetime | None) -> str:
    """``"01/10/2026"``; para ``datetime``, só a data."""
    return DASH if d is None else f"{d:%d/%m/%Y}"


def month_year(year: int, month: int) -> str:
    """``"jan/2026"``."""
    return f"{MONTHS[month - 1]}/{year}"


def vertex_factor(v: Vertex) -> float:
    """F(v) = (1 + s)^(v/252) (E8.2)."""
    return float((1 + v.rate) ** (v.days / 252))


# Rótulos ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Column:
    key: str
    label: str


COLUMNS = (
    Column("di", "DI"),
    Column("inflation", "Inflação"),
    Column("cds", "CDS"),
    Column("real", "Juro real"),
    Column("discount", "Taxa de desconto"),
)
CURVE_LABELS = {"di": "DI", "inflation": "Inflação", "cds": "CDS"}
SOURCE_LABELS = {
    "anbima_ettj": "ANBIMA: ETTJ (DI e inflação implícita)",
    "bcb_sgs_12": "BCB: CDI diário (SGS 12)",
    "bcb_sgs_433": "BCB: IPCA mensal (SGS 433)",
    "bcb_sgs_4390": "BCB: Selic mensal (SGS 4390)",
    "bcb_sgs_7478": "BCB: IPCA-15 (SGS 7478)",
    "ibge_calendario": "IBGE: agenda de divulgações",
    "cds_manual": "CDS: cópia manual do Investing.com",
}
ALERT_LEVELS = {"info": "Informação", "warning": "Aviso", "error": "Erro"}


def columns(show_cds: bool) -> tuple[Column, ...]:
    return tuple(c for c in COLUMNS if show_cds or c.key not in CDS_KEYS)


def mode_label(mode: str) -> str:
    return dict(MODES)[mode]


# Visão geral ------------------------------------------------------------------------


@dataclass(frozen=True)
class Row:
    head: str
    cells: tuple[str, ...]
    css: str = ""


@dataclass(frozen=True)
class Item:
    label: str
    value: str


@dataclass(frozen=True)
class ModeTable:
    mode: str
    label: str
    rows: tuple[Row, ...]
    details: tuple[Item, ...]
    notes: tuple[str, ...]


@dataclass(frozen=True)
class SourceView:
    label: str
    status: str  # "ok" | "stale"
    status_text: str
    data_date: str
    publication: str
    reason: str


@dataclass(frozen=True)
class AlertView:
    level: str
    level_text: str
    message: str
    source: str


@dataclass(frozen=True)
class Overview:
    t0: str
    columns: tuple[Column, ...]
    tables: tuple[ModeTable, ...]
    comparison: tuple[Row, ...]
    sources: tuple[SourceView, ...]
    alerts: tuple[AlertView, ...]
    stale_count: int


def _annual_cells(row: AnnualRow, cols: Sequence[Column]) -> tuple[str, ...]:
    return tuple(pct(getattr(row, c.key)) for c in cols)


def _legacy_notes(out: RunOutput, show_cds: bool) -> tuple[tuple[Item, ...], tuple[str, ...]]:
    li = out.inputs.legacy
    month = DASH if li.month is None else month_year(out.metadata.as_of_date.year, li.month)
    quarter = DASH if li.quarter is None else f"{li.quarter}º"
    details = [
        Item("Mês do último IPCA (m)", month),
        Item("Trimestre", quarter),
        Item("YTG (DI e inflação)", f"{li.ytg_days} dias úteis"),
    ]
    if show_cds:
        details.append(Item("YTG do CDS", f"{li.cds_ytg_days} dias úteis"))
    if li.month is None or li.quarter is None:
        return tuple(details), (
            "Linha YTG: indisponível na virada do ano, enquanto o IPCA de janeiro não sai (Q6).",
        )
    # DI!S26 e Inflação!E4 = Π(1 + realizado do trimestre de m) × curva nos YTG dias (E4.3).
    first = 3 * (li.quarter - 1) + 1
    year = out.metadata.as_of_date.year
    months = month_year(year, li.month)
    if first < li.month:
        months = f"{MONTHS[first - 1]}–{months}"
    note = (
        "Linha YTG: acumulados sem anualizar, como a coluna YTG do Dashboard da planilha. "
        f"DI e inflação: o realizado dos meses do trimestre de m ({months}: Selic e IPCA) "
        f"composto com a curva nos {li.ytg_days} dias úteis a partir de t0 (DI!S26 e "
        "Inflação!E4); não é só o período restante do ano."
    )
    if show_cds:
        note += f" CDS: só a curva nos {li.cds_ytg_days} dias úteis a partir de t0 (CDS!J9)."
    return tuple(details), (note,)


def _ytg_row(out: RunOutput, cols: Sequence[Column]) -> Row:
    ytg = out.annual.legacy_ytg
    values = {"di": ytg.di, "inflation": ytg.inflation, "cds": ytg.cds}
    cells = tuple(pct(values[c.key]) if c.key in values else "" for c in cols)
    return Row(f"YTG {out.inputs.legacy.first_year}", cells, "ytg")


def _corrected_details(out: RunOutput, show_cds: bool) -> tuple[Item, ...]:
    if not show_cds:
        return ()
    now = out.annual.corrected_cds_current_year
    year = out.annual.corrected[0].year
    return (
        Item(f"CDS {year}: taxa anualizada do período restante", pct(now.annualized_rate)),
        Item("CDS: acumulado de t0 a 31/12", pct(now.remaining_period_accumulated)),
        Item("Dias úteis restantes no ano", str(now.business_days)),
    )


def _source_view(s: SourceRecord) -> SourceView:
    return SourceView(
        label=SOURCE_LABELS.get(s.source, s.source),
        status="stale" if s.stale else "ok",
        status_text="Defasado" if s.stale else "Atual",
        data_date=day(s.source_date),
        publication=day(s.publication_date),
        reason=s.fallback_reason or "",
    )


# Resto da mensagem de ``json_out.daily_change_alerts`` depois de "<modo> <campo> <ano>:".
_CHANGE_TAIL = re.compile(
    r"^ (?P<change>[+-]?\d+(?:\.\d+)?) bps desde (?P<prev>\d{4}-\d{2}-\d{2}) "
    r"\(limite (?P<limit>\d+) bps\)$"
)


def _change_message(message: str) -> str:
    """Alerta ``variacao_diaria`` com os rótulos e a formatação do site (o JSON fica igual).

    ``"corrected cds 2027: +55.1 bps desde 2026-09-30 (limite 50 bps)"`` →
    ``"CORRIGIDO, CDS 2027: +55,1 bps desde 30/09/2026 (limite de 50 bps)"``; a forma já
    sem o valor (Q17) vira ``"CORRIGIDO, CDS 2027: variação acima do limite"``. Formato
    desconhecido volta igual.
    """
    head = CHANGE.match(message)
    labels = {c.key: c.label for c in COLUMNS}
    if head is None or head["mode"] not in dict(MODES) or head["field"] not in labels:
        return message
    what = f"{mode_label(head['mode'])}, {labels[head['field']]} {head['year']}:"
    tail = message[head.end() :]
    if tail == f" {CHANGE_HIDDEN}":
        return f"{what} {CHANGE_HIDDEN}"
    m = _CHANGE_TAIL.match(tail)
    if m is None:
        return message
    prev = day(date.fromisoformat(m["prev"]))
    return f"{what} {bps(float(m['change']))} bps desde {prev} (limite de {m['limit']} bps)"


def _alert_view(a: Alert, show_cds: bool) -> AlertView:
    if not show_cds:
        a = hide_cds_change(a)  # Q17: a mensagem traz a variação em bps; fica só o fato
    message = _change_message(a.message) if a.code == "variacao_diaria" else a.message
    source = "" if a.source is None else SOURCE_LABELS.get(a.source, a.source)
    return AlertView(a.level, ALERT_LEVELS[a.level], message, source)


def overview(out: RunOutput, show_cds: bool) -> Overview:
    cols = columns(show_cds)
    legacy_details, legacy_notes = _legacy_notes(out, show_cds)
    tables = (
        ModeTable(
            "corrected",
            "CORRIGIDO",
            tuple(Row(str(r.year), _annual_cells(r, cols)) for r in out.annual.corrected),
            _corrected_details(out, show_cds),
            (),
        ),
        ModeTable(
            "legacy",
            "LEGADO",
            (
                *(Row(str(r.year), _annual_cells(r, cols)) for r in out.annual.legacy),
                _ytg_row(out, cols),
            ),
            legacy_details,
            legacy_notes,
        ),
    )
    comparison = tuple(
        Row(str(c.year), tuple(bps(getattr(c, f"{col.key}_bps")) for col in cols))
        for c in out.comparison
    )
    sources = tuple(_source_view(s) for s in out.sources)
    return Overview(
        t0=day(out.metadata.as_of_date),
        columns=cols,
        tables=tables,
        comparison=comparison,
        sources=sources,
        alerts=tuple(_alert_view(a, show_cds) for a in out.alerts),
        stale_count=sum(s.status == "stale" for s in sources),
    )


# Curvas -----------------------------------------------------------------------------


@dataclass(frozen=True)
class VertexTable:
    mode: str
    label: str
    headers: tuple[str, ...]
    rows: tuple[Row, ...]


def vertex_tables(curve: CurveOut, cds_labels: Mapping[int, str]) -> tuple[VertexTable, ...]:
    tables = []
    headers: tuple[str, ...]
    for mode, label in MODES:
        vertices = curve.corrected_vertices if mode == "corrected" else curve.legacy_vertices
        if curve.name == "cds":
            headers = ("Vértice", "Prazo (d.u.)", "bps", "Taxa (a.a.)", "Fator")
            rows = tuple(
                Row(
                    cds_labels.get(v.days, DASH),
                    (
                        str(v.days),
                        num(v.rate * 10_000, 2),
                        pct(v.rate, 4),
                        factor(vertex_factor(v)),
                    ),
                )
                for v in vertices
            )
        else:
            headers = ("Prazo (d.u.)", "Taxa (a.a.)", "Fator")
            rows = tuple(
                Row(str(v.days), (pct(v.rate, 4), factor(vertex_factor(v)))) for v in vertices
            )
        tables.append(VertexTable(mode, label, headers, rows))
    return tuple(tables)


def compare_dates(dates: Sequence[date], t0: date, recent: int = 20) -> tuple[date, ...]:
    """Datas-base anteriores a t0 oferecidas na comparação, da mais recente à mais antiga.

    As ``recent`` mais recentes e, antes delas, a última de cada mês: cada data a mais
    pesa na página, porque os traços vão todos pré-renderizados.
    """
    prior = sorted((d for d in dates if d < t0), reverse=True)
    chosen = prior[:recent]
    months: set[tuple[int, int]] = set()
    for d in prior[recent:]:
        if (d.year, d.month) not in months:
            months.add((d.year, d.month))
            chosen.append(d)
    return tuple(chosen)


# Realizado --------------------------------------------------------------------------


@dataclass(frozen=True)
class Realized:
    ipca: tuple[Row, ...]
    ipca_ytd: str
    ipca_period: str
    ipca_rule: str
    ipca15: str
    cdi: tuple[Row, ...]
    cdi_partial: bool  # algum mês parcial (o de t0) na tabela
    cdi_factor: str
    cdi_accumulated: str
    cdi_period: str
    cdi_business_days: int
    cdi_last_observation: str
    selic: tuple[Row, ...]


def realized(out: RunOutput) -> Realized:
    r, t0 = out.realized, out.metadata.as_of_date
    eve = t0_eve(t0)
    ipca = tuple(
        Row(month_year(m.year, m.month), (pct_points(m.value_pct), day(m.release_date)))
        for m in r.ipca_monthly
    )
    period = (
        f"{month_year(r.ipca_monthly[0].year, r.ipca_monthly[0].month)} a "
        f"{month_year(r.ipca_monthly[-1].year, r.ipca_monthly[-1].month)}"
        if r.ipca_monthly
        else DASH
    )
    ipca15 = (
        "Não usado."
        if r.ipca15_used is None
        else (
            f"IPCA-15 de {month_year(r.ipca15_used.year, r.ipca15_used.month)}: "
            f"{pct_points(r.ipca15_used.value_pct)}, divulgado em "
            f"{day(r.ipca15_used.release_date)}."
        )
    )
    cdi = tuple(
        Row(
            month_year(m.year, m.month),
            (
                pct_points(m.value_pct, 4),
                f"parcial, até {day(eve)} (véspera de t0)"
                if (m.year, m.month) == (t0.year, t0.month)
                else "",
            ),
        )
        for m in r.cdi_monthly
    )
    selic = tuple(
        Row(month_year(m.year, m.month), (pct_points(m.value_pct),)) for m in r.selic_monthly_legacy
    )
    return Realized(
        ipca=ipca,
        ipca_ytd=pct(r.ipca_ytd),
        ipca_period=period,
        ipca_rule=r.ipca_rule,
        ipca15=ipca15,
        cdi=cdi,
        cdi_partial=any(row.cells[1] for row in cdi),
        cdi_factor=factor(r.cdi.factor),
        cdi_accumulated=pct(r.cdi.factor - 1),
        cdi_period=(
            f"{day(r.cdi.start)} a {day(eve)} (véspera de t0 = {day(t0)})"
            if r.cdi.business_days
            else f"nenhum dia útil de CDI no ano antes de t0 (t0 = {day(t0)})"
        ),
        cdi_business_days=r.cdi.business_days,
        cdi_last_observation=day(r.cdi.last_observation),
        selic=selic,
    )


# Histórico --------------------------------------------------------------------------


@dataclass(frozen=True)
class HistoryTable:
    mode: str
    label: str
    years: tuple[int, ...]
    rows: tuple[Row, ...]


def history_years(outputs: Sequence[RunOutput]) -> tuple[int, ...]:
    return tuple(sorted({r.year for o in outputs for r in o.annual.corrected}))


def history_values(
    outputs: Sequence[RunOutput], key: str, mode: str
) -> dict[int, list[float | None]]:
    """Taxa ``key`` de cada ano civil ao longo das datas-base (na ordem de ``outputs``)."""
    years = history_years(outputs)
    table: dict[int, list[float | None]] = {y: [] for y in years}
    for o in outputs:
        rows = {r.year: r for r in getattr(o.annual, mode)}
        for y in years:
            row = rows.get(y)
            table[y].append(None if row is None else getattr(row, key))
    return table


def history_tables(outputs: Sequence[RunOutput], key: str) -> tuple[HistoryTable, ...]:
    years = history_years(outputs)
    tables = []
    for mode, label in MODES:
        values = history_values(outputs, key, mode)
        rows = tuple(
            Row(day(o.metadata.as_of_date), tuple(pct(values[y][i]) for y in years))
            for i, o in reversed(list(enumerate(outputs)))
        )
        tables.append(HistoryTable(mode, label, years, rows))
    return tuple(tables)


# Coleta do CDS ----------------------------------------------------------------------


@dataclass(frozen=True)
class CdsLink:
    label: str
    days: int
    url: str
    value: str


@dataclass(frozen=True)
class CdsCollection:
    links: tuple[CdsLink, ...]
    reference_date: str
    status: str  # "ok" | "stale" | "missing"
    status_text: str
    reason: str
    workflow_url: str | None


def cds_collection(
    out: RunOutput,
    urls: Sequence[tuple[str, str]],
    vertex_days: Mapping[str, int],
    show_cds: bool,
    workflow_url: str | None,
) -> CdsCollection:
    record = next((s for s in out.sources if s.source == "cds_manual"), None)
    values = out.inputs.legacy.cds_bps
    if len(values) != len(urls):
        raise ValueError(f"esperados {len(urls)} vértices de CDS, vieram {len(values)}")
    links = tuple(
        CdsLink(label, vertex_days[label], url, num(value, 2) if show_cds else "")
        for (label, url), value in zip(urls, values, strict=True)
    )
    if record is None:
        status, text = "missing", "Sem registro"
    else:
        status, text = ("stale", "Defasado") if record.stale else ("ok", "Atual")
    return CdsCollection(
        links=links,
        reference_date=day(None if record is None else record.source_date),
        status=status,
        status_text=text,
        reason="" if record is None else record.fallback_reason or "",
        workflow_url=workflow_url,
    )
