"""Fixtures compartilhadas. Nenhum teste acessa rede, Excel ou LibreOffice."""

import hashlib
import json
import math
import os
from collections.abc import Callable, Sequence
from functools import cache
from pathlib import Path
from typing import Any

import pytest
from hypothesis import settings

from curvas.engine.legacy import LegacyInputs, SheetParams

# Na CI (variável CI definida), o hypothesis roda com exemplos derivados do código do
# teste: mesma entrada a cada execução, sem falha intermitente que bloqueie a publicação.
settings.register_profile("ci", derandomize=True, print_blob=True)
if os.environ.get("CI"):
    settings.load_profile("ci")

ROOT = Path(__file__).resolve().parent.parent
XLSX = ROOT / "docs" / "legado" / "Query-Avila.xlsx"
FIXTURES = Path(__file__).parent / "fixtures"
LEGACY = FIXTURES / "legacy"

# Tolerância oficial do uso (a) do LEGADO (Parte 1, seção 8 e 10).
TOL_LEGACY = 1e-8


@cache
def load_json(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((LEGACY / name).read_text(encoding="utf-8"))
    return data


def legacy_inputs(overrides: dict[str, Any] | None = None) -> LegacyInputs:
    """Inputs do uso (a): exatamente os da planilha, com overrides de cenário opcionais."""
    raw = {**load_json("inputs_planilha.json"), **(overrides or {})}
    return LegacyInputs(
        first_year=raw["first_year"],
        inflation_curve_pct=tuple(raw["inflation_curve_pct"]),
        di_curve_pct=tuple(raw["di_curve_pct"]),
        cds_bps=tuple(raw["cds_bps"]),
        ipca_monthly=tuple(raw["ipca_monthly"]),
        selic_monthly=tuple(raw["selic_monthly"]),
        inflation_params=SheetParams.from_labels(*raw["inflation_params"]),
        di_params=SheetParams.from_labels(*raw["di_params"]),
        cds_ytg_days=int(raw["cds_ytg_days"]),
    )


def is_na(expected: Any) -> bool:
    """Célula de erro ``#N/A`` gravada pelo gerador de fixtures."""
    return isinstance(expected, dict) and expected.get("erro") == "#N/A"


def assert_cells(
    actual: Sequence[float | None], expected: Sequence[Any], tol: float, label: str = ""
) -> None:
    """Compara célula a célula.

    - ``#N/A`` (e ``"-"`` em S3:S6) na fixture exige ``None`` no motor, e vice-versa;
    - valor numérico exige número finito com ``|a − e| ≤ tol`` (NaN sempre falha).
    """
    assert len(actual) == len(expected), f"{label}: tamanhos {len(actual)} × {len(expected)}"
    for i, (a, e) in enumerate(zip(actual, expected, strict=True)):
        where = f"{label}[{i}]"
        if is_na(e) or e == "-" or e is None:
            assert a is None, f"{where}: esperado #N/A, motor deu {a!r}"
            continue
        assert a is not None, f"{where}: motor deu #N/A, esperado {e!r}"
        assert math.isfinite(a), f"{where}: valor não finito {a!r}"
        assert abs(a - float(e)) <= tol, f"{where}: {a!r} × {e!r} (dif {abs(a - float(e)):.3e})"


@pytest.fixture(scope="session")
def planilha_inputs() -> LegacyInputs:
    return legacy_inputs()


@pytest.fixture(scope="session")
def esperado_planilha() -> dict[str, Any]:
    return load_json("esperado_planilha.json")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@pytest.fixture(scope="session")
def make_inputs() -> Callable[[dict[str, Any] | None], LegacyInputs]:
    return legacy_inputs
