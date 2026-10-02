"""Uso (a) do LEGADO: reprodução da planilha recalculada (Parte 1, seções 8 e 10)."""

import math
from typing import Any

import pytest

from conftest import TOL_LEGACY, XLSX, assert_cells, load_json, sha256
from curvas.engine.legacy import (
    LegacyInputs,
    LegacyResult,
    RateSheetResult,
    SheetParams,
    compute_legacy,
    month_number,
    quarter_number,
    quarterly_accumulated,
    usage_matrix,
    ytg_days,
)

# Regressão fina contra a fixture. A reprodução atual é exata (diferença 0,0); a
# ordem das operações é protegida pelos testes de igualdade exata mais abaixo.
TOL_FINA = 1e-12


@pytest.fixture(scope="module")
def resultado(planilha_inputs: LegacyInputs) -> LegacyResult:
    return compute_legacy(planilha_inputs)


def _check_rate_sheet(got: RateSheetResult, exp: dict[str, Any], tol: float, aba: str) -> None:
    assert got.ytg_days == exp["R26"]
    assert list(got.cuts[1:]) == exp["R28:R37"]
    assert_cells(got.usage_current, exp["T11:T22"], tol, f"{aba}!T11:T22")
    assert_cells(got.usage_previous, exp["U11:U22"], tol, f"{aba}!U11:U22")
    assert_cells(got.quarterly, exp["S3:S6"], tol, f"{aba}!S3:S6")
    assert_cells([got.ytg_accumulated], [exp["S26"]], tol, f"{aba}!S26")
    assert_cells([got.calendar_year1], [exp["S27"]], tol, f"{aba}!S27")
    assert_cells([got.calendar_year1], [exp["H6"]], tol, f"{aba}!H6")
    assert_cells(got.forwards, exp["S28:S37"], tol, f"{aba}!S28:S37")
    assert_cells(got.headline, exp["E4:O4"], tol, f"{aba}!E4:O4")
    assert_cells([got.accumulated[0]], [exp["Y3"]], tol, f"{aba}!Y3")


def _check_cds(res: LegacyResult, exp: dict[str, Any], tol: float) -> None:
    got = res.cds
    assert_cells(got.vertex_rates, exp["F8:F16"], tol, "CDS!F8:F16")
    assert list(got.cuts) == exp["I9:I19"]
    assert_cells([got.ytg_accumulated, *got.forwards], exp["J9:J19"], tol, "CDS!J9:J19")
    assert_cells(got.headline, exp["E4:O4"], tol, "CDS!E4:O4")


def _check_dashboard(res: LegacyResult, exp: dict[str, Any], tol: float) -> None:
    dash = res.dashboard
    assert list(dash.years) == [int(y) for y in exp["F3:P3"]]
    assert_cells(dash.di, exp["F4:P4"], tol, "Dashboard!F4:P4")
    assert_cells(dash.cds, exp["F5:P5"], tol, "Dashboard!F5:P5")
    assert_cells(dash.inflation, exp["F6:P6"], tol, "Dashboard!F6:P6")
    assert_cells([dash.di_ytg], [exp["Q4"]], tol, "Dashboard!Q4")
    assert_cells([dash.cds_ytg], [exp["Q5"]], tol, "Dashboard!Q5")
    assert_cells([dash.inflation_ytg], [exp["Q6"]], tol, "Dashboard!Q6")


@pytest.mark.skipif(not XLSX.exists(), reason="planilha fora do repositório (confidencial)")
def test_fixtures_vem_da_planilha_atual() -> None:
    """Se a planilha mudar sem regenerar as fixtures, a suíte acusa."""
    hashes = {
        load_json(name)["_meta"]["fonte_sha256"]
        for name in ("inputs_planilha.json", "esperado_planilha.json", "esperado_cenarios.json")
    }
    assert hashes == {sha256(XLSX)}


class TestPlanilhaOriginal:
    """Inputs e parâmetros exatamente como estão na planilha."""

    @pytest.mark.parametrize("tol", [TOL_LEGACY, TOL_FINA], ids=["oficial", "fina"])
    def test_dashboard_completo(
        self, resultado: LegacyResult, esperado_planilha: dict[str, Any], tol: float
    ) -> None:
        _check_dashboard(resultado, esperado_planilha["Dashboard"], tol)

    @pytest.mark.parametrize("aba", ["Inflação", "DI"])
    @pytest.mark.parametrize("tol", [TOL_LEGACY, TOL_FINA], ids=["oficial", "fina"])
    def test_abas_de_taxa(
        self,
        resultado: LegacyResult,
        esperado_planilha: dict[str, Any],
        aba: str,
        tol: float,
    ) -> None:
        got = resultado.inflation if aba == "Inflação" else resultado.di
        exp = esperado_planilha[aba]
        _check_rate_sheet(got, exp, tol, aba)
        assert_cells(got.daily_rate, exp["X3:X"], tol, f"{aba}!X")
        assert_cells(got.accumulated, exp["Y3:Y"], tol, f"{aba}!Y")

    @pytest.mark.parametrize("tol", [TOL_LEGACY, TOL_FINA], ids=["oficial", "fina"])
    def test_aba_cds(
        self, resultado: LegacyResult, esperado_planilha: dict[str, Any], tol: float
    ) -> None:
        _check_cds(resultado, esperado_planilha["CDS"], tol)
        assert_cells(resultado.cds.daily_rate, esperado_planilha["CDS"]["M8:M"], tol, "CDS!M")
        assert_cells(resultado.cds.accumulated, esperado_planilha["CDS"]["N8:N"], tol, "CDS!N")

    def test_tamanho_das_grades(self, resultado: LegacyResult) -> None:
        assert len(resultado.di.daily_rate) == 2998  # DI!W3:W3000
        assert len(resultado.inflation.daily_rate) == 3000  # Inflação!W3:W3002
        assert len(resultado.cds.daily_rate) == 5040  # CDS!L8:L5047

    def test_sanidade(self, resultado: LegacyResult) -> None:
        """Seção 10.5: sem NaN, fatores positivos e todas as saídas numéricas."""
        for grid in (
            resultado.inflation.daily_rate,
            resultado.inflation.accumulated,
            resultado.di.daily_rate,
            resultado.di.accumulated,
            resultado.cds.daily_rate,
            resultado.cds.accumulated,
        ):
            assert all(math.isfinite(x) for x in grid)
        for acc in (resultado.inflation, resultado.di, resultado.cds):
            assert all(1 + a > 0 for a in acc.accumulated)
        dash = resultado.dashboard
        for row in (dash.di, dash.cds, dash.inflation):
            assert all(v is not None and math.isfinite(v) for v in row)


class TestOrdemDasOperacoes:
    """Seção 8: a ordem das operações é a mesma da planilha.

    As grades de taxa usam só soma e divisão IEEE, que são determinísticas em
    qualquer plataforma; por isso a comparação com a fixture é exata. As
    acumulações usam ``pow``, que pode variar 1 ULP entre bibliotecas; nelas a
    ordem é conferida contra a fórmula literal da célula, na mesma plataforma.
    """

    def test_grades_de_taxa_exatas(
        self, resultado: LegacyResult, esperado_planilha: dict[str, Any]
    ) -> None:
        # Soma incremental X129 = X128+($C$8-$C$7)/126, não a fórmula fechada.
        assert list(resultado.inflation.daily_rate) == esperado_planilha["Inflação"]["X3:X"]
        assert list(resultado.di.daily_rate) == esperado_planilha["DI"]["X3:X"]
        assert list(resultado.cds.daily_rate) == esperado_planilha["CDS"]["M8:M"]

    @pytest.mark.parametrize("aba", ["Inflação", "DI", "CDS"])
    def test_recursao_literal(self, resultado: LegacyResult, aba: str) -> None:
        sheet = {"Inflação": resultado.inflation, "DI": resultado.di, "CDS": resultado.cds}[aba]
        x = sheet.daily_rate
        f0 = 1.0
        if aba != "CDS":
            assert isinstance(sheet, RateSheetResult)
            for t in sheet.usage_current:  # PRODUCT(1+T11:T22), da esquerda para a direita
                f0 *= 1 + t
        # Y3 = (PRODUCT(1+T11:T22)*(1+X3)^(1/252))-1 ; Y4 = (1+Y3)*(1+X4)^(1/252) - 1
        y = [f0 * math.pow(1 + x[0], 1 / 252) - 1]
        for d in range(1, len(x)):
            y.append((1 + y[d - 1]) * math.pow(1 + x[d], 1 / 252) - 1)
        assert list(sheet.accumulated) == y

    def test_forwards_literais(self, resultado: LegacyResult) -> None:
        di = resultado.di
        y, r = di.accumulated, di.cuts
        # S28 = (1+VLOOKUP(R28,…))/(1+VLOOKUP(R26,…) )- 1
        expected = [(1 + y[r[i] - 1]) / (1 + y[r[i - 1] - 1]) - 1 for i in range(1, len(r))]
        assert list(di.forwards) == expected
        # S27 = (1+S26)*PRODUCT(1+U11:U22)-1
        s26 = y[r[0] - 1]
        u = 1.0
        for v in di.usage_previous:
            u *= 1 + v
        assert di.calendar_year1 == (1 + s26) * u - 1


CENARIOS = load_json("esperado_cenarios.json")["cenarios"]


def _overrides(cenario: dict[str, Any]) -> dict[str, Any]:
    keys = ("inflation_params", "di_params", "cds_ytg_days")
    return {k: cenario[k] for k in keys if k in cenario}


@pytest.mark.parametrize("cenario", CENARIOS, ids=lambda c: c["id"])
def test_cenarios_recalculados(cenario: dict[str, Any], make_inputs: Any) -> None:
    """Mês, trimestre e YTG alterados, inclusive os cenários com ``#N/A`` parcial."""
    res = compute_legacy(make_inputs(_overrides(cenario)))
    exp = cenario["esperado"]
    _check_rate_sheet(res.inflation, exp["Inflação"], TOL_LEGACY, "Inflação")
    _check_rate_sheet(res.di, exp["DI"], TOL_LEGACY, "DI")
    _check_cds(res, exp["CDS"], TOL_LEGACY)
    _check_dashboard(res, exp["Dashboard"], TOL_LEGACY)


def test_dezembro_na_e_local(make_inputs: Any) -> None:
    """Com Dezembro, o #N/A atinge só o que depende do corte 0 (como na planilha)."""
    res = compute_legacy(make_inputs({"inflation_params": ["Dezembro", "4º Tri"]}))
    dash = res.dashboard
    assert dash.inflation[:2] == (None, None)  # F6 = H6 = S27 ; G6 = F4 = S28
    assert all(v is not None for v in dash.inflation[2:])  # H6:P6
    assert dash.inflation_ytg is None  # Q6
    assert all(v is not None for v in (*dash.di, *dash.cds, dash.di_ytg, dash.cds_ytg))


def test_cds_2026_nao_e_o_primeiro_vertice(make_inputs: Any) -> None:
    """Divergência D3: CDS!E4 anualiza A(YTG); só coincide com o 1º vértice se YTG ≤ 126."""
    res = compute_legacy(make_inputs({"cds_ytg_days": 200}))
    first = res.dashboard.cds[0]
    assert first is not None
    assert abs(first - 45.67 / 10000) > 5e-6


def test_di_2026_e_anualizacao_e_nao_ano_civil(make_inputs: Any) -> None:
    """Divergência D2: com q = 3, o DI 2026 do Dashboard é DI!E4, não DI!S27."""
    res = compute_legacy(make_inputs({"di_params": ["Setembro", "3º Tri"]}))
    e4, s27 = res.di.headline[0], res.di.calendar_year1
    assert e4 is not None
    assert s27 is not None
    assert res.dashboard.di[0] == e4
    assert abs(e4 - s27) > 1e-3


class TestParametros:
    def test_rotulos(self) -> None:
        assert month_number("Janeiro") == 1
        assert month_number("dezembro") == 12  # VLOOKUP ignora maiúsculas/minúsculas
        assert quarter_number("3º Tri") == 3
        for bad in ("Jan", " Janeiro", "Janeiro "):  # …mas não espaços (#N/A)
            with pytest.raises(ValueError, match="mês"):
                month_number(bad)
        with pytest.raises(ValueError, match="trimestre"):
            quarter_number("3 Tri")

    @pytest.mark.parametrize(("month", "expected"), [(1, 231), (8, 84), (9, 63), (11, 21), (12, 0)])
    def test_ytg(self, month: int, expected: int) -> None:
        assert ytg_days(month) == expected

    def test_mes_zero_e_a_extensao_do_uso_b(self) -> None:
        assert ytg_days(0) == 252
        assert SheetParams(0, 1).month == 0
        with pytest.raises(ValueError, match="1º trimestre"):
            SheetParams(0, 2)

    @pytest.mark.parametrize("month", [-1, 13])
    def test_ytg_mes_invalido(self, month: int) -> None:
        with pytest.raises(ValueError, match="mês"):
            ytg_days(month)

    def test_params_invalidos(self) -> None:
        with pytest.raises(ValueError, match="mês"):
            SheetParams(13, 1)
        with pytest.raises(ValueError, match="trimestre"):
            SheetParams(1, 0)
        with pytest.raises(TypeError, match="quarter"):
            SheetParams(1, 2.5)  # type: ignore[arg-type]
        with pytest.raises(TypeError, match="month"):
            SheetParams(True, 1)

    def test_inputs_com_tamanho_errado(self, planilha_inputs: LegacyInputs) -> None:
        with pytest.raises(ValueError, match="vértices"):
            LegacyInputs(
                **{**planilha_inputs.__dict__, "di_curve_pct": planilha_inputs.di_curve_pct[:-1]}
            )

    @pytest.mark.parametrize("campo", ["di_curve_pct", "cds_bps", "ipca_monthly"])
    @pytest.mark.parametrize("valor", [math.nan, math.inf])
    def test_inputs_nao_finitos(
        self, planilha_inputs: LegacyInputs, campo: str, valor: float
    ) -> None:
        original = getattr(planilha_inputs, campo)
        with pytest.raises(ValueError, match="não finito"):
            LegacyInputs(**{**planilha_inputs.__dict__, campo: (valor, *original[1:])})

    def test_ytg_cds_inteiro(self, planilha_inputs: LegacyInputs) -> None:
        with pytest.raises(TypeError, match="cds_ytg_days"):
            LegacyInputs(**{**planilha_inputs.__dict__, "cds_ytg_days": 62.0})


@pytest.mark.parametrize("month", range(1, 13))
@pytest.mark.parametrize("quarter", range(1, 5))
def test_matriz_usar(month: int, quarter: int) -> None:
    """T = meses do trimestre q em diante até m; U = meses dos trimestres anteriores a q."""
    monthly = [0.001 * (i + 1) for i in range(12)]
    current, previous = usage_matrix(monthly, SheetParams(month, quarter))
    for i in range(12):
        q_i = i // 3 + 1
        assert current[i] == (monthly[i] if q_i >= quarter and i + 1 <= month else 0.0)
        assert previous[i] == (monthly[i] if q_i < quarter else 0.0)
    if quarter == (month - 1) // 3 + 1:
        # Parâmetros coerentes: T ∪ U cobre exatamente Jan…m, sem sobreposição.
        used = [i for i in range(12) if current[i] or previous[i]]
        assert used == list(range(month))


def test_trimestral_traco() -> None:
    """``S3 = IF(G11<>0, …, "-")``: só o último mês do trimestre decide o traço."""
    monthly = [0.01, 0.02, 0.0, 0.0, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01, 0.01]
    q = quarterly_accumulated(monthly)
    assert q[0] is None  # março = 0
    assert q[1] == pytest.approx(1.01 * 1.01 - 1, abs=1e-15)  # abril = 0 não importa
