"""Coleta manual assistida do CDS (Q16, item 2): sem scraping, só digitação validada.

    python -m curvas.cds_add --data 2026-10-01 --por "Fulano" \\
        --valores "45.67 54.35 67.89 87.28 109.84 130.71 171.71 213.22 245.59"

Os 9 valores são, nesta ordem, os vértices 6M 1A 2A 3A 4A 5A 7A 10A 20A, em bps,
como aparecem no site, separados por espaço; o decimal pode ser vírgula ou ponto
("45,67" ou "45.67"). Sem ``--valores``, o comando pergunta um por um. No GitHub,
o workflow ``cds`` (aba Actions) roda este comando pelo navegador. As linhas
novas passam pela mesma validação do pipeline antes de entrar no arquivo; nada é
gravado se algo estiver errado. Para corrigir um dia já gravado, rode de novo com
os valores certos: a linha mais recente vale (``preenchido_em`` posterior).
"""

import argparse
import os
import sys
import tempfile
from collections.abc import Callable, Sequence
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from curvas.calendar import load_anbima_calendar
from curvas.normalize.cds_manual import (
    COLUMNS,
    DEFAULT_PATH,
    VERTEX_DAYS,
    ManualCdsError,
    cds_snapshot,
    parse_manual_cds,
)

BRT = timezone(timedelta(hours=-3))
DEFAULT_SOURCE = "Investing.com (cópia manual)"


def new_lines(
    day: date,
    values: Sequence[float],
    *,
    filled_by: str,
    source: str,
    filled_at: datetime,
) -> list[str]:
    if len(values) != len(VERTEX_DAYS):
        raise ManualCdsError(f"esperados {len(VERTEX_DAYS)} valores, vieram {len(values)}")
    stamp = filled_at.isoformat(timespec="seconds")
    return [
        f"{day.isoformat()},{vertex},{value},{source},{filled_by},{stamp}\n"
        for vertex, value in zip(VERTEX_DAYS, values, strict=True)
    ]


def append_cds(
    path: Path,
    day: date,
    values: Sequence[float],
    *,
    filled_by: str,
    source: str = DEFAULT_SOURCE,
    filled_at: datetime | None = None,
) -> int:
    """Valida o arquivo inteiro com as linhas novas e só então grava (atomicamente)."""
    if "," in source or "," in filled_by:
        raise ManualCdsError("fonte e nome não podem ter vírgula")
    stamp = filled_at or datetime.now(BRT).replace(microsecond=0)
    current = path.read_text(encoding="utf-8") if path.exists() else ",".join(COLUMNS) + "\n"
    if not current.endswith("\n"):
        current += "\n"
    text = current + "".join(
        new_lines(day, values, filled_by=filled_by, source=source, filled_at=stamp)
    )
    quotes = parse_manual_cds(text.splitlines(True), load_anbima_calendar())
    cds_snapshot(quotes, day)  # o conjunto do dia tem de ficar completo
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)
    return len(VERTEX_DAYS)


def _number(text: str) -> float:
    """Um valor em bps; vírgula ou ponto como decimal ("45,67" = "45.67")."""
    return float(text.strip().replace(",", "."))


def _ask(prompt: Callable[[str], str]) -> list[float]:
    return [_number(prompt(f"CDS {vertex} (bps): ")) for vertex in VERTEX_DAYS]


def main(argv: list[str] | None = None, prompt: Callable[[str], str] = input) -> int:
    parser = argparse.ArgumentParser(prog="python -m curvas.cds_add", description=__doc__)
    parser.add_argument("--data", type=date.fromisoformat, required=True, help="AAAA-MM-DD")
    parser.add_argument("--por", required=True, help="quem está preenchendo")
    parser.add_argument(
        "--valores", help="9 números em bps, separados por espaço (decimal: vírgula ou ponto)"
    )
    parser.add_argument("--fonte", default=DEFAULT_SOURCE)
    parser.add_argument("--arquivo", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args(argv)
    try:
        values = (
            [_number(v) for v in args.valores.split()] if args.valores is not None else _ask(prompt)
        )
        n = append_cds(args.arquivo, args.data, values, filled_by=args.por, source=args.fonte)
    except (ManualCdsError, ValueError) as exc:
        print(f"NADA GRAVADO: {exc}", file=sys.stderr)
        return 1
    print(f"ok: {n} vértices de {args.data:%d/%m/%Y} em {args.arquivo}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
