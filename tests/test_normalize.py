"""Parsers de respostas gravadas (sem rede)."""

import json
from datetime import date

import pytest

from conftest import ROOT
from curvas.normalize.bcb_sgs import monthly_by_reference, parse_sgs
from curvas.normalize.ibge import IPCA15_TITLE, parse_ipca_releases

F2 = ROOT / "tests" / "fixtures" / "f2"


def test_sgs_cdi() -> None:
    rows = parse_sgs((F2 / "bcb_sgs_12_cdi_diario.json").read_bytes())
    assert rows[0] == (date(2026, 1, 2), 0.055131)
    assert len(rows) == 170


def test_sgs_ipca_mensal() -> None:
    monthly = monthly_by_reference(parse_sgs((F2 / "bcb_sgs_433_ipca_mensal.json").read_bytes()))
    assert monthly[(2026, 4)] == 0.67  # a planilha tem 0,43 (abril de 2025)
    assert monthly[(2026, 8)] == -0.32


def test_sgs_erros() -> None:
    dup = json.dumps([{"data": "02/01/2026", "valor": "1"}] * 2)
    with pytest.raises(ValueError, match="repetidas"):
        parse_sgs(dup)
    with pytest.raises(ValueError, match="lista"):
        parse_sgs('{"erro": 1}')
    with pytest.raises(ValueError, match="dia 1"):
        monthly_by_reference([(date(2026, 1, 2), 0.1)])


def test_ibge_so_ipca_cheio() -> None:
    releases = parse_ipca_releases((F2 / "ibge_calendario_2026.json").read_bytes())
    assert len(releases) == 12
    by_ref = {(r.ref_year, r.ref_month): r.release_date for r in releases}
    assert by_ref[(2026, 7)] == date(2026, 8, 11)
    assert by_ref[(2026, 8)] == date(2026, 9, 11)
    assert by_ref[(2025, 12)] == date(2026, 1, 9)


def test_ibge_ipca15() -> None:
    rel = parse_ipca_releases((F2 / "ibge_calendario_2026.json").read_bytes(), IPCA15_TITLE)
    by_ref = {(r.ref_year, r.ref_month): r.release_date for r in rel}
    assert by_ref[(2026, 8)] == date(2026, 8, 26)
    assert by_ref[(2026, 9)] == date(2026, 9, 25)


def test_sgs_ipca15() -> None:
    monthly = monthly_by_reference(parse_sgs((F2 / "bcb_sgs_7478_ipca15_mensal.json").read_bytes()))
    assert monthly[(2026, 8)] == -0.40
    assert monthly[(2026, 9)] == 0.70
