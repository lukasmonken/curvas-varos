"""Pipeline ponta a ponta sem rede (Parte 1, seções 10.8, 11, 12 e 16)."""

import csv
import dataclasses
import json
import math
import zipfile
from collections.abc import Callable
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

import curvas.run as run_module
from conftest import ROOT
from curvas.config import DEFAULT, AlertConfig
from curvas.engine.legacy import compute_legacy
from curvas.fetch.raw import compact_old_months, day_dir, read_raw, store_raw
from curvas.models import RunOutput
from curvas.normalize.anbima_ettj import parse_anbima_ettj
from curvas.normalize.legacy_inputs import build_legacy_inputs
from curvas.run import BlockingError, Paths, main, run, write_output
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
    return Paths(raw_root=tmp / "raw", out_root=tmp / name, manual_cds=ROOT / "data/manual/cds.csv")


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


def test_site_provisorio(tmp_path: Path) -> None:
    go(tmp_path, T0)
    index = build(tmp_path / "site", tmp_path / "out")
    text = index.read_text()
    assert "Data-base: 2026-09-29" in text
    assert text.count("<tr><th>20") == 11
    assert (tmp_path / "site" / "latest.json").read_text() == (
        tmp_path / "out" / "latest.json"
    ).read_text()
