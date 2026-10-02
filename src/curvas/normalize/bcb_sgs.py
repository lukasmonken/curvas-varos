"""Séries do SGS/BCB (JSON da API ``bcdata.sgs.N/dados``)."""

import json
from datetime import date, datetime


def parse_sgs(payload: bytes | str) -> list[tuple[date, float]]:
    """``[{"data": "dd/mm/aaaa", "valor": "0.055131"}, …]`` → ``[(date, float), …]``.

    Datas repetidas ou fora de ordem são erro.
    """
    rows = json.loads(payload)
    if not isinstance(rows, list):
        raise ValueError("resposta do SGS não é uma lista")
    out: list[tuple[date, float]] = []
    for row in rows:
        d = datetime.strptime(row["data"], "%d/%m/%Y").date()
        out.append((d, float(row["valor"])))
    dates = [d for d, _ in out]
    if dates != sorted(set(dates)):
        raise ValueError("datas do SGS repetidas ou fora de ordem")
    return out


def monthly_by_reference(rows: list[tuple[date, float]]) -> dict[tuple[int, int], float]:
    """Série mensal (data = 1º dia do mês de referência) → ``{(ano, mês): valor}``."""
    out: dict[tuple[int, int], float] = {}
    for d, v in rows:
        if d.day != 1:
            raise ValueError(f"série mensal com data fora do dia 1: {d}")
        out[(d.year, d.month)] = v
    return out
