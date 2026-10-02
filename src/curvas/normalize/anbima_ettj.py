"""ETTJ da ANBIMA (download CSV de ``est-termo/CZ-down.asp``) → dados tipados.

O CSV (latin-1, ``;``, vírgula decimal, ponto de milhar) tem quatro seções:

1. parâmetros de Svensson (PREFIXADOS e IPCA), na linha que começa com a data;
2. ``ETTJ Inflação Implicita (IPCA)``: vértices com ETTJ IPCA (real), ETTJ PREF
   e Inflação Implícita (as duas últimas só até onde há títulos prefixados);
3. ``PREFIXADOS (CIRCULAR 3.361)``: curva prefixada em vértices curtos (21 a 2520);
4. ``Erro Título a Título``.

Reconciliação com a planilha (F3, Q8, Q14; ``docs/F3_RECONCILIACAO_ANBIMA.md``): a
curva de inflação digitada é a coluna "Inflação Implícita" de **29/09/2026**, com o
vértice 126 preenchido pelo valor do 252 e o 2646 pelo do 2520 (a ANBIMA não publica
nenhum dos dois); a de DI é o vértice 126 da Circular 3.361 mais a "ETTJ PREF" do
mesmo dia, **deslocada um vértice a partir do 378** (erro de colagem, E6.12).
"""

from dataclasses import dataclass
from datetime import date, datetime

from curvas.engine.curves import VertexCurve


class NotPublishedError(LookupError):
    """Resposta vazia: dia não útil ou publicação ainda não disponível."""


class AnbimaFormatError(ValueError):
    """O arquivo não tem o layout esperado."""


@dataclass(frozen=True)
class Svensson:
    beta1: float
    beta2: float
    beta3: float
    beta4: float
    lambda1: float
    lambda2: float


@dataclass(frozen=True)
class EttjRow:
    days: int
    real_pct: float | None  # ETTJ IPCA
    pre_pct: float | None  # ETTJ PREF
    implied_pct: float | None  # Inflação Implícita


@dataclass(frozen=True)
class AnbimaEttj:
    reference_date: date
    svensson_pre: Svensson
    svensson_ipca: Svensson
    rows: tuple[EttjRow, ...]
    pre_circular_3361: tuple[tuple[int, float], ...]  # (dias úteis, % a.a.)

    def _column(self, attr: str) -> tuple[tuple[int, float], ...]:
        out = []
        for r in self.rows:
            value = getattr(r, attr)
            if value is not None:
                out.append((r.days, value))
        return tuple(out)

    def implied_inflation(self) -> tuple[tuple[int, float], ...]:
        return self._column("implied_pct")

    def pre(self) -> tuple[tuple[int, float], ...]:
        return self._column("pre_pct")

    def real(self) -> tuple[tuple[int, float], ...]:
        return self._column("real_pct")


def _num(text: str) -> float:
    return float(text.strip().replace(".", "").replace(",", "."))


def _int(text: str) -> int:
    value = _num(text)
    if value != int(value):
        raise AnbimaFormatError(f"prazo não inteiro: {text!r}")
    return int(value)


def _opt(text: str) -> float | None:
    return _num(text) if text.strip() else None


def _section_title(line: str) -> str | None:
    up = line.upper()
    if up.startswith("ETTJ INFLA"):
        return "ettj"
    if up.startswith("PREFIXADOS (CIRCULAR 3.361)"):
        return "circular"
    if up.startswith("ERRO T"):
        return "erro"
    return None


def _sections(payload: bytes) -> dict[str, list[str]]:
    """Separa as seções pelos títulos, não por linhas em branco: uma linha em branco a
    mais não pode cortar uma tabela em silêncio. Título repetido ou faltando é erro."""
    text = payload.decode("latin-1").lstrip("\ufeff\xef\xbb\xbf")
    sections: dict[str, list[str]] = {"cabecalho": []}
    current = "cabecalho"
    for ln in (ln.strip() for ln in text.splitlines()):
        if not ln:
            continue
        title = _section_title(ln)
        if title is None:
            sections[current].append(ln)
            continue
        if title in sections:
            raise AnbimaFormatError(f"seção repetida: {ln!r}")
        current = title
        sections[current] = []
    missing = {"ettj", "circular", "erro"} - set(sections)
    if missing:
        raise AnbimaFormatError(f"seções ausentes: {sorted(missing)}")
    return sections


def _header(head: list[str]) -> tuple[date, dict[str, Svensson]]:
    if not head:
        raise AnbimaFormatError("cabeçalho ausente")
    try:
        ref = datetime.strptime(head[0].split(";")[0], "%d/%m/%Y").date()
    except ValueError as exc:
        raise AnbimaFormatError(f"cabeçalho inesperado: {head[0]!r}") from exc
    params: dict[str, Svensson] = {}
    for ln in head[1:]:
        name, *vals = ln.split(";")
        if len(vals) != 6:
            raise AnbimaFormatError(f"parâmetros de Svensson inválidos: {ln!r}")
        params[name.strip().upper()] = Svensson(*(_num(v) for v in vals))
    if set(params) != {"PREFIXADOS", "IPCA"}:
        raise AnbimaFormatError(f"parâmetros esperados PREFIXADOS e IPCA, veio {sorted(params)}")
    return ref, params


def _table(lines: list[str], header_prefix: str, what: str) -> list[list[str]]:
    if not lines or not lines[0].upper().startswith(header_prefix):
        raise AnbimaFormatError(f"cabeçalho da {what} inesperado: {lines[:1]!r}")
    return [ln.split(";") for ln in lines[1:]]


def parse_anbima_ettj(payload: bytes) -> AnbimaEttj:
    """Lê o CSV. Resposta vazia levanta :class:`NotPublishedError`."""
    if not payload.strip():
        raise NotPublishedError("resposta vazia da ANBIMA")
    sections = _sections(payload)
    ref, params = _header(sections["cabecalho"])
    ettj = _table(sections["ettj"], "VERTICES;ETTJ IPCA;ETTJ PREF;INFLA", "ETTJ")
    circ = _table(sections["circular"], "VERTICES;TAXA", "Circular 3.361")
    if any(len(c) > 4 for c in ettj) or any(len(c) != 2 for c in circ):
        raise AnbimaFormatError("linha com número de colunas inesperado")
    try:
        rows = [
            EttjRow(_int(c[0]), _opt(c[1]), _opt(c[2]), _opt(c[3]))
            for c in ([*c, "", "", ""][:4] for c in ettj)
        ]
        circular = tuple((_int(d), _num(v)) for d, v in circ)
    except ValueError as exc:  # número ilegível
        raise AnbimaFormatError(f"número inválido no arquivo da ANBIMA: {exc}") from exc
    return AnbimaEttj(
        reference_date=ref,
        svensson_pre=params["PREFIXADOS"],
        svensson_ipca=params["IPCA"],
        rows=tuple(rows),
        pre_circular_3361=circular,
    )


def _curve(points: tuple[tuple[int, float], ...]) -> VertexCurve:
    return VertexCurve(tuple(d for d, _ in points), tuple(v / 100 for _, v in points))


def corrected_curves(ettj: AnbimaEttj) -> tuple[VertexCurve, VertexCurve]:
    """Curvas (DI, inflação) para o CORRIGIDO: só vértices publicados (provisório, Q14).

    DI = "ETTJ PREF" + vértices da Circular 3.361 abaixo do 1º vértice da ETTJ.
    Inflação = "Inflação Implícita" como publicada (sem preencher 126 nem 2646).
    """
    pre = dict(ettj.pre())
    first = min(pre)
    for days, rate in ettj.pre_circular_3361:
        if days < first:
            pre[days] = rate
    return _curve(tuple(sorted(pre.items()))), _curve(ettj.implied_inflation())


def legacy_curves_pct(ettj: AnbimaEttj) -> tuple[tuple[float, ...], tuple[float, ...]]:
    """Curvas (DI, inflação) em %, nos 19 vértices da planilha (126…2394), como o operador
    preenche hoje (provisório, Q14): inflação 126 := 252; DI 126 := Circular 3.361.
    """
    implied = dict(ettj.implied_inflation())
    pre = dict(ettj.pre())
    circ = dict(ettj.pre_circular_3361)
    days = [126 * k for k in range(1, 20)]
    try:
        inflation = tuple(implied[252] if d == 126 else implied[d] for d in days)
        di = tuple(circ[126] if d == 126 else pre[d] for d in days)
    except KeyError as exc:
        raise AnbimaFormatError(f"vértice {exc} ausente para montar o LEGADO") from exc
    return di, inflation
