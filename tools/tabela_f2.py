"""Gera a tabela LEGADO × CORRIGIDO da F2.

    uv run python tools/tabela_f2.py

t0 = 29/09/2026 (Q8 revisada): as curvas da planilha são a publicação da ANBIMA
desse dia (docs/F3_RECONCILIACAO_ANBIMA.md). Saídas: ``docs/F2_LEGADO_X_CORRIGIDO.md``
e ``docs/f2_legado_x_corrigido.csv``.
"""

from datetime import date
from pathlib import Path

from curvas.calendar import load_anbima_calendar
from curvas.output.comparacao import RealizedFiles, build_report, render_csv, render_markdown

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
AS_OF = date(2026, 9, 29)


def main() -> None:
    report = build_report(
        FIXTURES / "legacy" / "inputs_planilha.json",
        RealizedFiles.in_dir(FIXTURES / "f2", cdi_name="bcb_sgs_12_cdi_diario_2026-09-29.json"),
        load_anbima_calendar(),
        AS_OF,
        anbima_csv=FIXTURES / "f3" / "anbima" / "cz_2026-09-29.csv",
    )
    (ROOT / "docs" / "F2_LEGADO_X_CORRIGIDO.md").write_text(render_markdown(report), "utf-8")
    (ROOT / "docs" / "f2_legado_x_corrigido.csv").write_text(render_csv(report), "utf-8")
    print("ok: docs/F2_LEGADO_X_CORRIGIDO.md, docs/f2_legado_x_corrigido.csv")


if __name__ == "__main__":
    main()
