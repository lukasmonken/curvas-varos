"""Coletores com respostas gravadas, sem rede (Parte 1, seção 10.8)."""

import hashlib
import json
import logging
import multiprocessing
from datetime import UTC, date, datetime
from pathlib import Path

import httpx
import pytest

from conftest import ROOT
from curvas.config import DEFAULT, HttpConfig
from curvas.fetch.http import FetchError, request_with_retry
from curvas.fetch.raw import day_dir, store_raw
from curvas.fetch.sources import fetch_anbima_ettj, fetch_ibge_calendar, fetch_sgs
from curvas.logs import JsonFormatter
from curvas.normalize.anbima_ettj import NotPublishedError, parse_anbima_ettj
from curvas.normalize.bcb_sgs import parse_sgs
from curvas.normalize.ibge import parse_ipca_releases

ANBIMA = ROOT / "tests" / "fixtures" / "f3" / "anbima"
F2 = ROOT / "tests" / "fixtures" / "f2"
FIXED_NOW = datetime(2026, 9, 29, 21, 0, tzinfo=UTC)


def client_for(handler: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=handler)


class TestRetry:
    def test_backoff_exponencial_ate_dar_certo(self) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(503 if len(calls) < 3 else 200, content=b"ok")

        waits: list[float] = []
        resp = request_with_retry(
            client_for(httpx.MockTransport(handler)),
            "GET",
            "https://x.test/a",
            source="t",
            sleep=waits.append,
        )
        assert resp.content == b"ok"
        assert waits == [2.0, 4.0]

    def test_erro_de_rede_e_timeout_repetem(self) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                raise httpx.ConnectError("sem rede", request=request)
            if len(calls) == 2:
                raise httpx.ReadTimeout("lento", request=request)
            return httpx.Response(200, content=b"ok")

        waits: list[float] = []
        request_with_retry(
            client_for(httpx.MockTransport(handler)), "GET", "https://x.test", source="t",
            sleep=waits.append,
        )  # fmt: skip
        assert len(calls) == 3

    def test_esgota_tentativas(self) -> None:
        cfg = HttpConfig(max_attempts=3, backoff_base_s=1.0, backoff_max_s=1.5)
        waits: list[float] = []
        with pytest.raises(FetchError, match="3 tentativas"):
            request_with_retry(
                client_for(httpx.MockTransport(lambda r: httpx.Response(500))),
                "GET",
                "https://x.test",
                source="t",
                cfg=cfg,
                sleep=waits.append,
            )
        assert waits == [1.0, 1.5]  # limitado por backoff_max_s

    def test_4xx_nao_repete(self) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            return httpx.Response(403)

        with pytest.raises(FetchError, match="HTTP 403"):
            request_with_retry(
                client_for(httpx.MockTransport(handler)), "GET", "https://x.test", source="t",
                sleep=lambda _s: None,
            )  # fmt: skip
        assert len(calls) == 1

    def test_timeouts_configurados(self) -> None:
        assert DEFAULT.http.connect_timeout_s > 0
        assert DEFAULT.http.read_timeout_s > 0


class TestAnbima:
    def test_pedido_e_resposta_gravada(self) -> None:
        body = (ANBIMA / "cz_2026-09-29.csv").read_bytes()
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["method"] = request.method
            seen["body"] = request.content.decode()
            return httpx.Response(200, content=body, headers={"content-type": "text/csv"})

        got = fetch_anbima_ettj(
            client_for(httpx.MockTransport(handler)), date(2026, 9, 29), now=lambda: FIXED_NOW
        )
        assert seen["method"] == "POST"
        assert "Dt_Ref=29%2F09%2F2026" in seen["body"]
        assert "saida=csv" in seen["body"]
        assert got.content == body
        assert got.retrieved_at == FIXED_NOW
        assert parse_anbima_ettj(got.content).reference_date == date(2026, 9, 29)

    def test_corpo_vazio_e_nao_publicado(self) -> None:
        got = fetch_anbima_ettj(
            client_for(httpx.MockTransport(lambda r: httpx.Response(200, content=b""))),
            date(2026, 10, 1),
        )
        with pytest.raises(NotPublishedError):
            parse_anbima_ettj(got.content)


class TestBcbIbge:
    def test_sgs(self) -> None:
        body = (F2 / "bcb_sgs_12_cdi_diario.json").read_bytes()
        seen: dict[str, str] = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            return httpx.Response(200, content=body)

        got = fetch_sgs(
            client_for(httpx.MockTransport(handler)),
            12,
            date(2026, 1, 1),
            date(2026, 9, 4),
            as_of=date(2026, 9, 4),
        )
        assert "bcdata.sgs.12/dados" in seen["url"]
        assert "dataInicial=01%2F01%2F2026" in seen["url"]
        assert len(parse_sgs(got.content)) == 170

    def test_ibge(self) -> None:
        body = (F2 / "ibge_calendario_2026.json").read_bytes()
        got = fetch_ibge_calendar(
            client_for(httpx.MockTransport(lambda r: httpx.Response(200, content=body))),
            date(2026, 1, 1),
            date(2026, 12, 31),
            as_of=date(2026, 9, 29),
        )
        assert len(parse_ipca_releases(got.content)) == 12

    def test_ibge_paginado_falha(self) -> None:
        payload = json.dumps({"count": 3, "totalPages": 2, "items": [{"titulo": "x"}]})
        with pytest.raises(ValueError, match="paginada"):
            parse_ipca_releases(payload)


def _store(args: tuple[str, bytes, str]) -> str:
    root, content, name = args
    got = store_raw(
        date(2026, 9, 29),
        name,
        content,
        source="t",
        url="https://x.test",
        requested_date=date(2026, 9, 29),
        retrieved_at=FIXED_NOW,
        root=Path(root),
    )
    return got.path.name


class TestRaw:
    KW = {  # noqa: RUF012
        "source": "anbima_ettj",
        "url": "https://x.test",
        "requested_date": date(2026, 9, 29),
        "retrieved_at": FIXED_NOW,
        "source_date": date(2026, 9, 29),
    }

    def test_grava_com_manifesto_e_nunca_sobrescreve(self, tmp_path: Path) -> None:
        kw = {**self.KW, "root": tmp_path}
        a = store_raw(date(2026, 9, 29), "anbima.csv", b"v1", **kw)  # type: ignore[arg-type]
        b = store_raw(date(2026, 9, 29), "anbima.csv", b"v1", **kw)  # type: ignore[arg-type]
        c = store_raw(date(2026, 9, 29), "anbima.csv", b"v2", **kw)  # type: ignore[arg-type]
        d = store_raw(date(2026, 9, 29), "anbima.csv", b"v1", **kw)  # type: ignore[arg-type]
        folder = day_dir(date(2026, 9, 29), tmp_path)
        assert folder == tmp_path / "2026" / "09" / "2026-09-29"
        assert (a.new, b.new, c.new, d.new) == (True, False, True, False)
        assert (a.path.name, c.path.name, d.path.name) == (
            "anbima.csv",
            "anbima.v2.csv",
            "anbima.csv",
        )
        assert a.path.read_bytes() == b"v1"  # o original não muda
        manifest = json.loads((folder / "manifest.json").read_text())
        # Toda coleta é registrada, inclusive A → B → A.
        assert [(m["file"], m["duplicate"]) for m in manifest] == [
            ("anbima.csv", False),
            ("anbima.csv", True),
            ("anbima.v2.csv", False),
            ("anbima.csv", True),
        ]
        assert manifest[0]["source_date"] == "2026-09-29"
        assert manifest[0]["retrieved_at"].startswith("2026-09-29T21:00")

    def test_processos_simultaneos(self, tmp_path: Path) -> None:
        """Revisão da F3: dois processos no mesmo dia não podem perder bruto nem entrada."""
        jobs = [(str(tmp_path), f"conteudo {i}".encode(), "x.csv") for i in range(8)]
        with multiprocessing.get_context("spawn").Pool(4) as pool:
            names = pool.map(_store, jobs)
        assert len(set(names)) == 8
        folder = day_dir(date(2026, 9, 29), tmp_path)
        manifest = json.loads((folder / "manifest.json").read_text())
        assert len(manifest) == 8
        on_disk = {p.name: p.read_bytes() for p in folder.glob("x*.csv")}
        assert sorted(on_disk.values()) == sorted(c for _, c, _ in jobs)
        for entry in manifest:
            assert hashlib.sha256(on_disk[entry["file"]]).hexdigest() == entry["sha256"]


class TestHttpErros:
    def test_retry_after_e_408(self) -> None:
        calls: list[int] = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(1)
            if len(calls) == 1:
                return httpx.Response(429, headers={"Retry-After": "12"})
            if len(calls) == 2:
                return httpx.Response(408)
            return httpx.Response(200, content=b"ok")

        waits: list[float] = []
        request_with_retry(
            client_for(httpx.MockTransport(handler)), "GET", "https://x.test", source="t",
            sleep=waits.append,
        )  # fmt: skip
        assert waits == [12.0, 4.0]

    def test_erro_nao_transitorio_vira_fetcherror(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.TooManyRedirects("loop", request=request)

        waits: list[float] = []
        with pytest.raises(FetchError, match="TooManyRedirects"):
            request_with_retry(
                client_for(httpx.MockTransport(handler)), "GET", "https://x.test", source="t",
                sleep=waits.append,
            )  # fmt: skip
        assert waits == []


def test_log_json(caplog: pytest.LogCaptureFixture) -> None:
    formatter = JsonFormatter()
    record = logging.makeLogRecord(
        {"name": "curvas.x", "levelname": "INFO", "msg": "fetch ok", "source": "s", "status": 200}
    )
    payload = json.loads(formatter.format(record))
    assert payload["event"] == "fetch ok"
    assert payload["source"] == "s"
    assert payload["status"] == 200
    assert "ts" in payload
