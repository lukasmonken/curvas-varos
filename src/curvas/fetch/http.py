"""HTTP com timeout, retry com backoff exponencial e log estruturado (seção 12)."""

import time
from collections.abc import Callable, Mapping
from typing import Any

import httpx

from curvas import logs
from curvas.config import DEFAULT, HttpConfig

log = logs.get("fetch.http")


class FetchError(RuntimeError):
    """Falha definitiva depois de todas as tentativas."""


def make_client(cfg: HttpConfig = DEFAULT.http, **kwargs: Any) -> httpx.Client:
    timeout = httpx.Timeout(cfg.read_timeout_s, connect=cfg.connect_timeout_s)
    headers = {"User-Agent": cfg.user_agent}
    return httpx.Client(timeout=timeout, headers=headers, follow_redirects=True, **kwargs)


def request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    source: str,
    params: Mapping[str, str] | None = None,
    data: Mapping[str, str] | None = None,
    cfg: HttpConfig = DEFAULT.http,
    sleep: Callable[[float], None] = time.sleep,
    accept: Callable[[httpx.Response], bool] | None = None,
) -> httpx.Response:
    """Faz a requisição; repete em erro de rede, timeout e status transitório.

    Espera ``backoff_base · 2^(tentativa−1)`` segundos (limitado a ``backoff_max``)
    entre tentativas. Status 4xx que não seja 408 ou 429 falha na hora: repetir não
    ajuda. ``accept`` confere o conteúdo de uma resposta 2xx; se recusar, a resposta
    conta como falha transitória (o BCB às vezes devolve 200 com uma página HTML de
    "requisição rejeitada").
    """
    last_error: str = ""
    retry_after: float | None = None
    for attempt in range(1, cfg.max_attempts + 1):
        retry_after = None
        try:
            resp = client.request(method, url, params=params, data=data)
        except (httpx.TimeoutException, httpx.NetworkError, httpx.RemoteProtocolError) as exc:
            last_error = f"{type(exc).__name__}: {exc}"  # transitório: repete
        except httpx.HTTPError as exc:
            # Redirect em loop, corpo corrompido, URL/protocolo inválido: repetir não ajuda.
            log.error(
                "fetch falhou sem retry",
                extra={"source": source, "url": url, "error": f"{type(exc).__name__}: {exc}"},
            )
            raise FetchError(f"{source}: {type(exc).__name__}: {exc} ({url})") from exc
        else:
            if resp.status_code < 400 and accept is not None and not accept(resp):
                last_error = f"HTTP {resp.status_code} com conteúdo inesperado"
            elif resp.status_code < 400:
                log.info(
                    "fetch ok",
                    extra={
                        "source": source,
                        "url": str(resp.url),
                        "status": resp.status_code,
                        "bytes": len(resp.content),
                        "attempt": attempt,
                    },
                )
                return resp
            else:
                last_error = f"HTTP {resp.status_code}"
            if resp.status_code >= 400 and resp.status_code not in cfg.retry_statuses:
                log.error(
                    "fetch falhou sem retry",
                    extra={"source": source, "url": str(resp.url), "status": resp.status_code},
                )
                raise FetchError(f"{source}: {last_error} em {resp.url}")
            retry_after = _retry_after(resp)
        if attempt < cfg.max_attempts:
            wait = min(cfg.backoff_base_s * 2 ** (attempt - 1), cfg.backoff_max_s)
            if retry_after is not None:
                wait = min(max(wait, retry_after), cfg.backoff_max_s)
            log.warning(
                "fetch: nova tentativa",
                extra={
                    "source": source,
                    "url": url,
                    "attempt": attempt,
                    "error": last_error,
                    "wait_s": wait,
                },
            )
            sleep(wait)
    log.error("fetch esgotou tentativas", extra={"source": source, "url": url, "error": last_error})
    raise FetchError(f"{source}: {last_error} depois de {cfg.max_attempts} tentativas ({url})")


def _retry_after(resp: httpx.Response) -> float | None:
    """``Retry-After`` em segundos (só a forma numérica; a forma de data é ignorada)."""
    value = resp.headers.get("Retry-After")
    try:
        return max(float(value), 0.0) if value is not None else None
    except ValueError:
        return None
