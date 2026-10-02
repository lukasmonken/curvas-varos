"""``docs/ESPECIFICACAO.md`` em HTML para a página de metodologia.

markdown-it (CommonMark + tabelas), sem HTML cru. Sai o título do arquivo e os demais
títulos descem um nível (a página já tem os seus), com âncoras estáveis e índice das
seções E1…E11.

Chave Q17: com ``show_cds=False``, os números de CDS da planilha que a especificação
cita saem antes da renderização (colunas e linhas de tabela de CDS; números com vírgula
decimal nas frases sobre CDS).
"""

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from markdown_it import MarkdownIt

DECIMAL = re.compile(r"−?\d+(?:,\d+)+\s?%?")
HIDDEN = "[oculto]"


@dataclass(frozen=True)
class Heading:
    anchor: str
    text: str


@dataclass(frozen=True)
class SpecDoc:
    html: str
    toc: tuple[Heading, ...]


def _cells(line: str) -> list[str]:
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _row(cells: list[str]) -> str:
    return "| " + " | ".join(cells) + " |"


def _is_cds(cell: str) -> bool:
    plain = cell.replace("*", "").strip()
    return "CDS" in plain or plain == "bps"


def _filter_table(lines: list[str]) -> list[str]:
    """Tira as colunas com cabeçalho de CDS e as linhas de CDS que tenham números."""
    rows = [_cells(line) for line in lines]
    header, body = rows[0], rows[2:]
    drop = {
        i
        for i, h in enumerate(header)
        if i > 0 and _is_cds(h) and any(i < len(r) and DECIMAL.search(r[i]) for r in body)
    }
    kept = [r for r in body if not (r and _is_cds(r[0]) and any(DECIMAL.search(c) for c in r[1:]))]
    out = [header, rows[1], *kept]
    return [_row([c for i, c in enumerate(r) if i not in drop]) for r in out]


def hide_cds(text: str) -> str:
    """Remove da especificação os valores de CDS (Q17)."""
    lines = text.splitlines()
    out: list[str] = []
    fenced = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith("```"):
            fenced = not fenced
        is_table = (
            not fenced
            and line.startswith("|")
            and i + 1 < len(lines)
            and re.match(r"^\|[\s:|-]+\|$", lines[i + 1].strip()) is not None
        )
        if is_table:
            j = i
            while j < len(lines) and lines[j].startswith("|"):
                j += 1
            out.extend(_filter_table(lines[i:j]))
            i = j
            continue
        if not fenced and "CDS" in line:
            line = DECIMAL.sub(HIDDEN, line)
        out.append(line)
        i += 1
    return "\n".join(out) + "\n"


def _slug(text: str, seen: set[str]) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-") or "secao"
    slug, n = base, 2
    while slug in seen:
        slug, n = f"{base}-{n}", n + 1
    seen.add(slug)
    return slug


def render_spec(path: Path, show_cds: bool) -> SpecDoc:
    text = path.read_text(encoding="utf-8")
    if not show_cds:
        text = hide_cds(text)
    md = MarkdownIt("commonmark", {"html": False}).enable("table")
    tokens = md.parse(text)
    if tokens and tokens[0].type == "heading_open" and tokens[0].tag == "h1":
        tokens = tokens[3:]  # o título do arquivo: a página já tem o seu
    seen: set[str] = set()
    toc: list[Heading] = []
    for i, tok in enumerate(tokens):
        if tok.type not in ("heading_open", "heading_close"):
            continue
        level = int(tok.tag[1])
        tok.tag = f"h{min(level + 1, 6)}"
        if tok.type == "heading_open":
            title = tokens[i + 1].content
            anchor = "esp-" + _slug(title, seen)
            tok.attrSet("id", anchor)
            if level == 2:
                toc.append(Heading(anchor, title))
    html = _wrap_tables(md.renderer.render(tokens, md.options, {}))
    return SpecDoc(html, tuple(toc))


def _wrap_tables(html: str) -> str:
    """Cada tabela num contêiner rolável que recebe foco de teclado, rotulado pelo título
    da seção em que está (a tabela larga rola na horizontal no celular)."""
    out: list[str] = []
    last, heading = 0, None
    for m in re.finditer(r'id="(esp-[^"]+)"|<table>', html):
        if m.group(1) is not None:
            heading = m.group(1)
            continue
        label = f'aria-labelledby="{heading}"' if heading else 'aria-label="Tabela"'
        wrap = f'<div class="table-wrap" tabindex="0" role="region" {label}><table>'
        out += [html[last : m.start()], wrap]
        last = m.end()
    out.append(html[last:])
    return "".join(out).replace("</table>", "</table></div>")
