"""Site estático (seção 14, F5): páginas, links, Q17, determinismo e tokens (Q5)."""

import re
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import pytest

from curvas.config import DEFAULT
from curvas.models import Alert, CurveOut, LegacyYtg, MonthlyValue, RunOutput
from curvas.output.csv_out import render_day_csv, render_history_csv
from curvas.output.xlsx_out import build_day_xlsx
from curvas.site import view
from curvas.site.build import PAGES, build, main, workflow_url
from curvas.site.charts import THEME
from curvas.site.spec_doc import hide_cds, render_spec

ROOT = Path(__file__).resolve().parent.parent
# Cópia congelada das saídas de 29/09 a 01/10/2026: o data/ de produção muda todo dia, e o
# daily roda estes testes antes de publicar (não podem depender do que o pipeline gravou).
DATA = ROOT / "tests" / "fixtures" / "f5" / "data"
STATIC = ROOT / "src" / "curvas" / "site" / "static"
GITHUB = {"GITHUB_SERVER_URL": "https://github.com", "GITHUB_REPOSITORY": "varos/curvas"}


def base() -> RunOutput:
    return RunOutput.model_validate_json((DATA / "latest.json").read_bytes())


def write_data(tmp: Path, outputs: Sequence[RunOutput]) -> Path:
    data = tmp / "data"
    (data / "curves").mkdir(parents=True)
    for out in outputs:
        path = data / "curves" / f"{out.metadata.as_of_date.isoformat()}.json"
        path.write_text(out.model_dump_json(indent=2), encoding="utf-8")
    latest = max(outputs, key=lambda o: o.metadata.as_of_date)
    (data / "latest.json").write_text(latest.model_dump_json(indent=2), encoding="utf-8")
    return data


def single_day() -> RunOutput:
    """Uma data só, LEGADO com None no ano corrente, fonte defasada e alertas."""
    out = base()
    legacy = list(out.annual.legacy)
    legacy[0] = legacy[0].model_copy(
        update={"di": None, "inflation": None, "cds": None, "real": None, "discount": None}
    )
    comparison = list(out.comparison)
    comparison[0] = comparison[0].model_copy(
        update={k: None for k in ("di_bps", "inflation_bps", "cds_bps", "real_bps", "discount_bps")}
    )
    sources = [
        s.model_copy(
            update={"stale": True, "fallback_reason": "ETTJ de t0 ausente; usada a de 30/09"}
        )
        if s.source == "anbima_ettj"
        else s
        for s in out.sources
    ]
    alerts = [
        Alert(level="error", code="teste", message="Erro de teste"),
        Alert(level="info", code="teste", message="Informação de teste"),
    ]
    return out.model_copy(
        update={
            "annual": out.annual.model_copy(
                update={
                    "legacy": legacy,
                    "legacy_ytg": LegacyYtg(di=None, inflation=None, cds=None),
                }
            ),
            "comparison": comparison,
            "sources": sources,
            "alerts": alerts,
        }
    )


def _marked_curve(curve: CurveOut) -> CurveOut:
    vertices = [v.model_copy(update={"rate": 0.0432101}) for v in curve.corrected_vertices]
    sample = [
        p.model_copy(update={"rate": 0.0432987, "factor": 1.0432987})
        for p in curve.corrected_sample
    ]
    return curve.model_copy(
        update={
            "corrected_vertices": vertices,
            "legacy_vertices": vertices,
            "corrected_sample": sample,
            "legacy_sample": sample,
        }
    )


def marked_cds() -> tuple[RunOutput, list[str]]:
    """Saída com valores de CDS e de desconto inconfundíveis e as strings que os revelariam."""
    out = base()
    rows = {
        mode: [
            r.model_copy(update={"cds": 0.4321 + i / 10_000, "discount": 0.5678 + i / 10_000})
            for i, r in enumerate(getattr(out.annual, mode))
        ]
        for mode in ("corrected", "legacy")
    }
    comparison = [
        c.model_copy(update={"cds_bps": 987.6 + i, "discount_bps": 876.5 + i})
        for i, c in enumerate(out.comparison)
    ]
    curves = [_marked_curve(c) if c.name == "cds" else c for c in out.curves]
    bps = [4321.11 + i for i in range(9)]
    alerts = [
        *out.alerts,
        Alert(
            level="warning",
            code="variacao_diaria",
            message="corrected cds 2027: +55.1 bps desde 2026-09-30 (limite 50 bps)",
        ),
    ]
    marked = out.model_copy(
        update={
            "annual": out.annual.model_copy(
                update={
                    **rows,
                    "corrected_cds_current_year": out.annual.corrected_cds_current_year.model_copy(
                        update={"annualized_rate": 0.4444, "remaining_period_accumulated": 0.3333}
                    ),
                    "legacy_ytg": out.annual.legacy_ytg.model_copy(update={"cds": 0.2222}),
                }
            ),
            "comparison": comparison,
            "curves": curves,
            "inputs": out.inputs.model_copy(
                update={"legacy": out.inputs.legacy.model_copy(update={"cds_bps": bps})}
            ),
            "alerts": alerts,
        }
    )
    secrets = [
        *(view.pct(getattr(r, k)) for rs in rows.values() for r in rs for k in ("cds", "discount")),
        *(view.bps(getattr(c, k)) for c in comparison for k in ("cds_bps", "discount_bps")),
        *(view.num(x, 2) for x in bps),
        "44,44%",
        "33,33%",
        "22,22%",
        "4,3210%",
        "0.0432101",
        "0.0432987",
        "+55,1",
    ]
    return marked, secrets


def html_files(site: Path) -> dict[str, str]:
    return {p.name: p.read_text(encoding="utf-8") for p in sorted(site.glob("*.html"))}


def tree(site: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(site)): p.read_bytes() for p in sorted(site.rglob("*")) if p.is_file()
    }


# Build a partir de data/ ------------------------------------------------------------


@pytest.fixture(scope="module")
def site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("site")
    build(out, DATA, show_cds=True, env={})
    return out


def test_todas_as_paginas(site: Path) -> None:
    for name, _ in PAGES:
        assert (site / name).is_file(), name
    for asset in ("tokens.css", "site.css", "site.js", "plotly.min.js"):
        assert (site / "assets" / asset).stat().st_size > 0
    assert (site / "latest.json").read_bytes() == (DATA / "latest.json").read_bytes()
    for path in (DATA / "curves").glob("*.json"):
        assert (site / "curves" / path.name).read_bytes() == path.read_bytes()


def test_downloads(site: Path) -> None:
    out = base()
    history = [RunOutput.model_validate_json(p.read_bytes()) for p in (DATA / "curves").glob("*")]
    day = site / "downloads" / f"curvas-{out.metadata.as_of_date.isoformat()}"
    assert day.with_suffix(".csv").read_text(encoding="utf-8") == render_day_csv(out)
    assert day.with_suffix(".xlsx").read_bytes() == build_day_xlsx(out)
    assert (site / "downloads" / "historico.csv").read_text(encoding="utf-8") == render_history_csv(
        history
    )
    index = (site / "index.html").read_text(encoding="utf-8")
    for name in (day.with_suffix(".csv"), day.with_suffix(".xlsx")):
        assert f'href="downloads/{name.name}" download' in index
    assert 'href="downloads/historico.csv" download' in index
    historico = (site / "historico.html").read_text(encoding="utf-8")
    assert 'href="downloads/historico.csv" download' in historico


def test_cabecalho_comum(site: Path) -> None:
    for name, text in html_files(site).items():
        assert '<html lang="pt-BR"' in text, name
        assert '<meta name="viewport" content="width=device-width, initial-scale=1">' in text
        assert '<span class="wordmark">VAROS</span>' in text
        assert "CDS: cópia manual do Investing.com" in text


def test_links_internos_resolvem(site: Path) -> None:
    ids = {
        name: set(re.findall(r'\sid="([^"]+)"', text)) for name, text in html_files(site).items()
    }
    for name, text in html_files(site).items():
        for link in re.findall(r'(?:href|src)="([^"]+)"', text):
            if link.startswith(("https://", "http://")):
                continue
            path, _, anchor = link.partition("#")
            target = path or name
            assert (site / target).exists(), f"{name}: {link}"
            if anchor:
                assert anchor in ids[target], f"{name}: âncora {link}"


def test_nenhuma_requisicao_externa_alem_do_google_fonts(site: Path) -> None:
    allowed = ("https://fonts.googleapis.com", "https://fonts.gstatic.com")
    for name, text in html_files(site).items():
        for tag in re.findall(r"<(?:script|link|img|iframe)\b[^>]*>", text):
            for url in re.findall(r'(?:src|href)="([^"]+)"', tag):
                assert not url.startswith(("http:", "//")), f"{name}: {url}"
                assert not url.startswith("https:") or url.startswith(allowed), f"{name}: {url}"
        assert "cdn.plot.ly" not in text
        assert "mathjax" not in text.lower()


# Hosts que o site pode citar: fontes do pipeline, abas do CDS, Google Fonts e o formulário
# do Actions. Qualquer outro (por exemplo, um link interno copiado da planilha) falha.
ALLOWED_HOSTS = {
    "api.bcb.gov.br",
    "br.investing.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
    "github.com",
    "servicodados.ibge.gov.br",
    "www.anbima.com.br",
}


def test_so_hosts_conhecidos(site: Path) -> None:
    for path in site.rglob("*"):
        # plotly.min.js é a biblioteca de terceiros, copiada sem alteração.
        if path.is_file() and path.name != "plotly.min.js" and path.suffix != ".xlsx":
            found = re.findall(rb"https?://([A-Za-z0-9.-]+)", path.read_bytes())
            hosts = {h.decode() for h in found}
            assert hosts <= ALLOWED_HOSTS, (path, hosts - ALLOWED_HOSTS)


def test_visao_geral(site: Path) -> None:
    out = base()
    text = (site / "index.html").read_text(encoding="utf-8")
    assert f'data-mode="{out.metadata.default_mode}"' in text
    assert view.day(out.metadata.as_of_date) in text
    for mode in ("corrected", "legacy"):
        assert f'class="card only-{mode}"' in text
        for row in getattr(out.annual, mode):
            assert view.pct(row.di) in text
    assert view.pct(out.annual.corrected_cds_current_year.annualized_rate) in text
    assert f"YTG {out.inputs.legacy.first_year}" in text
    assert view.bps(out.comparison[0].di_bps) in text
    assert 'href="latest.json" download' in text
    assert 'aria-pressed="true"' in text


def test_curvas_traz_todas_as_datas_e_os_dois_modos(site: Path) -> None:
    text = (site / "curvas.html").read_text(encoding="utf-8")
    for name in ("di", "inflation", "cds"):
        for measure in ("taxa", "fator"):
            assert f'id="grafico-{name}-{measure}"' in text
    dates = [date.fromisoformat(p.stem) for p in (DATA / "curves").glob("*.json")]
    compare = view.compare_dates(dates, base().metadata.as_of_date)
    assert compare
    for d in compare:
        assert f'<option value="{d.isoformat()}">' in text
        assert f'"date":"{d.isoformat()}"' in text
    assert '"mode":"legacy"' in text
    assert '"mode":"corrected"' in text


def test_coleta_do_cds(site: Path) -> None:
    text = (site / "cds.html").read_text(encoding="utf-8")
    assert len(DEFAULT.urls.investing_cds) == 9
    for label, url in DEFAULT.urls.investing_cds:
        assert f'href="{url}" target="_blank" rel="noopener noreferrer"' in text, label
    for value in base().inputs.legacy.cds_bps:
        assert view.num(value, 2) in text
    assert "python -m curvas.cds_add" in text
    assert "actions/workflows/cds.yml" not in text  # sem GITHUB_* no ambiente


def test_metodologia(site: Path) -> None:
    text = (site / "metodologia.html").read_text(encoding="utf-8")
    assert "LEGADO × CORRIGIDO" in text
    assert '<div class="table-wrap" tabindex="0" role="region" aria-labelledby="esp-' in text
    assert "<pre><code" in text
    assert 'id="esp-e8-metodologia-corrigida"' in text
    assert "ESPECIFICAÇÃO: Plataforma" not in text  # o título do arquivo sai
    # O texto do site segue as fórmulas do LEGADO (seção 2), não a leitura que a
    # especificação (renderizada abaixo, como está) fez dos valores da planilha.
    ours = text.split('id="especificacao"')[0]
    assert "19 vértices de 126 a 2394 d.u." in ours
    assert "2646 := 2520" not in ours  # C30:C31 não entram em nenhuma fórmula (E6.8)
    assert "a Selic dos trimestres anteriores não entra no DI publicado" in ours
    assert "(1 + Acum(YTG))^(252/YTG) − 1" in ours
    assert "taxa do primeiro vértice" not in ours
    assert "E6.12" not in text  # rótulo interno: a especificação renderizada vai até E6.11


def test_realizado(site: Path) -> None:
    text = (site / "realizado.html").read_text(encoding="utf-8")
    out = base()
    # Última observação real antes de t0, e não a última do SGS 12 (que pode ser o próprio t0).
    last = view.day(out.realized.cdi.last_observation)
    assert f"Último CDI observado antes de t0 (SGS 12)</dt><dd>{last}</dd>" in text
    assert "Última observação no SGS 12" not in text
    assert "IPCA, usado nos dois modos" in text
    assert "só os do trimestre de m entram no DI publicado do LEGADO" in text


def test_tabelas_rolaveis_recebem_foco(site: Path) -> None:
    """Contêiner rolável com foco de teclado e nome acessível (axe: scrollable-region-focusable)."""
    for name, text in html_files(site).items():
        ids = set(re.findall(r'\sid="([^"]+)"', text))
        wraps = re.findall(r'<div class="table-wrap"([^>]*)>', text)
        for attrs in wraps:
            assert 'tabindex="0" role="region"' in attrs, f"{name}: {attrs}"
            label = re.search(r'aria-labelledby="([^"]+)"|aria-label="([^"]+)"', attrs)
            assert label is not None, f"{name}: {attrs}"
            if label.group(1):
                assert label.group(1) in ids, f"{name}: {label.group(1)}"
    assert len(re.findall('class="table-wrap"', html_files(site)["metodologia.html"])) > 1


def test_plotly_sem_nuvem_e_fora_do_head(site: Path) -> None:
    for name in ("curvas.html", "historico.html"):
        text = (site / name).read_text(encoding="utf-8")
        head, body = text.split("<body>")
        assert "plotly.min.js" not in head, name  # não trava a primeira pintura da página
        first_chart = body.index("Plotly.newPlot")
        assert body.index('<script src="assets/plotly.min.js"></script>') < first_chart, name
        charts = body.count("Plotly.newPlot")
        assert charts, name
        assert body.count('"showSendToCloud": false') == charts, name
        # Legenda presa ao pé do contêiner: não cobre o título do eixo X no celular.
        assert body.count('"yref":"container"') == charts, name
    for name in ("index.html", "realizado.html", "metodologia.html", "cds.html"):
        assert "plotly.min.js" not in (site / name).read_text(encoding="utf-8"), name


# Saídas sintéticas ------------------------------------------------------------------


def test_uma_data_so_legado_indisponivel_e_fonte_defasada(tmp_path: Path) -> None:
    data = write_data(tmp_path, [single_day()])
    site = tmp_path / "site"
    build(site, data, show_cds=True, env={})
    pages = html_files(site)
    assert set(pages) == {name for name, _ in PAGES}
    index = pages["index.html"]
    year = base().annual.legacy[0].year
    assert f'<tr><th scope="row">{year}</th>' + "<td>—</td>" * 5 + "</tr>" in index
    assert '<span class="badge stale">Defasado</span>' in index
    assert "ETTJ de t0 ausente; usada a de 30/09" in index
    assert '<li class="error"><span class="badge error">Erro</span> Erro de teste' in index
    assert '<li class="info">' in index
    historico = pages["historico.html"]
    assert "1 data-base" in historico
    assert 'id="historico-di"' in historico
    curvas = pages["curvas.html"]
    assert "nenhuma outra data-base" in curvas
    assert '"role":"compare"' not in curvas


def test_cds_oculto_nao_vaza_nenhum_numero(tmp_path: Path) -> None:
    marked, secrets = marked_cds()
    data = write_data(tmp_path, [marked])
    shown, hidden = tmp_path / "com", tmp_path / "sem"
    build(shown, data, show_cds=True, env={})
    build(hidden, data, show_cds=False, env={})
    shown_text = "".join(html_files(shown).values())
    # as strings de controle aparecem com o CDS visível (senão o teste não provaria nada)
    for s in secrets:
        if s not in {"0.0432101", "0.0432987"}:  # números crus só existem nos gráficos
            assert s in shown_text, s
    assert "0.0432101" in shown_text
    for name, text in html_files(hidden).items():
        for s in secrets:
            assert s not in text, f"{name}: {s}"
        assert "Taxa de desconto</th>" not in text, name
    assert not (hidden / "latest.json").exists()
    assert not (hidden / "curves").exists()
    rows = [*marked.annual.corrected, *marked.annual.legacy]
    raw = [repr(x) for r in rows for x in (r.cds, r.discount) if x is not None]
    assert any(v in (shown / "downloads" / "historico.csv").read_text() for v in raw)
    for path in (hidden / "downloads").glob("*.csv"):
        text = path.read_text(encoding="utf-8")
        assert text.startswith("data_base,modo,ano,di,inflacao,juro_real\n"), path.name
        for v in raw:
            assert v not in text, f"{path.name}: {v}"
    assert len(list((hidden / "downloads").glob("*.xlsx"))) == 1  # conteúdo: test_exports
    cds = (hidden / "cds.html").read_text(encoding="utf-8")
    for _, url in DEFAULT.urls.investing_cds:
        assert f'href="{url}" target="_blank" rel="noopener noreferrer"' in cds
    assert "variação acima do limite" in (hidden / "index.html").read_text(encoding="utf-8")


def test_cds_oculto_com_os_dados_reais(tmp_path: Path) -> None:
    site = tmp_path / "site"
    build(site, DATA, show_cds=False, env={})
    out = base()
    values = [view.num(x, 2) for x in out.inputs.legacy.cds_bps]
    cds = next(c for c in out.curves if c.name == "cds")
    values += [view.pct(v.rate, 4) for v in cds.corrected_vertices]
    for name, text in html_files(site).items():
        for v in values:
            assert v not in text, f"{name}: {v}"
    assert not (site / "latest.json").exists()


def test_build_oculto_apaga_o_json_de_um_build_anterior(tmp_path: Path) -> None:
    site = tmp_path / "site"
    build(site, DATA, show_cds=True, env={})
    assert (site / "latest.json").exists()
    main(["--out", str(site), "--dados", str(DATA), "--ocultar-cds"])
    assert not (site / "latest.json").exists()
    assert not (site / "curves").exists()
    index = (site / "index.html").read_text(encoding="utf-8")
    assert 'href="latest.json"' not in index
    assert "Sem CDS e sem taxa de desconto (Q17)." in index
    assert (
        (site / "downloads" / "historico.csv")
        .read_text(encoding="utf-8")
        .startswith("data_base,modo,ano,di,inflacao,juro_real\n")
    )


def test_determinismo(tmp_path: Path) -> None:
    a, b = tmp_path / "a", tmp_path / "b"
    build(a, DATA, show_cds=True, env=GITHUB)
    build(b, DATA, show_cds=True, env=GITHUB)
    assert tree(a) == tree(b)


def test_link_do_formulario_do_github() -> None:
    assert workflow_url(GITHUB) == "https://github.com/varos/curvas/actions/workflows/cds.yml"
    assert workflow_url({"GITHUB_REPOSITORY": "varos/curvas"}) is None
    assert workflow_url({}) is None


def test_link_do_formulario_na_pagina(tmp_path: Path) -> None:
    site = tmp_path / "site"
    build(site, DATA, show_cds=False, env=GITHUB)
    text = (site / "cds.html").read_text(encoding="utf-8")
    assert 'href="https://github.com/varos/curvas/actions/workflows/cds.yml"' in text


# Identidade visual (Q5) -------------------------------------------------------------


def test_tokens_css_igual_ao_theme() -> None:
    css = (STATIC / "tokens.css").read_text(encoding="utf-8")
    tokens = dict(re.findall(r"--([\w-]+):\s*([^;]+);", css))
    assert tokens == THEME
    assert THEME["font-sans"].startswith('"Instrument Sans"')


def test_cores_so_nos_tokens() -> None:
    for name in ("site.css", "site.js"):
        text = (STATIC / name).read_text(encoding="utf-8")
        assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", text), name
        assert "rgb(" not in text, name


# Formatação e regras de exibição ----------------------------------------------------


def test_formatacao_pt_br() -> None:
    assert view.pct(0.139694993) == "13,97%"
    assert view.pct(-0.0032) == "−0,32%"
    assert view.pct(None) == "—"
    assert view.pct(-0.00001) == "0,00%"
    assert view.bps(15.1708) == "+15,2"
    assert view.bps(-2.62) == "−2,6"
    assert view.bps(-1.5e-10) == "0,0"
    assert view.num(1234.5, 2) == "1.234,50"
    assert view.day(date(2026, 10, 1)) == "01/10/2026"
    assert view.month_year(2026, 1) == "jan/2026"
    assert view.pct_points(-0.32) == "−0,32%"


def test_cdi_no_primeiro_dia_util_do_ano() -> None:
    """Nenhum dia de CDI antes de t0: o período não sai invertido (01/01 a 31/12 do ano antes)."""
    out = base()
    t0 = date(2027, 1, 4)
    cdi = out.realized.cdi.model_copy(
        update={"start": date(2027, 1, 1), "end_exclusive": t0, "business_days": 0, "factor": 1.0}
    )
    first = out.model_copy(
        update={
            "metadata": out.metadata.model_copy(update={"as_of_date": t0}),
            "realized": out.realized.model_copy(update={"cdi": cdi, "cdi_monthly": []}),
        }
    )
    r = view.realized(first)
    assert r.cdi_period == "nenhum dia útil de CDI no ano antes de t0 (t0 = 04/01/2027)"
    assert view.realized(out).cdi_period == "01/01/2026 a 30/09/2026 (véspera de t0 = 01/10/2026)"


def test_nota_da_linha_ytg_do_legado() -> None:
    """DI e inflação do YTG trazem o realizado do trimestre de m; o CDS é só a curva."""
    out = base()
    li = out.inputs.legacy
    assert (li.month, li.quarter, li.ytg_days) == (8, 3, 84)
    (note,) = view.overview(out, show_cds=True).tables[1].notes
    assert "realizado dos meses do trimestre de m (jul–ago/2026: Selic e IPCA)" in note
    assert "84 dias úteis a partir de t0 (DI!S26 e Inflação!E4)" in note
    assert "CDS: só a curva nos 84 dias úteis" in note
    assert "período restante, não anualizados" not in note
    (hidden,) = view.overview(out, show_cds=False).tables[1].notes
    assert "CDS" not in hidden
    july = out.model_copy(
        update={
            "inputs": out.inputs.model_copy(
                update={"legacy": li.model_copy(update={"month": 7, "ytg_days": 105})}
            )
        }
    )
    (note,) = view.overview(july, show_cds=True).tables[1].notes
    assert "(jul/2026: Selic e IPCA)" in note
    turn = out.model_copy(
        update={
            "inputs": out.inputs.model_copy(
                update={"legacy": li.model_copy(update={"month": None, "quarter": None})}
            )
        }
    )
    (note,) = view.overview(turn, show_cds=True).tables[1].notes
    assert "virada do ano" in note


def test_cdi_mensal_parcial_e_vazio() -> None:
    out = base()
    t0 = date(2026, 10, 15)
    months = [MonthlyValue(year=2026, month=m, value_pct=1.0) for m in range(1, 11)]
    mid = out.model_copy(
        update={
            "metadata": out.metadata.model_copy(update={"as_of_date": t0}),
            "realized": out.realized.model_copy(update={"cdi_monthly": months}),
        }
    )
    r = view.realized(mid)
    assert r.cdi_partial
    assert r.cdi[-1].cells[1] == "parcial, até 14/10/2026 (véspera de t0)"
    assert all(row.cells[1] == "" for row in r.cdi[:-1])
    empty = out.model_copy(update={"realized": out.realized.model_copy(update={"cdi_monthly": []})})
    assert view.realized(empty).cdi == ()


def test_pagina_realizado_sem_cdi_mensal(tmp_path: Path) -> None:
    out = base()
    empty = out.model_copy(update={"realized": out.realized.model_copy(update={"cdi_monthly": []})})
    site = tmp_path / "site"
    build(site, write_data(tmp_path, [empty]), show_cds=True, env={})
    assert "sem dados" in (site / "realizado.html").read_text(encoding="utf-8")


def test_datas_de_comparacao() -> None:
    t0 = date(2026, 12, 30)
    dates = [date(2026, m, d) for m in (9, 10, 11, 12) for d in (1, 10, 20, 28)] + [t0]
    chosen = view.compare_dates(dates, t0, recent=5)
    assert chosen[:5] == (
        date(2026, 12, 28),
        date(2026, 12, 20),
        date(2026, 12, 10),
        date(2026, 12, 1),
        date(2026, 11, 28),
    )
    assert chosen[5:] == (date(2026, 11, 20), date(2026, 10, 28), date(2026, 9, 28))
    assert t0 not in chosen


def test_alerta_de_variacao_do_cds_fica_sem_numero() -> None:
    alert = Alert(
        level="warning",
        code="variacao_diaria",
        message="legacy discount 2030: -61.0 bps desde 2026-09-30 (limite 50 bps)",
    )
    out = base().model_copy(update={"alerts": [alert]})
    hidden = view.overview(out, show_cds=False).alerts[0].message
    assert hidden == "LEGADO, Taxa de desconto 2030: variação acima do limite"
    shown = view.overview(out, show_cds=True).alerts[0].message
    assert shown == "LEGADO, Taxa de desconto 2030: −61,0 bps desde 30/09/2026 (limite de 50 bps)"


def test_alerta_de_variacao_em_pt_br() -> None:
    """Rótulos do site, decimal com vírgula e data dd/mm/aaaa; o JSON continua igual."""
    alerts = [
        Alert(
            level="warning",
            code="variacao_diaria",
            message="corrected di 2027: +55.1 bps desde 2026-09-30 (limite 50 bps)",
        ),
        Alert(level="warning", code="variacao_diaria", message="formato novo: fica como está"),
        Alert(level="info", code="outro", message="corrected di 2027: +55.1 bps"),
    ]
    out = base().model_copy(update={"alerts": alerts})
    for show_cds in (True, False):
        got = [a.message for a in view.overview(out, show_cds=show_cds).alerts]
        assert got == [
            "CORRIGIDO, DI 2027: +55,1 bps desde 30/09/2026 (limite de 50 bps)",
            "formato novo: fica como está",
            "corrected di 2027: +55.1 bps",
        ]


def test_especificacao_sem_cds() -> None:
    text = (
        "**CDS.** Valores do Investing.com.\n\n"
        "| Prazo | 6M | 1A |\n|---|---|---|\n"
        "| Dias úteis | 126 | 252 |\n| bps | 45,67 | 54,35 |\n\n"
        "| Ano | DI | CDS |\n|---|---|---|\n| 2026 | 13,47% | 0,46% |\n\n"
        "| Dado | Fonte |\n|---|---|\n| CDS Brasil (USD) | Investing.com |\n\n"
        "- O CDS sobe de 0,46% para 2,09% ao ano em 62 dias.\n"
        "```\nCDS 0,1\n```\n"
    )
    out = hide_cds(text)
    for gone in ("45,67", "54,35", "0,46%", "2,09%"):
        assert gone not in out
    assert "| Dias úteis | 126 | 252 |" in out
    assert "| 2026 | 13,47% |" in out
    assert "| CDS Brasil (USD) | Investing.com |" in out
    assert "em 62 dias" in out
    assert "CDS 0,1" in out  # bloco de código fica como está


def test_especificacao_real_sem_cds() -> None:
    spec = render_spec(ROOT / "docs" / "ESPECIFICACAO.md", show_cds=False)
    for gone in ("45,67", "245,59", "0,4567", "0,004567"):
        assert gone not in spec.html
    assert [h.text.split(".")[0] for h in spec.toc] == [f"E{i}" for i in range(1, 12)]
