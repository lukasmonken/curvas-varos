"""Reconciliação da planilha com a ETTJ da ANBIMA (F3, Q1/Q8/Q14).

Prova, com respostas gravadas da ANBIMA, de onde vêm as curvas digitadas:

- inflação = coluna "Inflação Implícita" de 29/09/2026, com o vértice 126
  preenchido pelo 252 e o 2646 pelo 2520 (a ANBIMA não publica nenhum dos dois);
- DI = vértice 126 da tabela "PREFIXADOS (CIRCULAR 3.361)" + "ETTJ PREF" de
  29/09/2026, **deslocada um vértice a partir do 378** (erro de colagem: no "378"
  está o 504, no "504" o 630, …, no "2394" o 2520; o 378 ficou de fora).
"""

import json

from conftest import LEGACY, ROOT
from curvas.normalize.anbima_ettj import legacy_curves_pct, parse_anbima_ettj

ANBIMA = ROOT / "tests" / "fixtures" / "f3" / "anbima"


def _planilha() -> dict[str, list[float]]:
    data: dict[str, list[float]] = json.loads(
        (LEGACY / "inputs_planilha.json").read_text(encoding="utf-8")
    )
    return data


def test_inflacao_da_planilha_e_a_anbima_de_29_09() -> None:
    ettj = parse_anbima_ettj((ANBIMA / "cz_2026-09-29.csv").read_bytes())
    _, inflation = legacy_curves_pct(ettj)
    planilha = _planilha()
    assert list(inflation) == planilha["inflation_curve_pct"]  # 126 … 2394
    implied = dict(ettj.implied_inflation())
    assert planilha["inflation_curve_pct_full"][19:] == [implied[2520], implied[2520]]


def test_di_da_planilha_e_a_anbima_de_29_09_deslocada() -> None:
    ettj = parse_anbima_ettj((ANBIMA / "cz_2026-09-29.csv").read_bytes())
    pre, circ = dict(ettj.pre()), dict(ettj.pre_circular_3361)
    shifted = [circ[126], pre[252]] + [pre[d + 126] for d in range(378, 2395, 126)]
    assert _planilha()["di_curve_pct"] == shifted
    # O valor certo do 378 não aparece na planilha.
    assert pre[378] not in _planilha()["di_curve_pct"]


def test_nenhum_outro_dia_bate() -> None:
    planilha = _planilha()["inflation_curve_pct"]
    for f in sorted(ANBIMA.glob("cz_*.csv")):
        _, inflation = legacy_curves_pct(parse_anbima_ettj(f.read_bytes()))
        assert (list(inflation) == planilha) == (f.stem == "cz_2026-09-29")
