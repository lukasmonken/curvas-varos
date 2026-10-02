"""CDS Brasil (USD) do arquivo manual ``data/manual/cds.csv`` (Q2, seção 12).

Não há coletor automático permitido (``docs/F3_DIAGNOSTICO_CDS.md``). O arquivo é
só de acréscimo; o pipeline usa o último conjunto completo com data ≤ t0 e, se
não for do próprio t0, marca ``stale`` com a data real e gera alerta (``alerts``).
Dado antigo nunca é publicado como se fosse atual. Correção = nova linha com o
mesmo dia e vértice e ``preenchido_em`` posterior.
"""

import csv
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any

from curvas.calendar import BusinessCalendar
from curvas.config import DATA_DIR
from curvas.engine.curves import VertexCurve
from curvas.models import SourceRecord

DEFAULT_PATH = DATA_DIR / "manual" / "cds.csv"
# Prazos em dias úteis, como na planilha (CDS!C8:C16).
VERTEX_DAYS: dict[str, int] = {
    "6M": 126,
    "1A": 252,
    "2A": 504,
    "3A": 756,
    "4A": 1008,
    "5A": 1260,
    "7A": 1764,
    "10A": 2520,
    "20A": 5040,
}
BPS_RANGE = (0.0, 3000.0)


COLUMNS = ["data_referencia", "vertice", "bps", "fonte", "preenchido_por", "preenchido_em"]


class ManualCdsError(ValueError):
    """Arquivo manual de CDS inválido."""


@dataclass(frozen=True)
class CdsQuote:
    reference_date: date
    vertex: str
    bps: float
    source: str
    filled_by: str
    filled_at: datetime
    line: int


@dataclass(frozen=True)
class CdsSnapshot:
    """Curva de CDS de uma data, com o registro da fonte (seção 7) e os alertas (seção 12)."""

    reference_date: date
    bps: tuple[float, ...]  # na ordem de VERTEX_DAYS
    record: SourceRecord
    alerts: tuple[str, ...] = ()

    @property
    def stale(self) -> bool:
        return self.record.stale

    def curve(self) -> VertexCurve:
        """Taxas em decimal (bps ÷ 10.000, E4.5/E8.7)."""
        return VertexCurve(tuple(VERTEX_DAYS.values()), tuple(b / 10_000 for b in self.bps))


def _quote(row: dict[str | None, Any], i: int, calendar: BusinessCalendar | None) -> CdsQuote:
    if None in row or any(v is None for v in row.values()):
        raise ManualCdsError(f"linha {i}: número de colunas diferente do cabeçalho")
    try:
        ref = date.fromisoformat(str(row["data_referencia"]).strip())
        vertex = str(row["vertice"]).strip().upper()
        bps = float(str(row["bps"]))
        source = str(row["fonte"]).strip()
        filled_by = str(row["preenchido_por"]).strip()
        filled_at = datetime.fromisoformat(str(row["preenchido_em"]).strip())
    except (KeyError, ValueError) as exc:
        raise ManualCdsError(f"linha {i} inválida: {row}") from exc
    if vertex not in VERTEX_DAYS:
        raise ManualCdsError(f"linha {i}: vértice desconhecido {vertex!r}")
    if not (math.isfinite(bps) and BPS_RANGE[0] < bps < BPS_RANGE[1]):
        raise ManualCdsError(f"linha {i}: bps fora da faixa: {bps}")
    if not source or not filled_by:
        raise ManualCdsError(f"linha {i}: fonte e preenchido_por são obrigatórios")
    if filled_at.tzinfo is None:
        raise ManualCdsError(f"linha {i}: preenchido_em precisa de fuso (ex.: -03:00)")
    if ref > filled_at.date():
        raise ManualCdsError(f"linha {i}: data de referência {ref} depois do preenchimento")
    if calendar is not None and not calendar.is_business_day(ref):
        raise ManualCdsError(f"linha {i}: {ref} não é dia útil ANBIMA")
    return CdsQuote(ref, vertex, bps, source, filled_by, filled_at, i)


def parse_manual_cds(
    lines: Iterable[str], calendar: BusinessCalendar | None = None
) -> list[CdsQuote]:
    """Lê e valida o arquivo. Para corrigir um valor, acrescente uma linha nova com o
    mesmo dia e vértice e um ``preenchido_em`` posterior: ela substitui a anterior."""
    reader = csv.DictReader(ln for ln in lines if ln.strip() and not ln.startswith("#"))
    if reader.fieldnames != COLUMNS:
        raise ManualCdsError(f"cabeçalho esperado {COLUMNS}, veio {reader.fieldnames}")
    quotes = [_quote(row, i, calendar) for i, row in enumerate(reader, start=1)]
    seen: dict[tuple[date, str], CdsQuote] = {}
    for q in quotes:
        prev = seen.get((q.reference_date, q.vertex))
        if prev is not None and q.filled_at <= prev.filled_at:
            raise ManualCdsError(
                f"linha {q.line}: correção de {q.vertex} em {q.reference_date} precisa de "
                f"preenchido_em posterior ao da linha {prev.line}"
            )
        seen[(q.reference_date, q.vertex)] = q
    return quotes


def cds_snapshot(
    quotes: Iterable[CdsQuote],
    as_of: date,
    *,
    retrieved_at: datetime | None = None,
    path: Path = DEFAULT_PATH,
) -> CdsSnapshot:
    """Último conjunto completo (9 vértices) com data ≤ t0. ``stale`` se a data < t0.

    ``retrieved_at`` padrão: o último ``preenchido_em`` do conjunto, que é quando o
    dado entrou no sistema (determinístico, ao contrário da data do arquivo).

    Gera alertas para: dado defasado, conjunto incompleto mais recente que o usado
    e correções aplicadas.
    """
    by_date: dict[date, dict[str, CdsQuote]] = {}
    corrected: list[CdsQuote] = []
    for q in sorted(quotes, key=lambda q: q.filled_at):
        if q.reference_date <= as_of:
            day = by_date.setdefault(q.reference_date, {})
            if q.vertex in day:
                corrected.append(q)
            day[q.vertex] = q  # a linha mais recente vale
    complete = [d for d, qs in by_date.items() if set(qs) == set(VERTEX_DAYS)]
    if not complete:
        raise ManualCdsError(f"nenhum conjunto completo de CDS até {as_of}")
    ref = max(complete)
    chosen = by_date[ref]
    stale = ref < as_of

    alerts: list[str] = []
    newer_incomplete = sorted(d for d in by_date if d > ref)
    for d in newer_incomplete:
        missing = [v for v in VERTEX_DAYS if v not in by_date[d]]
        alerts.append(f"CDS manual de {d:%d/%m/%Y} incompleto (faltam {', '.join(missing)})")
    reason = None
    if stale:
        reason = (
            f"CDS manual mais recente completo é de {ref:%d/%m/%Y}, "
            f"anterior a t0 ({as_of:%d/%m/%Y})"
        )
        if newer_incomplete:
            reason += "; há conjunto mais recente incompleto"
        alerts.append(f"CDS defasado: usando {ref:%d/%m/%Y} para t0 = {as_of:%d/%m/%Y}")
    for q in corrected:
        if q.reference_date == ref:
            alerts.append(f"CDS {q.vertex} de {ref:%d/%m/%Y} corrigido (linha {q.line})")

    sources = sorted({q.source for q in chosen.values()})
    record = SourceRecord(
        source="cds_manual",
        requested_date=as_of,
        source_date=ref,
        # Data da cópia manual: a fonte original não informa quando publicou.
        publication_date=max(q.filled_at for q in chosen.values()),
        retrieved_at=retrieved_at or max(q.filled_at for q in chosen.values()),
        stale=stale,
        fallback_reason=reason,
        url=f"arquivo:{path.name} ({'; '.join(sources)})",
    )
    return CdsSnapshot(ref, tuple(chosen[v].bps for v in VERTEX_DAYS), record, tuple(alerts))


def load_cds(
    as_of: date,
    *,
    retrieved_at: datetime | None = None,
    path: Path = DEFAULT_PATH,
    calendar: BusinessCalendar | None = None,
) -> CdsSnapshot:
    with path.open(encoding="utf-8") as fh:
        quotes = parse_manual_cds(fh, calendar)
    return cds_snapshot(quotes, as_of, retrieved_at=retrieved_at, path=path)
