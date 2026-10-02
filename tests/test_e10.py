"""Casos de teste de E10 (docs/ESPECIFICACAO.md), tolerância 1e-8.

Valores transcritos da especificação. Pela regra de desempate (3.3) o recálculo
prevalece; a F0 confirmou que nenhum caso de E10 diverge dele em mais de 5e-11.
"""

import pytest

from conftest import TOL_LEGACY
from curvas.engine.curves import grid_value
from curvas.engine.legacy import LegacyInputs, LegacyResult, compute_legacy


@pytest.fixture(scope="module")
def res(planilha_inputs: LegacyInputs) -> LegacyResult:
    return compute_legacy(planilha_inputs)


PONTOS = [
    ("DI", "taxa", 127, 0.1332783571),
    ("DI", "acum", 1, 0.01210233742),
    ("DI", "acum", 127, 0.07743467076),
    ("DI", "acum", 231, 0.1347318473),
    ("DI", "acum", 504, 0.3039766),
    ("Inflação", "taxa", 253, 0.06479265079),
    ("Inflação", "acum", 1, 0.003550109048),
    ("Inflação", "acum", 231, 0.06276345587),
    ("Inflação", "acum", 253, 0.06860711517),
    ("Inflação", "acum", 504, 0.1337749986),
    ("CDS", "taxa", 127, 0.004573888889),
    ("CDS", "acum", 62, 0.0011216976),
    ("CDS", "acum", 127, 0.00229904919),
]


@pytest.mark.parametrize(("aba", "serie", "dia", "esperado"), PONTOS)
def test_pontos_diarios(res: LegacyResult, aba: str, serie: str, dia: int, esperado: float) -> None:
    sheet = {"DI": res.di, "Inflação": res.inflation, "CDS": res.cds}[aba]
    grid = sheet.daily_rate if serie == "taxa" else sheet.accumulated
    assert grid_value(grid, dia) == pytest.approx(esperado, abs=TOL_LEGACY)


ANUAIS = {
    # ano: (DI, Inflação, CDS)
    2026: (0.1347318473, 0.06276345587, 0.004567),
    2027: (0.1367704582, 0.06170699177, 0.005040834358),
    2028: (0.1397224171, 0.05921274213, 0.006465717867),
    2029: (0.1411788478, 0.05975990725, 0.008248988388),
    2030: (0.1419084912, 0.06048500357, 0.0104101213),
    2031: (0.1421659309, 0.06101641848, 0.01254379297),
    2032: (0.1421324179, 0.06138540302, 0.01460425996),
    2033: (0.1419262871, 0.06165391388, 0.01663378424),
    2034: (0.1416246573, 0.06186391725, 0.01820592628),
    2035: (0.1413084536, 0.0620259023, 0.01958959306),
    2036: (0.141248, 0.062054, 0.0209406778),
}


@pytest.mark.parametrize("ano", sorted(ANUAIS))
def test_linhas_anuais_do_dashboard(res: LegacyResult, ano: int) -> None:
    i = res.dashboard.years.index(ano)
    di, inflacao, cds = ANUAIS[ano]
    assert res.dashboard.di[i] == pytest.approx(di, abs=TOL_LEGACY)
    assert res.dashboard.inflation[i] == pytest.approx(inflacao, abs=TOL_LEGACY)
    assert res.dashboard.cds[i] == pytest.approx(cds, abs=TOL_LEGACY)


def test_ytg_2026(res: LegacyResult) -> None:
    """Linha "YTG 2026" do Dashboard (E3.3)."""
    assert res.dashboard.di_ytg == pytest.approx(0.1347318473, abs=TOL_LEGACY)
    assert res.dashboard.inflation_ytg == pytest.approx(0.06276345587, abs=TOL_LEGACY)
    assert res.dashboard.cds_ytg == pytest.approx(0.0011216976, abs=TOL_LEGACY)


TRIMESTRAIS = [
    # (trimestre, IPCA, Selic)
    (1, 0.01921394328, 0.0340787636),
    (2, 0.0117411399, 0.03315985626),
    (3, 0.002285749248, 0.03438621948),
    (4, 0.006010535346, 0.03592029968),
]


@pytest.mark.parametrize(("tri", "ipca", "selic"), TRIMESTRAIS)
def test_acumulados_trimestrais(res: LegacyResult, tri: int, ipca: float, selic: float) -> None:
    assert res.inflation.quarterly[tri - 1] == pytest.approx(ipca, abs=TOL_LEGACY)
    assert res.di.quarterly[tri - 1] == pytest.approx(selic, abs=TOL_LEGACY)
