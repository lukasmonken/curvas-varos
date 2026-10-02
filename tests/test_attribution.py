"""Cascata LEGADO → CORRIGIDO da tabela da F2.

Duas configurações:

- ``report()``: t0 = 04/09/2026 com as curvas da planilha (1ª versão da F2). É a
  que tem o oráculo independente (``referencia_independente/``) e os números fixados.
- ``report_oficial()``: t0 = 29/09/2026 com as curvas da ANBIMA desse dia e a etapa
  do erro de colagem (Q8, Q14, Q15). É a tabela publicada em ``docs/``.
"""

import csv
import io
import json
from dataclasses import replace
from datetime import date
from functools import cache

import pytest

from conftest import LEGACY, ROOT, sha256
from curvas.calendar import load_anbima_calendar
from curvas.engine.attribution import STAGE_NAMES, contributions, legacy_to_corrected
from curvas.engine.corrected import compute_corrected
from curvas.engine.curves import VertexCurve
from curvas.engine.legacy import compute_legacy
from curvas.normalize.anbima_ettj import legacy_curves_pct, parse_anbima_ettj
from curvas.output.comparacao import (
    F2Report,
    RealizedFiles,
    build_report,
    legacy_inputs_from_json,
    render_csv,
    render_markdown,
)

F2 = ROOT / "tests" / "fixtures" / "f2"
ANBIMA_29 = ROOT / "tests" / "fixtures" / "f3" / "anbima" / "cz_2026-09-29.csv"
T0 = date(2026, 9, 4)
T0_OFICIAL = date(2026, 9, 29)


@cache
def report() -> F2Report:
    files = RealizedFiles.in_dir(F2)
    return build_report(LEGACY / "inputs_planilha.json", files, load_anbima_calendar(), T0)


@cache
def report_oficial() -> F2Report:
    files = RealizedFiles.in_dir(F2, cdi_name="bcb_sgs_12_cdi_diario_2026-09-29.json")
    return build_report(
        LEGACY / "inputs_planilha.json",
        files,
        load_anbima_calendar(),
        T0_OFICIAL,
        anbima_csv=ANBIMA_29,
    )


FIELDS = ("di", "inflation", "cds", "real")


def test_inputs_do_corrigido() -> None:
    ci = report().corrected_inputs
    assert ci.year_end_business_days[0] == 80
    assert ci.ipca_last_month == 7  # IPCA de agosto saiu em 11/09/2026, depois de t0
    assert ci.inflation_gap_business_days == 104  # 03/08 a 31/12
    assert ci.cdi_realized_factor == pytest.approx(1.094935, abs=5e-6)
    assert ci.ipca_realized_factor == pytest.approx(1.034368, abs=5e-6)
    assert ci.inflation_curve.days[-2:] == (2520, 2646)  # o CORRIGIDO usa todos os vértices


def test_ponta_inicial_e_o_dashboard() -> None:
    first, dash = report().stages[0], report().legacy.dashboard
    assert first.di == dash.di
    assert first.inflation == dash.inflation
    assert first.cds == dash.cds


def test_ponta_final_e_o_corrigido() -> None:
    last, corr = report().stages[-1], report().corrected
    for field in FIELDS:
        got, exp = getattr(last, field), getattr(corr, field)
        assert max(abs(a - b) for a, b in zip(got, exp, strict=True)) < 1e-15


def test_etapa_anualizacao_reproduz_ano_civil_do_legado() -> None:
    """Depois da 1ª troca, o DI é o ano civil da planilha (DI!S27, S28:S37)."""
    stage, di = report().stages[1], report().legacy.di
    assert stage.di[0] == pytest.approx(di.calendar_year1, abs=1e-14)
    assert all(
        a == pytest.approx(b, abs=1e-14) for a, b in zip(stage.di[1:], di.forwards, strict=True)
    )
    # Inflação e CDS não mudam nessa etapa.
    assert all(
        abs(a - b) < 1e-14
        for a, b in zip(stage.inflation, report().stages[0].inflation, strict=True)
    )
    assert all(abs(a - b) < 1e-14 for a, b in zip(stage.cds, report().stages[0].cds, strict=True))


@pytest.mark.parametrize("field", FIELDS)
def test_soma_das_causas_e_a_diferenca_total(field: str) -> None:
    stages = report().stages
    contrib = contributions(stages, field)
    assert tuple(contrib) == STAGE_NAMES[1:]
    for i in range(11):
        total = getattr(stages[-1], field)[i] - getattr(stages[0], field)[i]
        assert sum(c[i] for c in contrib.values()) == pytest.approx(total, abs=1e-14)


def test_curva_flat_metodo_nao_importa() -> None:
    """Item 10.4: com curvas flat, acumulação e interpolação não mudam nada."""
    raw = json.loads((LEGACY / "inputs_planilha.json").read_text(encoding="utf-8"))
    legacy = legacy_inputs_from_json(raw)
    legacy = replace(
        legacy,
        inflation_curve_pct=(6.0,) * 19,
        di_curve_pct=(14.0,) * 19,
        cds_bps=(100.0,) * 9,
    )
    ci = report().corrected_inputs
    ci = replace(
        ci,
        di_curve=VertexCurve(ci.di_curve.days, (0.14,) * len(ci.di_curve.days)),
        inflation_curve=VertexCurve(ci.inflation_curve.days, (0.06,) * 21),
        cds_curve=VertexCurve(ci.cds_curve.days, (0.01,) * 9),
    )
    stages = legacy_to_corrected(legacy, ci)
    for field in FIELDS:
        contrib = contributions(stages, field)
        for cause in ("acumulação", "interpolação"):
            assert max(abs(x) for x in contrib[cause]) < 1e-12, (field, cause)
    # E, com os mesmos cortes e realizado, LEGADO e CORRIGIDO dão o mesmo número.
    corr = compute_corrected(ci)
    assert max(abs(a - b) for a, b in zip(stages[4].di, corr.di, strict=True)) < 1e-12


def test_relatorio_markdown_e_csv() -> None:
    rep = report()
    md = render_markdown(rep)
    assert "| 2036 |" in md
    assert "Data-base (t0): 04/09/2026" in md
    rows = list(csv.DictReader(io.StringIO(render_csv(rep))))
    assert len(rows) == 4 * 11
    for row in rows:
        total = float(row["dif_bps"])
        parts = sum(float(row[f"bps_{n}"]) for n in STAGE_NAMES[1:])
        assert parts == pytest.approx(total, abs=1e-5)


def test_tabela_publicada_esta_atualizada() -> None:
    """``docs/f2_legado_x_corrigido.csv`` é o que o código gera hoje.

    Mesmas linhas e colunas; números iguais até a última casa que importa. A potência
    da libm do Linux (CI) pode diferir da do macOS no último bit, e o CSV traz o
    ``repr`` completo: a comparação exata acusaria isso como tabela desatualizada.
    """
    published = (ROOT / "docs" / "f2_legado_x_corrigido.csv").read_text(encoding="utf-8")
    pub = list(csv.reader(io.StringIO(published)))
    now = list(csv.reader(io.StringIO(render_csv(report_oficial()))))
    assert pub[0] == now[0]
    assert [r[:2] for r in pub] == [r[:2] for r in now]
    for a, b in zip(pub[1:], now[1:], strict=True):
        assert [float(x) for x in a[2:4]] == pytest.approx([float(x) for x in b[2:4]], abs=1e-14)
        assert [float(x) for x in a[4:]] == pytest.approx([float(x) for x in b[4:]], abs=2e-6)
    md = (ROOT / "docs" / "F2_LEGADO_X_CORRIGIDO.md").read_text(encoding="utf-8")
    assert md == render_markdown(report_oficial())


def test_legado_da_cascata_exige_linhas_completas() -> None:
    raw = json.loads((LEGACY / "inputs_planilha.json").read_text(encoding="utf-8"))
    raw["inflation_params"] = ["Dezembro", "4º Tri"]
    legacy = legacy_inputs_from_json(raw)
    assert compute_legacy(legacy).dashboard.inflation[0] is None
    with pytest.raises(ValueError, match="#N/A"):
        legacy_to_corrected(legacy, report().corrected_inputs)


def test_corrigido_bate_com_referencia_independente() -> None:
    """Oráculo escrito às cegas a partir de E8 (ver referencia_independente/LEIAME.md)."""
    ref = json.loads((F2 / "referencia_independente" / "blind_B_ii.json").read_text("utf-8"))
    corr = report().corrected
    for i, year in enumerate(corr.years):
        row = ref["rows"][str(year)]
        assert corr.di[i] == pytest.approx(row["di"], abs=1e-12)
        assert corr.inflation[i] == pytest.approx(row["inflacao"], abs=1e-12)
        assert corr.cds[i] == pytest.approx(row["cds"], abs=1e-12)
        assert corr.real[i] == pytest.approx(row["juro_real"], abs=1e-12)
    now = corr.cds_current_year
    first = ref["rows"][str(corr.years[0])]
    assert now.remaining_period_accumulated == pytest.approx(first["cds_remaining"], abs=1e-12)
    assert now.annualized_rate == pytest.approx(first["cds_annualized"], abs=1e-12)


class TestEtapas:
    """Cada etapa da cascata mexe só no que o rótulo diz."""

    def test_realizado_so_mexe_no_ano_corrente(self) -> None:
        for field in FIELDS:
            assert all(x == 0 for x in contributions(report().stages, field)["realizado"][1:])

    def test_calendario_nao_mexe_no_ano_corrente(self) -> None:
        for field in FIELDS:
            assert contributions(report().stages, field)["calendário"][0] == 0

    def test_anualizacao_so_mexe_no_di_2026(self) -> None:
        contrib = contributions(report().stages, "di")["anualização"]
        assert all(abs(x) < 1e-14 for x in contrib[1:])

    def test_metodo_nao_mexe_no_ano_corrente_antes_do_primeiro_vertice(self) -> None:
        """Com dU(2026) = 80 e intervalo = 104 < 126, as duas curvas são flat até ali."""
        for field in ("di", "inflation", "cds"):
            contrib = contributions(report().stages, field)
            # 80 passos recursivos × uma potência: só ruído de ponto flutuante.
            assert abs(contrib["acumulação"][0]) < 1e-12
            assert abs(contrib["interpolação"][0]) < 1e-12


@pytest.mark.parametrize(
    "folder", ["tests/fixtures/f2", "data/calendar", "tests/fixtures/f3/anbima"]
)
def test_dados_brutos_batem_com_o_manifesto(folder: str) -> None:
    manifest = json.loads((ROOT / folder / "manifest.json").read_text("utf-8"))
    assert manifest
    for entry in manifest:
        assert sha256(ROOT / folder / entry["file"]) == entry["sha256"], entry["file"]


def test_csv_de_feriados_vem_do_xls() -> None:
    folder = ROOT / "data" / "calendar"
    header = (folder / "feriados_anbima.csv").read_text("utf-8").split("\n")[0]
    assert header.endswith(f"sha256={sha256(folder / 'feriados_nacionais.xls')}")


class TestTabelaOficial:
    """t0 = 29/09/2026, curvas da ANBIMA desse dia (Q8, Q14, Q15)."""

    def test_inputs(self) -> None:
        rep = report_oficial()
        ci = rep.corrected_inputs
        assert rep.anbima_date == T0_OFICIAL
        assert ci.year_end_business_days[0] == 64
        assert ci.ipca_last_month == 8  # IPCA de agosto saiu em 11/09, antes de t0
        assert ci.ipca15_used is None  # Forma A desligada por padrão
        assert ci.inflation_gap_business_days == load_anbima_calendar().business_days(
            date(2026, 9, 1), date(2027, 1, 1)
        )
        assert ci.di_curve.days[:5] == (21, 42, 63, 126, 252)
        assert ci.inflation_curve.days == tuple(range(252, 2521, 126))

    def test_etapas(self) -> None:
        names = tuple(s.name for s in report_oficial().stages)
        assert names == ("legado", "erro de colagem", *STAGE_NAMES[1:])

    def test_erro_de_colagem_so_mexe_no_di(self) -> None:
        stages = report_oficial().stages
        for field in ("inflation", "cds"):
            assert all(x == 0 for x in contributions(stages, field)["erro de colagem"])
        assert max(abs(x) for x in contributions(stages, "di")["erro de colagem"]) > 5e-4

    def test_erro_de_colagem_e_o_legado_com_a_curva_certa(self) -> None:
        raw = json.loads((LEGACY / "inputs_planilha.json").read_text(encoding="utf-8"))
        planilha = legacy_inputs_from_json(raw)
        di_ok, _ = legacy_curves_pct(parse_anbima_ettj(ANBIMA_29.read_bytes()))
        certo = replace(planilha, di_curve_pct=di_ok)
        assert report_oficial().stages[1].di == compute_legacy(certo).dashboard.di

    def test_ponta_final_e_o_corrigido(self) -> None:
        last, corr = report_oficial().stages[-1], report_oficial().corrected
        for field in FIELDS:
            got, exp = getattr(last, field), getattr(corr, field)
            assert max(abs(a - b) for a, b in zip(got, exp, strict=True)) < 1e-15

    @pytest.mark.parametrize("field", FIELDS)
    def test_soma_das_causas(self, field: str) -> None:
        stages = report_oficial().stages
        for i in range(11):
            total = getattr(stages[-1], field)[i] - getattr(stages[0], field)[i]
            parts = sum(c[i] for c in contributions(stages, field).values())
            assert parts == pytest.approx(total, abs=1e-14)

    def test_sensibilidade_ipca15(self) -> None:
        rep = report_oficial()
        assert rep.ipca15 is not None
        assert "IPCA-15 de 09/2026" in rep.ipca15.inflation_gap_rule
        assert rep.ipca15.inflation[1:] == rep.corrected.inflation[1:]  # Q12: só o ano corrente
        assert rep.ipca15.di == rep.corrected.di
