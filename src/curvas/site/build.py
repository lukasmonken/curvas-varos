"""Build do site estático (seção 14, F5).

    python -m curvas.site.build --out site [--ocultar-cds] [--dados data]

Lê ``data/latest.json`` e ``data/curves/*.json`` (sempre validados com ``RunOutput``) e
gera as páginas com Jinja2 (autoescape ligado) e Plotly auto-hospedado. Todo número
exibido vem pronto do JSON (seção 5); o JavaScript só alterna o que é mostrado.

Mesma entrada → mesmos bytes: nada de data/hora do build nem ids aleatórios. O link do
formulário "cds" do GitHub Actions sai só quando ``GITHUB_SERVER_URL`` e
``GITHUB_REPOSITORY`` existem no ambiente do build.

Downloads (seção 14) em ``downloads/``: CSV e XLSX do dia (``curvas-AAAA-MM-DD``) e o
CSV do histórico (``historico.csv``), de ``curvas.output``; com o CDS visível, também o
``latest.json``.

Chave Q17 (``--ocultar-cds`` ou ``DEFAULT.site.show_cds_values = False``): nenhum valor
de CDS nem de taxa de desconto em página, gráfico, tabela ou download, e os JSON não são
copiados; os links de coleta continuam.
"""

import argparse
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import plotly.offline
from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

from curvas.config import DATA_DIR, DEFAULT, ROOT
from curvas.models import RunOutput
from curvas.normalize.cds_manual import VERTEX_DAYS
from curvas.output.csv_out import render_day_csv, render_history_csv
from curvas.output.xlsx_out import build_day_xlsx
from curvas.site import charts, view
from curvas.site.spec_doc import render_spec

HERE = Path(__file__).resolve().parent
SPEC_PATH = ROOT / "docs" / "ESPECIFICACAO.md"
PAGES = (
    ("index.html", "Visão geral"),
    ("curvas.html", "Curvas"),
    ("realizado.html", "Realizado"),
    ("historico.html", "Histórico"),
    ("metodologia.html", "Metodologia"),
    ("cds.html", "Coleta do CDS"),
)
ASSETS = ("tokens.css", "site.css", "site.js")
DOWNLOADS = "downloads"
HISTORY_CSV = f"{DOWNLOADS}/historico.csv"
HISTORY_KEYS = (
    ("di", "DI", ".1%", ".2%"),
    ("inflation", "Inflação", ".1%", ".2%"),
    ("cds", "CDS", ".2%", ".2%"),
    ("real", "Juro real", ".1%", ".2%"),
    ("discount", "Taxa de desconto", ".1%", ".2%"),
)


@dataclass(frozen=True)
class Inputs:
    latest: RunOutput
    history: tuple[RunOutput, ...]  # todas as datas-base, da mais antiga à mais recente


def load_inputs(data: Path) -> Inputs:
    """``latest.json`` e ``curves/*.json``, validados; ``latest`` sempre entra no histórico."""
    latest = RunOutput.model_validate_json((data / "latest.json").read_bytes())
    by_date: dict[date, RunOutput] = {}
    for path in sorted((data / "curves").glob("*.json")):
        out = RunOutput.model_validate_json(path.read_bytes())
        by_date[out.metadata.as_of_date] = out
    by_date[latest.metadata.as_of_date] = latest
    return Inputs(latest, tuple(by_date[d] for d in sorted(by_date)))


def workflow_url(env: Mapping[str, str]) -> str | None:
    """Formulário do workflow "cds" (workflow_dispatch), se o build roda no GitHub."""
    server, repo = env.get("GITHUB_SERVER_URL"), env.get("GITHUB_REPOSITORY")
    if not server or not repo:
        return None
    return f"{server.rstrip('/')}/{repo}/actions/workflows/cds.yml"


def _day_file(t0: date) -> str:
    """Caminho dos downloads do dia, sem a extensão."""
    return f"{DOWNLOADS}/curvas-{t0.isoformat()}"


def downloads(t0: date, show_cds: bool) -> list[dict[str, str]]:
    """Bloco de downloads da visão geral (lista de {label, href}).

    Com o CDS oculto (Q17), o CSV e o XLSX saem sem CDS e sem taxa de desconto, e o JSON
    não é publicado.
    """
    day = _day_file(t0)
    links = [
        {"label": "CSV do dia", "href": f"{day}.csv"},
        {"label": "XLSX do dia (layout do Dashboard)", "href": f"{day}.xlsx"},
        {"label": "CSV do histórico", "href": HISTORY_CSV},
    ]
    if show_cds:
        links.append({"label": "JSON do dia (latest.json)", "href": "latest.json"})
    return links


def download_files(inputs: Inputs, show_cds: bool) -> dict[str, bytes]:
    """Caminho no site → conteúdo dos downloads gerados no build (sem o ``latest.json``)."""
    day = _day_file(inputs.latest.metadata.as_of_date)
    return {
        f"{day}.csv": render_day_csv(inputs.latest, show_cds=show_cds).encode("utf-8"),
        f"{day}.xlsx": build_day_xlsx(inputs.latest, show_cds=show_cds),
        HISTORY_CSV: render_history_csv(inputs.history, show_cds=show_cds).encode("utf-8"),
    }


def _environment() -> Environment:
    return Environment(
        loader=FileSystemLoader(HERE / "templates"),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )


def _curve_tabs(inputs: Inputs, show_cds: bool, compare: Sequence[date]) -> list[dict[str, Any]]:
    latest, t0 = inputs.latest, inputs.latest.metadata.as_of_date
    wanted = {t0, *compare}
    outputs = [o for o in inputs.history if o.metadata.as_of_date in wanted]
    mode = latest.metadata.default_mode
    cds_labels = {days: label for label, days in VERTEX_DAYS.items()}
    tabs = []
    for curve in latest.curves:
        if curve.name == "cds" and not show_cds:
            continue
        tabs.append(
            {
                "name": curve.name,
                "label": view.CURVE_LABELS[curve.name],
                "source": curve.source,
                "rate_chart": Markup(
                    charts.curve_figure(curve.name, outputs, t0, measure="rate", default_mode=mode)
                ),
                "factor_chart": Markup(
                    charts.curve_figure(
                        curve.name, outputs, t0, measure="factor", default_mode=mode
                    )
                ),
                "tables": view.vertex_tables(curve, cds_labels),
            }
        )
    return tabs


def _history_tabs(inputs: Inputs, show_cds: bool) -> list[dict[str, Any]]:
    outputs = inputs.history
    dates = [o.metadata.as_of_date for o in outputs]
    mode = inputs.latest.metadata.default_mode
    tabs = []
    for key, label, tick, hover in HISTORY_KEYS:
        if key in view.CDS_KEYS and not show_cds:
            continue
        values = {m: view.history_values(outputs, key, m) for m, _ in view.MODES}
        chart = charts.history_figure(
            dates, values, default_mode=mode, tick=tick, hover=hover, div_id=f"historico-{key}"
        )
        tabs.append(
            {
                "key": key,
                "label": label,
                "chart": Markup(chart),
                "tables": view.history_tables(outputs, key),
            }
        )
    return tabs


def render_pages(
    inputs: Inputs,
    *,
    show_cds: bool,
    env: Mapping[str, str],
    spec_path: Path = SPEC_PATH,
    download_links: Sequence[Mapping[str, str]] = (),
) -> dict[str, str]:
    """Nome do arquivo → HTML de cada página."""
    latest = inputs.latest
    meta = latest.metadata
    t0 = meta.as_of_date
    jinja = _environment()
    commit = meta.git_commit or ""
    common: dict[str, Any] = {
        "nav": [{"href": href, "label": label} for href, label in PAGES],
        "modes": view.MODES,
        "default_mode": meta.default_mode,
        "show_cds": show_cds,
        "t0": view.day(t0),
        "code_version": meta.code_version,
        "commit": commit[:7] + ("-dirty" if commit.endswith("-dirty") else ""),
        "schema_version": meta.schema_version,
    }
    years = [r.year for r in latest.annual.corrected]
    dates = [o.metadata.as_of_date for o in inputs.history]
    compare = view.compare_dates(dates, t0)
    spec = render_spec(spec_path, show_cds)
    hrefs = {d["href"] for d in download_links}
    pages: dict[str, dict[str, Any]] = {
        "index.html": {
            "ov": view.overview(latest, show_cds),
            "first_year": years[0],
            "last_year": years[-1],
            "downloads": list(download_links),
            "mode_toggle": True,
        },
        "curvas.html": {
            "tabs": _curve_tabs(inputs, show_cds, compare),
            "compare": [{"value": d.isoformat(), "label": view.day(d)} for d in compare],
            "mode_toggle": True,
        },
        "realizado.html": {"r": view.realized(latest)},
        "historico.html": {
            "tabs": _history_tabs(inputs, show_cds),
            "n_dates": len(dates),
            "first_date": view.day(dates[0]),
            "last_date": view.day(dates[-1]),
            "history_csv": HISTORY_CSV if HISTORY_CSV in hrefs else None,
            "mode_toggle": True,
        },
        "metodologia.html": {
            "spec": spec,
            "spec_html": Markup(spec.html),
            "default_label": view.mode_label(meta.default_mode),
        },
        "cds.html": {
            "c": view.cds_collection(
                latest,
                DEFAULT.urls.investing_cds,
                VERTEX_DAYS,
                show_cds,
                workflow_url(env),
            ),
        },
    }
    titles = dict(PAGES)
    html = {}
    for name, extra in pages.items():
        context = {"mode_toggle": False, **common, **extra}
        html[name] = jinja.get_template(name).render(page=name, title=titles[name], **context)
    return html


_OWNED = (*(name for name, _ in PAGES), "assets", DOWNLOADS, "latest.json", "curves")


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def build(
    out: Path,
    data: Path = DATA_DIR,
    *,
    show_cds: bool | None = None,
    env: Mapping[str, str] | None = None,
    spec_path: Path = SPEC_PATH,
) -> Path:
    """Gera o site em ``out`` e devolve o caminho do ``index.html``.

    Antes de escrever, apaga o que um build anterior deixou com os mesmos nomes (páginas,
    ``assets/``, ``downloads/``, ``latest.json``, ``curves/``): um build com o CDS oculto
    não pode herdar o JSON nem os downloads de um build anterior.
    """
    show = DEFAULT.site.show_cds_values if show_cds is None else show_cds
    inputs = load_inputs(data)
    pages = render_pages(
        inputs,
        show_cds=show,
        env=os.environ if env is None else env,
        spec_path=spec_path,
        download_links=downloads(inputs.latest.metadata.as_of_date, show),
    )
    out.mkdir(parents=True, exist_ok=True)
    for name in _OWNED:
        target = out / name
        if target.is_dir():
            shutil.rmtree(target)
        elif target.exists():
            target.unlink()
    for name, text in pages.items():
        _write(out / name, text)
    assets = out / "assets"
    for name in ASSETS:
        _write(assets / name, (HERE / "static" / name).read_text(encoding="utf-8"))
    _write(assets / "plotly.min.js", plotly.offline.get_plotlyjs())
    for name, content in download_files(inputs, show).items():
        (out / name).parent.mkdir(parents=True, exist_ok=True)
        (out / name).write_bytes(content)
    if show:
        shutil.copyfile(data / "latest.json", out / "latest.json")
        (out / "curves").mkdir()
        for o in inputs.history:
            name = f"{o.metadata.as_of_date.isoformat()}.json"
            source = data / "curves" / name
            if source.exists():
                shutil.copyfile(source, out / "curves" / name)
    return out / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m curvas.site.build", description=__doc__)
    parser.add_argument("--out", type=Path, default=ROOT / "site", help="pasta de saída")
    parser.add_argument("--dados", type=Path, default=DATA_DIR, help="pasta data/ de entrada")
    parser.add_argument(
        "--ocultar-cds",
        action="store_true",
        help="esconde os valores de CDS e a taxa de desconto (Q17); os links de coleta ficam",
    )
    args = parser.parse_args(argv)
    index = build(args.out, args.dados, show_cds=False if args.ocultar_cds else None)
    print(f"ok: {index}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
