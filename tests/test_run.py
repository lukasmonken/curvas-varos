"""Pipeline ponta a ponta sem rede (Parte 1, seções 10.8, 11, 12 e 16)."""

import csv
import dataclasses
import json
import math
import subprocess
import zipfile
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

import curvas.run as run_module
from conftest import ROOT
from curvas.calendar import load_anbima_calendar
from curvas.cds_add import append_cds
from curvas.config import DEFAULT, AlertConfig
from curvas.engine.legacy import compute_legacy
from curvas.fetch.http import FetchError
from curvas.fetch.raw import compact_old_months, day_dir, read_raw, store_raw
from curvas.fetch.sources import fetch_sgs
from curvas.models import RunOutput
from curvas.normalize.anbima_ettj import parse_anbima_ettj
from curvas.normalize.legacy_inputs import build_legacy_inputs
from curvas.output.json_out import hide_cds_change
from curvas.run import BlockingError, Paths, catch_up, main, pending_dates, run, write_output
from curvas.schema import SCHEMA_PATH, schema_text
from curvas.site.build import build

FIX = ROOT / "tests" / "fixtures"
SGS_FILES = {
    "12": FIX / "f2" / "bcb_sgs_12_cdi_diario_2026-09-29.json",
    "433": FIX / "f2" / "bcb_sgs_433_ipca_mensal.json",
    "4390": FIX / "f2" / "bcb_sgs_4390_selic_mensal.json",
    "7478": FIX / "f2" / "bcb_sgs_7478_ipca15_mensal.json",
}
IBGE = FIX / "f2" / "ibge_calendario_2026.json"
# Cópia congelada do CDS manual: o arquivo de produção muda todo dia (data/manual/cds.csv).
CDS_FIXTURE = FIX / "f4" / "cds_manual.csv"
NO_START = dataclasses.replace(DEFAULT, pipeline_start=None)
COMMIT = "0" * 40


def handler(
    overrides: dict[str, bytes] | None = None,
) -> Callable[[httpx.Request], httpx.Response]:
    over = overrides or {}

    def serve(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "anbima" in url:
            day = parse_qs(request.content.decode())["Dt_Ref"][0]
            d, m, y = day.split("/")
            if f"anbima:{y}-{m}-{d}" in over:
                return httpx.Response(200, content=over[f"anbima:{y}-{m}-{d}"])
            path = FIX / "f3" / "anbima" / f"cz_{y}-{m}-{d}.csv"
            return httpx.Response(200, content=path.read_bytes() if path.exists() else b"")
        if "bcdata.sgs." in url:
            code = url.split("bcdata.sgs.")[1].split("/", maxsplit=1)[0]
            if f"sgs:{code}" in over:
                return httpx.Response(200, content=over[f"sgs:{code}"])
            return httpx.Response(200, content=SGS_FILES[code].read_bytes())
        if "ibge" in url:
            return httpx.Response(200, content=IBGE.read_bytes())
        return httpx.Response(404)

    return serve


def client(overrides: dict[str, bytes] | None = None) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler(overrides)))


def paths(tmp: Path, name: str = "out") -> Paths:
    return Paths(raw_root=tmp / "raw", out_root=tmp / name, manual_cds=CDS_FIXTURE)


CDS_DIA = [46.0, 55.0, 68.0, 88.0, 110.0, 131.0, 172.0, 214.0, 246.0]
LATER = datetime(2026, 10, 1, 23, 0, tzinfo=UTC)  # depois de todo preenchimento do fixture


def cds_copy(tmp: Path) -> Paths:
    """Paths com uma cópia gravável do CDS manual congelado."""
    target = tmp / "cds.csv"
    target.write_text(CDS_FIXTURE.read_text(encoding="utf-8"), encoding="utf-8")
    return dataclasses.replace(paths(tmp), manual_cds=target)


def go(tmp: Path, as_of: date, **kw: Any) -> RunOutput:
    p = kw.pop("p", None) or paths(tmp)
    result = run(
        as_of=as_of, client=kw.pop("client", None) or client(), paths=p, git_commit=COMMIT, **kw
    )
    assert result.output is not None
    return result.output


T0 = date(2026, 9, 29)


class TestPontaAPonta:
    def test_bate_com_a_tabela_oficial_da_f2(self, tmp_path: Path) -> None:
        """O CORRIGIDO de 29/09 é o mesmo número da tabela da F2 (mesmas curvas e realizado)."""
        out = go(tmp_path, T0)
        rows = list(csv.DictReader((ROOT / "docs/f2_legado_x_corrigido.csv").open()))
        f2 = {(r["curva"], int(r["ano"])): float(r["corrigido"]) for r in rows}
        for row in out.annual.corrected:
            assert row.di == pytest.approx(f2[("di", row.year)], abs=1e-12)
            assert row.inflation == pytest.approx(f2[("inflation", row.year)], abs=1e-12)
            assert row.cds == pytest.approx(f2[("cds", row.year)], abs=1e-12)
            assert row.real == pytest.approx(f2[("real", row.year)], abs=1e-12)
            assert row.discount == pytest.approx((1 + row.di) * (1 + row.cds) - 1)  # type: ignore[operator]

    def test_legado_diario(self, tmp_path: Path) -> None:
        out = go(tmp_path, T0)
        li = out.inputs.legacy
        assert (li.month, li.quarter, li.ytg_days, li.cds_ytg_days) == (8, 3, 84, 84)
        assert li.di_curve_pct[2] == 13.6052  # 378 alinhado: sem o erro de colagem (Q14)
        assert li.inflation_curve_pct[0] == li.inflation_curve_pct[1]  # 126 := 252 (Q15)
        assert [m.month for m in out.realized.selic_monthly_legacy] == list(range(1, 9))
        assert all(r.di is not None for r in out.annual.legacy)
        # DI 2026 do LEGADO = DI!E4 anualizado com expoente 4/(5−3) = 2.
        ettj = parse_anbima_ettj((FIX / "f3/anbima/cz_2026-09-29.csv").read_bytes())
        ipca = {
            (2026, m): v for m, v in enumerate([0.33, 0.70, 0.88, 0.67, 0.58, 0.16, 0.07, -0.32], 1)
        }
        selic = {
            (2026, m): v for m, v in enumerate([1.16, 1.0, 1.21, 1.09, 1.07, 1.12, 1.22, 1.09], 1)
        }
        daily = build_legacy_inputs(
            as_of=T0,
            ettj=ettj,
            cds_bps=li.cds_bps,
            last_ipca=(2026, 8),
            ipca_monthly_pct=ipca,
            selic_monthly_pct=selic,
        )
        assert out.annual.legacy[0].di == compute_legacy(daily.inputs).dashboard.di[0]

    def test_estrutura_e_fontes(self, tmp_path: Path) -> None:
        out = go(tmp_path, T0)
        assert out.metadata.as_of_date == T0
        assert out.metadata.git_commit == COMMIT
        names = {s.source for s in out.sources}
        assert names == {
            "anbima_ettj",
            "bcb_sgs_12",
            "bcb_sgs_433",
            "bcb_sgs_4390",
            "bcb_sgs_7478",
            "ibge_calendario",
            "cds_manual",
        }
        assert not any(s.stale for s in out.sources)
        assert out.alerts == []
        assert [c.name for c in out.curves] == ["di", "inflation", "cds"]
        di = out.curves[0]
        assert di.corrected_vertices[0].days == 21
        assert all(p.factor > 0 for c in out.curves for p in c.corrected_sample)
        for v in di.corrected_vertices:  # 10.3 na saída publicada
            sample = {p.days: p for p in di.corrected_sample}
            if v.days in sample:
                assert sample[v.days].rate == pytest.approx(v.rate, abs=1e-12)
        assert out.realized.cdi.last_observation == date(2026, 9, 28)
        assert out.realized.ipca_monthly[-1].month == 8
        assert out.comparison[0].di_bps is not None

    def test_reexecucao_offline_identica(self, tmp_path: Path) -> None:
        """16.7: mesmos t0, brutos e configuração → exatamente o mesmo resultado."""
        go(tmp_path, T0)
        first = (tmp_path / "out" / "curves" / "2026-09-29.json").read_bytes()
        result = run(as_of=T0, offline=True, paths=paths(tmp_path, "out2"), git_commit=COMMIT)
        assert result.path is not None
        assert result.path.read_bytes() == first
        assert (tmp_path / "out2" / "latest.json").read_bytes() == first

    def test_brutos_e_manifesto(self, tmp_path: Path) -> None:
        go(tmp_path, T0)
        folder = day_dir(T0, tmp_path / "raw")
        manifest = json.loads((folder / "manifest.json").read_text())
        assert {m["source"] for m in manifest} >= {"anbima_ettj", "bcb_sgs_12", "ibge_calendario"}
        anbima = next(m for m in manifest if m["source"] == "anbima_ettj")
        assert anbima["requested_date"] == anbima["source_date"] == "2026-09-29"


class TestFallback:
    def test_anbima_nao_publicada_usa_o_dia_anterior(self, tmp_path: Path) -> None:
        go(tmp_path, T0)  # grava os brutos de 29/09
        out = go(tmp_path, date(2026, 9, 30), client=client({"anbima:2026-09-30": b""}))
        anbima = next(s for s in out.sources if s.source == "anbima_ettj")
        assert anbima.stale
        assert anbima.source_date == T0
        assert anbima.fallback_reason is not None
        assert "29/09/2026" in anbima.fallback_reason
        assert any(a.code == "fonte_defasada" and a.source == "anbima_ettj" for a in out.alerts)
        assert any(a.code == "cds_manual" for a in out.alerts)  # CDS de 29/09 para t0 = 30/09

    def test_sem_nenhum_dado_valido_bloqueia(self, tmp_path: Path) -> None:
        with pytest.raises(BlockingError, match="anbima_ettj"):
            go(tmp_path, T0, client=client({"anbima:2026-09-29": b""}))

    def test_resposta_invalida_nao_vira_dado(self, tmp_path: Path) -> None:
        with pytest.raises(BlockingError, match="bcb_sgs_12"):
            go(tmp_path, T0, client=client({"sgs:12": b'{"erro": "x"}'}))

    def test_cdi_atrasado_e_preenchido_com_alerta(self, tmp_path: Path) -> None:
        rows = json.loads(SGS_FILES["12"].read_text())[:-2]  # sem 28 e 29/09
        out = go(tmp_path, T0, client=client({"sgs:12": json.dumps(rows).encode()}))
        assert any(a.code == "cdi_preenchido" for a in out.alerts)

    def test_ipca_divulgado_sem_valor_no_sgs(self, tmp_path: Path) -> None:
        rows = [r for r in json.loads(SGS_FILES["433"].read_text()) if r["data"] != "01/08/2026"]
        out = go(tmp_path, T0, client=client({"sgs:433": json.dumps(rows).encode()}))
        assert any(a.code == "ipca_sem_valor_no_sgs" for a in out.alerts)
        assert out.realized.ipca_monthly[-1].month == 7
        assert out.inputs.legacy.month == 7


class TestBloqueiosEAlertas:
    def test_dia_nao_util(self, tmp_path: Path) -> None:
        result = run(today=date(2026, 10, 3), paths=paths(tmp_path), client=client())
        assert result.status == "skipped"
        assert "não é dia útil" in result.reason
        with pytest.raises(BlockingError, match="dia útil"):
            run(as_of=date(2026, 10, 3), paths=paths(tmp_path), client=client())

    def test_nan_bloqueia_a_publicacao(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:

        real = run_module.compute_corrected

        def broken(inputs: Any) -> Any:
            res = real(inputs)
            return dataclasses.replace(res, di=(math.nan, *res.di[1:]))

        monkeypatch.setattr(run_module, "compute_corrected", broken)
        with pytest.raises(BlockingError, match="schema"):
            go(tmp_path, T0)
        assert not (tmp_path / "out" / "latest.json").exists()

    def test_variacao_diaria(self, tmp_path: Path) -> None:
        go(tmp_path, T0)
        cfg = dataclasses.replace(DEFAULT, alerts=AlertConfig(max_daily_change_bps=0.5))
        out = go(tmp_path, date(2026, 9, 30), cfg=cfg)
        changes = [a for a in out.alerts if a.code == "variacao_diaria"]
        assert changes
        assert "desde 2026-09-29" in changes[0].message
        # Q17: o site e os downloads reconhecem esta mensagem e tiram o valor do CDS/desconto.
        assert any(a.message.split()[1] == "discount" for a in changes)
        for a in changes:
            hidden = hide_cds_change(a).message
            if a.message.split()[1] in ("cds", "discount"):
                assert hidden.endswith(": variação acima do limite"), a.message
            else:
                assert hidden == a.message

    def test_latest_nao_regride(self, tmp_path: Path) -> None:
        go(tmp_path, date(2026, 9, 30))
        go(tmp_path, T0)
        latest = json.loads((tmp_path / "out" / "latest.json").read_text())
        assert latest["metadata"]["as_of_date"] == "2026-09-30"

    def test_cli_e_saida_do_github(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        gh = tmp_path / "gh_output"
        monkeypatch.setenv("GITHUB_OUTPUT", str(gh))
        assert main(["--today", "2026-10-03", "--offline"]) == 0
        assert "published=false" in gh.read_text()


def test_virada_do_ano_no_legado() -> None:
    """Q6: último IPCA do ano anterior → m = 0, ano corrente indisponível, seguintes normais."""
    ettj = parse_anbima_ettj((FIX / "f3/anbima/cz_2026-09-29.csv").read_bytes())
    daily = build_legacy_inputs(
        as_of=date(2027, 1, 15),
        ettj=ettj,
        cds_bps=[50.0] * 9,
        last_ipca=(2026, 12),
        ipca_monthly_pct={},
        selic_monthly_pct={},
    )
    assert daily.turn_of_year
    assert daily.month == 0
    assert daily.inputs.cds_ytg_days == 252
    dash = compute_legacy(daily.inputs).dashboard
    assert all(v is not None for v in dash.di[1:])


def test_retencao_compacta_e_le_do_zip(tmp_path: Path) -> None:
    root = tmp_path / "raw"
    for day in (date(2026, 5, 4), date(2026, 5, 5), date(2026, 9, 1)):
        store_raw(
            day,
            "x.csv",
            f"{day}".encode(),
            source="s",
            url="u",
            requested_date=day,
            retrieved_at=datetime(2026, 9, 1),
            root=root,
        )
    created = compact_old_months(date(2026, 9, 1), root)
    assert created == [root / "2026" / "05.zip"]
    assert not (root / "2026" / "05").exists()
    assert (root / "2026" / "09").exists()  # dentro dos 90 dias
    with zipfile.ZipFile(created[0]) as zf:
        assert "2026-05-04/x.csv" in zf.namelist()
    got = read_raw(date(2026, 5, 4), "s", root)
    assert got is not None
    assert got.content == b"2026-05-04"
    assert compact_old_months(date(2026, 9, 1), root) == []  # nunca sobrescreve


def test_schema_publicado_atualizado() -> None:
    assert SCHEMA_PATH.read_text(encoding="utf-8") == schema_text()


def test_write_output_grava_por_data(tmp_path: Path) -> None:
    out = go(tmp_path, T0)
    p = paths(tmp_path, "other")
    target = write_output(out, p)
    assert target.name == "2026-09-29.json"
    assert RunOutput.model_validate_json(target.read_text()) == out


def test_site_a_partir_da_saida(tmp_path: Path) -> None:
    go(tmp_path, T0)
    index = build(tmp_path / "site", tmp_path / "out", show_cds=True, env={})
    assert "29/09/2026" in index.read_text(encoding="utf-8")
    assert (tmp_path / "site" / "latest.json").read_bytes() == (
        tmp_path / "out" / "latest.json"
    ).read_bytes()
    assert (tmp_path / "site" / "downloads" / "curvas-2026-09-29.xlsx").is_file()


class TestRecuperacao:
    def test_dias_pendentes(self, tmp_path: Path) -> None:
        cal = load_anbima_calendar()
        p = paths(tmp_path)
        # Sem saída gravada: a janela inteira de 5 dias úteis (07/09 é feriado).
        assert pending_dates(date(2026, 9, 11), p, cal, None) == [
            date(2026, 9, 4),
            date(2026, 9, 8),
            date(2026, 9, 9),
            date(2026, 9, 10),
            date(2026, 9, 11),
        ]
        go(tmp_path, T0)
        window = [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)]
        assert pending_dates(date(2026, 10, 3), p, cal, T0) == window
        # Sem data de início, o 28/09 (sem saída) também fica pendente: buracos não somem.
        assert pending_dates(date(2026, 10, 3), p, cal, None) == [date(2026, 9, 28), *window]

    def test_dia_sem_ettj_fica_pendente_e_depois_sai(self, tmp_path: Path) -> None:
        go(tmp_path, T0)
        first = catch_up(
            today=date(2026, 9, 30),
            client=client({"anbima:2026-09-30": b""}),
            paths=paths(tmp_path),
            git_commit=COMMIT,
        )
        assert first.published == []
        assert [d for d, _ in first.not_ready] == [date(2026, 9, 30)]
        assert not (tmp_path / "out" / "curves" / "2026-09-30.json").exists()
        second = catch_up(
            today=date(2026, 9, 30), client=client(), paths=paths(tmp_path), git_commit=COMMIT
        )
        assert [r.as_of for r in second.published] == [date(2026, 9, 30)]
        third = catch_up(
            today=date(2026, 9, 30), client=client(), paths=paths(tmp_path), git_commit=COMMIT
        )
        assert (third.published, third.not_ready, third.blocked) == ([], [], [])

    def test_dia_bloqueado_nao_impede_os_outros(self, tmp_path: Path) -> None:
        res = catch_up(
            today=date(2026, 9, 29),
            client=client(),
            paths=paths(tmp_path),
            git_commit=COMMIT,
            cfg=NO_START,
        )
        # Sem CDS manual antes de 29/09: 23 a 28/09 bloqueiam; 29/09 sai.
        assert [r.as_of for r in res.published] == [T0]
        assert {d for d, _ in res.blocked} == {
            date(2026, 9, 23),
            date(2026, 9, 24),
            date(2026, 9, 25),
            date(2026, 9, 28),
        }
        assert all("CDS manual" in why for _, why in res.blocked)

    def test_cds_lancado_depois_refaz_o_dia(self, tmp_path: Path) -> None:
        """Saída com CDS defasado; o CDS do dia entra no arquivo depois (cds.yml): refazer."""
        p = cds_copy(tmp_path)
        cal = load_anbima_calendar()
        day = date(2026, 9, 30)
        go(tmp_path, T0, p=p)
        before = go(tmp_path, day, p=p)
        assert next(s for s in before.sources if s.source == "cds_manual").stale
        assert pending_dates(day, p, cal, T0) == []  # arquivo sem novidade: nada a refazer
        append_cds(p.manual_cds, day, CDS_DIA, filled_by="fulano", filled_at=LATER)
        assert pending_dates(day, p, cal, T0) == [day]  # o 29/09 continua como estava
        res = catch_up(today=day, client=client(), paths=p, git_commit=COMMIT)
        assert [r.as_of for r in res.published] == [day]
        after = res.published[0].output
        assert after is not None
        cds = next(s for s in after.sources if s.source == "cds_manual")
        assert not cds.stale
        assert cds.source_date == day
        assert after.inputs.legacy.cds_bps == CDS_DIA
        assert not any(a.code == "cds_manual" for a in after.alerts)
        assert pending_dates(day, p, cal, T0) == []

    def test_cds_corrigido_depois_refaz_o_dia(self, tmp_path: Path) -> None:
        """Correção (mesmo dia, ``preenchido_em`` posterior) também refaz a saída."""
        p = cds_copy(tmp_path)
        cal = load_anbima_calendar()
        first = go(tmp_path, T0, p=p)
        assert pending_dates(T0, p, cal, T0) == []
        fixed = [*first.inputs.legacy.cds_bps]
        fixed[5] = 99.5
        append_cds(p.manual_cds, T0, fixed, filled_by="beltrano", filled_at=LATER)
        assert pending_dates(T0, p, cal, T0) == [T0]
        res = catch_up(today=T0, client=client(), paths=p, git_commit=COMMIT)
        assert [r.as_of for r in res.published] == [T0]
        after = res.published[0].output
        assert after is not None
        assert after.inputs.legacy.cds_bps == fixed
        assert pending_dates(T0, p, cal, T0) == []

    def test_cds_de_outro_dia_nao_refaz(self, tmp_path: Path) -> None:
        p = cds_copy(tmp_path)
        cal = load_anbima_calendar()
        go(tmp_path, T0, p=p)
        go(tmp_path, date(2026, 9, 30), p=p)  # CDS defasado (de 29/09)
        append_cds(p.manual_cds, date(2026, 10, 1), CDS_DIA, filled_by="x", filled_at=LATER)
        assert pending_dates(date(2026, 10, 1), p, cal, T0) == [date(2026, 10, 1)]

    def test_cds_ilegivel_nao_derruba_a_recuperacao(self, tmp_path: Path) -> None:
        go(tmp_path, T0)
        p = dataclasses.replace(paths(tmp_path), manual_cds=tmp_path / "nao_existe.csv")
        assert pending_dates(T0, p, load_anbima_calendar(), T0) == []


def test_bcb_html_com_status_200_e_repetido() -> None:
    calls: list[int] = []
    body = SGS_FILES["12"].read_bytes()

    def serve(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(200, content=b"<html>A sua requisicao foi rejeitada</html>")
        return httpx.Response(200, content=body)

    waits: list[float] = []
    got = fetch_sgs(
        httpx.Client(transport=httpx.MockTransport(serve)),
        12,
        date(2026, 1, 1),
        T0,
        as_of=T0,
        sleep=waits.append,
    )
    assert got.content == body
    assert waits == [2.0]
    always_html = httpx.Client(
        transport=httpx.MockTransport(lambda r: httpx.Response(200, content=b"<html>x</html>"))
    )
    with pytest.raises(FetchError, match="conteúdo inesperado"):
        fetch_sgs(always_html, 12, date(2026, 1, 1), T0, as_of=T0, sleep=lambda _s: None)


class TestRevisaoF4:
    """Achados da revisão adversarial da F4."""

    def test_falha_da_anbima_em_dia_passado_bloqueia_com_a_causa(self, tmp_path: Path) -> None:
        def broken(request: httpx.Request) -> httpx.Response:
            if "anbima" in str(request.url):
                return httpx.Response(503)
            return handler()(request)

        go(tmp_path, T0)  # 29/09 gravado: há bruto antigo para o fallback
        cfg = dataclasses.replace(DEFAULT, http=dataclasses.replace(DEFAULT.http, max_attempts=1))
        res = catch_up(
            today=date(2026, 9, 30),
            client=httpx.Client(transport=httpx.MockTransport(broken)),
            paths=paths(tmp_path),
            cfg=cfg,
            git_commit=COMMIT,
        )
        assert res.not_ready == []
        assert [d for d, _ in res.blocked] == [date(2026, 9, 30)]
        assert "HTTP 503" in res.blocked[0][1]

    def test_dia_passado_vazio_tambem_e_erro(self, tmp_path: Path) -> None:
        go(tmp_path, T0)
        res = catch_up(
            today=date(2026, 10, 1),
            client=client({"anbima:2026-09-30": b"", "anbima:2026-10-01": b""}),
            paths=paths(tmp_path),
            git_commit=COMMIT,
        )
        assert [d for d, _ in res.blocked] == [date(2026, 9, 30)]
        assert [d for d, _ in res.not_ready] == [date(2026, 10, 1)]  # hoje: ainda não saiu

    def test_saida_com_ettj_defasada_e_refeita(self, tmp_path: Path) -> None:
        go(tmp_path, T0)
        stale = go(tmp_path, date(2026, 9, 30), client=client({"anbima:2026-09-30": b""}))
        assert next(s for s in stale.sources if s.source == "anbima_ettj").stale
        cal = load_anbima_calendar()
        assert date(2026, 9, 30) in pending_dates(date(2026, 9, 30), paths(tmp_path), cal, T0)
        res = catch_up(
            today=date(2026, 9, 30), client=client(), paths=paths(tmp_path), git_commit=COMMIT
        )
        assert [r.as_of for r in res.published] == [date(2026, 9, 30)]
        fresh = res.published[0].output
        assert fresh is not None
        assert not next(s for s in fresh.sources if s.source == "anbima_ettj").stale

    def test_data_futura_bloqueia(self, tmp_path: Path) -> None:
        with pytest.raises(BlockingError, match="futuro"):
            run(
                as_of=date(2026, 10, 2),
                today=date(2026, 10, 1),
                paths=paths(tmp_path),
                client=client(),
            )

    def test_agenda_do_ibge_cobre_o_ano_seguinte(self, tmp_path: Path) -> None:
        seen: list[str] = []

        def spy(request: httpx.Request) -> httpx.Response:
            seen.append(str(request.url))
            return handler()(request)

        go(tmp_path, T0, client=httpx.Client(transport=httpx.MockTransport(spy)))
        assert "ate=12-31-2027" in next(u for u in seen if "ibge" in u)

    def test_sgs_fora_da_faixa_nao_entra(self, tmp_path: Path) -> None:
        rows = json.loads(SGS_FILES["12"].read_text())
        rows[100]["valor"] = "13.65"  # taxa anual no lugar da diária
        with pytest.raises(BlockingError, match="fora da faixa"):
            go(tmp_path, T0, client=client({"sgs:12": json.dumps(rows).encode()}))

    def test_serie_mensal_fora_do_dia_1_bloqueia_so_o_dia(self, tmp_path: Path) -> None:
        rows = json.loads(SGS_FILES["433"].read_text())
        rows[-1]["data"] = "15/08/2026"
        with pytest.raises(BlockingError, match="fora do dia 1"):
            go(tmp_path, T0, client=client({"sgs:433": json.dumps(rows).encode()}))

    def test_datas_das_fontes(self, tmp_path: Path) -> None:
        out = go(tmp_path, T0)
        by = {s.source: s for s in out.sources}
        assert by["bcb_sgs_433"].publication_date == date(2026, 9, 11)  # IPCA de agosto
        for s in out.sources:
            if s.source_date is not None:
                assert s.source_date <= T0  # o 4390 traz outubro parcial no bruto

    def test_cdi_preenchido_fica_defasado(self, tmp_path: Path) -> None:
        rows = json.loads(SGS_FILES["12"].read_text())[:-2]  # sem 28 e 29/09
        out = go(tmp_path, T0, client=client({"sgs:12": json.dumps(rows).encode()}))
        cdi = next(s for s in out.sources if s.source == "bcb_sgs_12")
        assert cdi.stale
        assert cdi.fallback_reason is not None
        assert out.realized.cdi.last_observation == date(2026, 9, 25)

    def test_zip_e_pasta_solta_juntos(self, tmp_path: Path) -> None:
        root = tmp_path / "raw"
        day = date(2026, 5, 4)
        kw: dict[str, Any] = {"url": "u", "requested_date": day, "root": root}
        store_raw(
            day, "a.csv", b"anbima", source="anbima_ettj", retrieved_at=datetime(2026, 5, 4), **kw
        )
        compact_old_months(date(2026, 9, 1), root)
        store_raw(
            day, "b.json", b"sgs", source="bcb_sgs_12", retrieved_at=datetime(2026, 9, 2), **kw
        )
        anbima = read_raw(day, "anbima_ettj", root)
        sgs = read_raw(day, "bcb_sgs_12", root)
        assert anbima is not None
        assert anbima.content == b"anbima"
        assert sgs is not None
        assert sgs.content == b"sgs"


class TestRevisaoF5:
    """Achados da revisão adversarial da F5."""

    def test_ipca_reprocessado_depois_da_divulgacao_seguinte(self, tmp_path: Path) -> None:
        """Bruto do SGS 433 já com setembro (dia refeito depois de ~09/10): a data do dado
        é a do IPCA usado (agosto), o mesmo que a data de divulgação descreve."""
        rows = [*json.loads(SGS_FILES["433"].read_text()), {"data": "01/09/2026", "valor": "0.48"}]
        out = go(tmp_path, T0, client=client({"sgs:433": json.dumps(rows).encode()}))
        ipca = next(s for s in out.sources if s.source == "bcb_sgs_433")
        assert out.realized.ipca_monthly[-1].month == 8
        assert ipca.source_date == date(2026, 8, 1)  # antes: 01/09, a última do bruto
        assert ipca.publication_date == date(2026, 9, 11)

    def test_commit_do_codigo_em_uso(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """HEAD do git (o checkout do daily é a ponta do branch), com -dirty se há
        alteração fora de data/; o GITHUB_SHA do disparo só sem git."""
        status = ""

        def fake(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
            if cmd[1] == "rev-parse":
                return subprocess.CompletedProcess(cmd, 0, stdout="abc123\n")
            assert ":(exclude)data" in cmd
            return subprocess.CompletedProcess(cmd, 0, stdout=status)

        monkeypatch.setenv("GITHUB_SHA", "sha_do_disparo")
        monkeypatch.setattr(run_module.subprocess, "run", fake)
        assert run_module._git_commit() == "abc123"
        status = " M src/curvas/run.py\n"
        assert run_module._git_commit() == "abc123-dirty"

        def broken(cmd: list[str], **_kw: Any) -> Any:
            raise OSError("sem git")

        monkeypatch.setattr(run_module.subprocess, "run", broken)
        assert run_module._git_commit() == "sha_do_disparo"
        monkeypatch.delenv("GITHUB_SHA")
        assert run_module._git_commit() is None

    def test_cds_fora_de_utf8_bloqueia_com_mensagem(self, tmp_path: Path) -> None:
        """cds.csv salvo em cp1252 (ex.: pelo Excel): BLOQUEADO com a causa, sem traceback."""
        go(tmp_path, T0)
        bad = tmp_path / "cds_cp1252.csv"
        text = CDS_FIXTURE.read_text(encoding="utf-8")
        assert text.encode("cp1252") != text.encode("utf-8")  # há acentos (cabeçalho e fonte)
        bad.write_bytes(text.encode("cp1252"))
        p = dataclasses.replace(paths(tmp_path), manual_cds=bad)
        assert pending_dates(T0, p, load_anbima_calendar(), T0) == []
        with pytest.raises(BlockingError, match=r"CDS manual: .*UTF-8"):
            run(as_of=T0, offline=True, paths=p, git_commit=COMMIT)
