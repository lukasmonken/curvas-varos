"""Build provisório do site (F4): uma página com a tabela de ``data/latest.json``.

    python -m curvas.site.build [--out site]

A F5 substitui isto pelo site completo (Jinja2 + Plotly + identidade visual). Todo
número exibido vem pronto do JSON; nada é calculado aqui além de formatar.
"""

import argparse
import html
import json
import shutil
from pathlib import Path
from typing import Any

from curvas.config import DATA_DIR, ROOT


def _pct(x: float | None) -> str:
    return "—" if x is None else f"{100 * x:.2f}%".replace(".", ",")


def render(latest: dict[str, Any]) -> str:
    meta = latest["metadata"]
    rows = []
    for c, lg in zip(latest["annual"]["corrected"], latest["annual"]["legacy"], strict=True):
        cells = "".join(
            f"<td>{_pct(c[k])}</td><td class=l>{_pct(lg[k])}</td>"
            for k in ("di", "inflation", "cds", "real", "discount")
        )
        rows.append(f"<tr><th>{c['year']}</th>{cells}</tr>")
    head = "".join(
        f"<th colspan=2>{name}</th>"
        for name in ("DI", "Inflação", "CDS", "Juro real", "Taxa de desconto")
    )
    sub = "<th></th>" + "<th>Corrigido</th><th class=l>Legado</th>" * 5
    alerts = "".join(f"<li>{html.escape(a['message'])}</li>" for a in latest["alerts"]) or (
        "<li>Nenhum alerta.</li>"
    )
    sources = "".join(
        f"<li>{html.escape(s['source'])}: dado de {s['source_date'] or '—'}"
        f"{' (defasado)' if s['stale'] else ''}</li>"
        for s in latest["sources"]
    )
    return f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Curvas VAROS</title>
<style>
body{{font-family:system-ui,sans-serif;margin:16px;background:#131313;color:#E2E5EB}}
table{{border-collapse:collapse;font-variant-numeric:tabular-nums}}
th,td{{padding:4px 8px;border-bottom:1px solid #333;text-align:right}}
.l{{color:#878D96}} a{{color:#12D8B2}} .wrap{{overflow-x:auto}}
</style></head><body>
<h1>Curvas VAROS</h1>
<p>Data-base: {meta["as_of_date"]}. Página provisória da F4; o site completo vem na F5.
<a href="latest.json">latest.json</a></p>
<div class=wrap><table><thead><tr><th>Ano</th>{head}</tr><tr>{sub}</tr></thead>
<tbody>{"".join(rows)}</tbody></table></div>
<h2>Fontes</h2><ul>{sources}</ul>
<h2>Alertas</h2><ul>{alerts}</ul>
</body></html>
"""


def build(out: Path, data: Path = DATA_DIR) -> Path:
    latest = json.loads((data / "latest.json").read_text(encoding="utf-8"))
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render(latest), encoding="utf-8")
    shutil.copyfile(data / "latest.json", out / "latest.json")
    return out / "index.html"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m curvas.site.build")
    parser.add_argument("--out", type=Path, default=ROOT / "site")
    args = parser.parse_args(argv)
    print(f"ok: {build(args.out)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
