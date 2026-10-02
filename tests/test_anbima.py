"""Parser e validação da ETTJ da ANBIMA (respostas gravadas)."""

import dataclasses
from datetime import date
from pathlib import Path

import pytest

from conftest import ROOT
from curvas.normalize.anbima_ettj import (
    AnbimaFormatError,
    corrected_curves,
    legacy_curves_pct,
    parse_anbima_ettj,
)
from curvas.validate.checks import ValidationError, validate_anbima

ANBIMA = ROOT / "tests" / "fixtures" / "f3" / "anbima"
FILES = sorted(ANBIMA.glob("cz_*.csv"))


@pytest.mark.parametrize("path", FILES, ids=lambda p: p.stem)
def test_todos_os_dias_gravados(path: Path) -> None:
    ettj = parse_anbima_ettj(path.read_bytes())
    assert ettj.reference_date == date.fromisoformat(path.stem[3:])
    validate_anbima(ettj, ettj.reference_date)
    assert [d for d, _ in ettj.implied_inflation()] == list(range(252, 2521, 126))
    assert [d for d, _ in ettj.pre()] == list(range(252, 2521, 126))
    assert [d for d, _ in ettj.pre_circular_3361][:4] == [21, 42, 63, 126]
    assert len(ettj.real()) > len(ettj.pre())  # a curva real vai até ~8.000 d.u.


def test_valores_de_29_09() -> None:
    ettj = parse_anbima_ettj((ANBIMA / "cz_2026-09-29.csv").read_bytes())
    pre, implied = dict(ettj.pre()), dict(ettj.implied_inflation())
    assert pre[252] == 13.4448
    assert pre[378] == 13.6052
    assert implied[252] == 6.4827
    assert dict(ettj.pre_circular_3361)[126] == 13.3269
    assert ettj.svensson_pre.lambda1 > 0


def test_curvas_do_corrigido_so_com_vertices_publicados() -> None:
    di, inflation = corrected_curves(parse_anbima_ettj((ANBIMA / "cz_2026-09-29.csv").read_bytes()))
    assert di.days[:5] == (21, 42, 63, 126, 252)
    assert di.days[-1] == 2520
    assert inflation.days == tuple(range(252, 2521, 126))
    assert inflation.rates[0] == pytest.approx(0.064827)


def test_curvas_do_legado_como_o_operador() -> None:
    ettj = parse_anbima_ettj((ANBIMA / "cz_2026-09-29.csv").read_bytes())
    di, inflation = legacy_curves_pct(ettj)
    assert len(di) == len(inflation) == 19
    assert inflation[0] == inflation[1] == 6.4827  # 126 := 252
    assert di[0] == 13.3269  # Circular 3.361
    assert di[2] == 13.6052  # 378 alinhado (a planilha tem o 504 aqui: Q14)


GOOD = (ANBIMA / "cz_2026-09-29.csv").read_bytes()


def test_formato_inesperado() -> None:
    with pytest.raises(AnbimaFormatError, match="ausentes"):
        parse_anbima_ettj(b"<html>erro</html>")
    broken = GOOD.replace(b"PREFIXADOS (CIRCULAR 3.361)", b"OUTRA COISA")
    with pytest.raises(AnbimaFormatError, match="ausentes"):
        parse_anbima_ettj(broken)
    with pytest.raises(AnbimaFormatError, match="colunas"):
        parse_anbima_ettj(GOOD.replace(b"1.638;", b"1.638;9;"))
    with pytest.raises(AnbimaFormatError, match="número inválido"):
        parse_anbima_ettj(GOOD.replace(b"1.638;", b"1.6x8;"))


def test_linha_em_branco_a_mais_nao_corta_a_tabela() -> None:
    """Revisão da F3: antes, uma linha em branco no meio truncava a ETTJ em silêncio."""
    spaced = GOOD.replace(b"\r\n1.638;", b"\r\n\r\n1.638;")
    assert spaced != GOOD
    assert parse_anbima_ettj(spaced) == parse_anbima_ettj(GOOD)
    with_bom = b"\xef\xbb\xbf" + GOOD
    assert parse_anbima_ettj(with_bom) == parse_anbima_ettj(GOOD)


def test_validacao_da_grade_e_da_circular() -> None:
    ettj = parse_anbima_ettj(GOOD)
    sem_1638 = tuple(r for r in ettj.rows if r.days != 1638)
    with pytest.raises(ValidationError, match="grade"):
        validate_anbima(dataclasses.replace(ettj, rows=sem_1638), ettj.reference_date)
    circ = list(ettj.pre_circular_3361)
    circ[4] = (252, circ[4][1] + 0.01)
    with pytest.raises(ValidationError, match="Circular"):
        validate_anbima(
            dataclasses.replace(ettj, pre_circular_3361=tuple(circ)), ettj.reference_date
        )


def test_validacao() -> None:
    ettj = parse_anbima_ettj((ANBIMA / "cz_2026-09-29.csv").read_bytes())
    with pytest.raises(ValidationError, match="pedido"):
        validate_anbima(ettj, date(2026, 9, 30))
    rows = list(ettj.rows)
    rows[0] = dataclasses.replace(rows[0], implied_pct=9.0)  # quebra Fisher no 252
    with pytest.raises(ValidationError, match="Fisher"):
        validate_anbima(dataclasses.replace(ettj, rows=tuple(rows)), ettj.reference_date)
    rows = list(ettj.rows)
    rows[0] = dataclasses.replace(rows[0], pre_pct=99.0)
    with pytest.raises(ValidationError, match="PREF"):
        validate_anbima(dataclasses.replace(ettj, rows=tuple(rows)), ettj.reference_date)
    with pytest.raises(ValidationError, match="vértices"):
        validate_anbima(dataclasses.replace(ettj, rows=ettj.rows[:5]), ettj.reference_date)
