"""CSV do dia e do histórico (Parte 1, seção 14): tabela anual nos dois modos, formato longo.

Mesma convenção de ``docs/f2_legado_x_corrigido.csv``: vírgula, ponto decimal, taxas em
decimal ao ano com ``repr`` (precisão total) e célula vazia quando o valor é ``None``.
Com ``show_cds=False`` (Q17), saem as colunas ``cds`` e ``desconto``, que dependem do CDS.
"""

import csv
import io
from collections.abc import Iterator, Sequence
from itertools import pairwise

from curvas.models import RunOutput

# Coluna do CSV → campo de ``AnnualRow``.
COLUMNS: tuple[tuple[str, str], ...] = (
    ("di", "di"),
    ("inflacao", "inflation"),
    ("cds", "cds"),
    ("juro_real", "real"),
    ("desconto", "discount"),
)
CDS_COLUMNS = frozenset({"cds", "desconto"})


def _columns(show_cds: bool) -> list[tuple[str, str]]:
    return [c for c in COLUMNS if show_cds or c[0] not in CDS_COLUMNS]


def _cell(value: float | None) -> str:
    return "" if value is None else repr(value)


def _rows(out: RunOutput, columns: Sequence[tuple[str, str]]) -> Iterator[list[str]]:
    day = out.metadata.as_of_date.isoformat()
    for mode, rows in (("corrigido", out.annual.corrected), ("legado", out.annual.legacy)):
        for row in rows:
            values = [_cell(getattr(row, field)) for _, field in columns]
            yield [day, mode, str(row.year), *values]


def _render(outputs: Sequence[RunOutput], show_cds: bool) -> str:
    columns = _columns(show_cds)
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(["data_base", "modo", "ano", *(name for name, _ in columns)])
    for out in outputs:
        writer.writerows(_rows(out, columns))
    return buf.getvalue()


def render_day_csv(out: RunOutput, *, show_cds: bool = True) -> str:
    """Tabela anual de uma data-base: CORRIGIDO (o padrão do site) e depois LEGADO."""
    return _render([out], show_cds)


def render_history_csv(outputs: Sequence[RunOutput], *, show_cds: bool = True) -> str:
    """Tabela anual de todas as datas-base, em ordem de data. Data-base repetida é erro."""
    ordered = sorted(outputs, key=lambda o: o.metadata.as_of_date)
    for a, b in pairwise(ordered):
        if a.metadata.as_of_date == b.metadata.as_of_date:
            raise ValueError(f"data-base repetida no histórico: {a.metadata.as_of_date}")
    return _render(ordered, show_cds)
