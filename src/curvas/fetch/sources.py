"""Coletores das fontes públicas. Só baixam bytes; não interpretam (ver ``normalize``)."""

import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime

import httpx

from curvas.config import DEFAULT, Config
from curvas.fetch.http import request_with_retry


@dataclass(frozen=True)
class Fetched:
    source: str
    url: str
    requested_date: date
    retrieved_at: datetime
    content: bytes


def _now() -> datetime:
    return datetime.now(UTC)


def _is_json(resp: httpx.Response) -> bool:
    """SGS e IBGE respondem JSON; HTML (bloqueio, erro) com status 200 é recusado."""
    return resp.content.lstrip()[:1] in (b"[", b"{")


def fetch_anbima_ettj(
    client: httpx.Client,
    as_of: date,
    *,
    cfg: Config = DEFAULT,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = _now,
) -> Fetched:
    """ETTJ da ANBIMA de ``as_of`` em CSV. Corpo vazio = não publicado (ver normalize).

    A página pública só oferece os últimos 5 dias úteis; por isso o bruto precisa ser gravado
    todo dia útil (a rotina diária é da F4) e não pode ser reconstruído depois.
    """
    data = {"Idioma": "PT", "saida": "csv", "Dt_Ref": f"{as_of:%d/%m/%Y}"}
    resp = request_with_retry(
        client,
        "POST",
        cfg.urls.anbima_ettj_download,
        source=f"anbima_ettj:{as_of:%Y-%m-%d}",
        data=data,
        cfg=cfg.http,
        sleep=sleep,
    )
    return Fetched("anbima_ettj", str(resp.url), as_of, now(), resp.content)


def fetch_sgs(
    client: httpx.Client,
    code: int,
    start: date,
    end: date,
    *,
    as_of: date,
    cfg: Config = DEFAULT,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = _now,
) -> Fetched:
    """Série ``code`` do SGS/BCB entre ``start`` e ``end`` (JSON)."""
    params = {"formato": "json", "dataInicial": f"{start:%d/%m/%Y}", "dataFinal": f"{end:%d/%m/%Y}"}
    url = cfg.urls.bcb_sgs.format(code=code)
    resp = request_with_retry(
        client,
        "GET",
        url,
        source=f"bcb_sgs_{code}",
        params=params,
        cfg=cfg.http,
        sleep=sleep,
        accept=_is_json,
    )
    return Fetched(f"bcb_sgs_{code}", str(resp.url), as_of, now(), resp.content)


def fetch_ibge_calendar(
    client: httpx.Client,
    start: date,
    end: date,
    *,
    as_of: date,
    cfg: Config = DEFAULT,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], datetime] = _now,
) -> Fetched:
    """Agenda de divulgações do IBGE (uma página com até 1000 itens)."""
    params = {"de": f"{start:%m-%d-%Y}", "ate": f"{end:%m-%d-%Y}", "qtd": "1000"}
    resp = request_with_retry(
        client,
        "GET",
        cfg.urls.ibge_calendario,
        source="ibge_calendario",
        params=params,
        cfg=cfg.http,
        sleep=sleep,
        accept=_is_json,
    )
    return Fetched("ibge_calendario", str(resp.url), as_of, now(), resp.content)
