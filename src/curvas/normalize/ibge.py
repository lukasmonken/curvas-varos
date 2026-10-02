"""Calendário de divulgações do IBGE (API ``servicodados.ibge.gov.br/api/v3/calendario``)."""

import json
from datetime import datetime

from curvas.engine.corrected import IpcaRelease

IPCA_TITLE = "Índice Nacional de Preços ao Consumidor Amplo"
IPCA15_TITLE = "Índice Nacional de Preços ao Consumidor Amplo 15"


def parse_ipca_releases(payload: bytes | str, title: str = IPCA_TITLE) -> list[IpcaRelease]:
    """Divulgações com o título exato (IPCA por padrão; IPCA-15 com ``IPCA15_TITLE``)."""
    data = json.loads(payload)
    items = data["items"] if isinstance(data, dict) else data
    if isinstance(data, dict) and (
        data.get("totalPages", 1) != 1 or data.get("count", len(items)) != len(items)
    ):
        raise ValueError("resposta paginada do calendário do IBGE: faltam páginas")
    out: list[IpcaRelease] = []
    for item in items:
        if item.get("titulo") != title:
            continue
        released = datetime.strptime(item["data_divulgacao"], "%d/%m/%Y %H:%M:%S").date()
        out.append(
            IpcaRelease(
                ref_year=int(item["ano_referencia_inicio"]),
                ref_month=int(item["mes_referencia_inicio"]),
                release_date=released,
            )
        )
    return sorted(out, key=lambda r: r.release_date)
