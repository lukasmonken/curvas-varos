"""Converte o arquivo oficial de feriados da ANBIMA (.xls) em CSV versionado.

    uv run --group tools python tools/converter_feriados_anbima.py

Entrada: ``data/calendar/feriados_nacionais.xls`` (baixado por
``tools/baixar_dados_f2.py``). Saída: ``data/calendar/feriados_anbima.csv``,
com a data (ISO), o nome do feriado e um cabeçalho de comentário com a origem.
"""

from __future__ import annotations

import csv
import hashlib
from datetime import date, timedelta
from pathlib import Path

import xlrd

ROOT = Path(__file__).resolve().parent.parent
XLS = ROOT / "data" / "calendar" / "feriados_nacionais.xls"
CSV = ROOT / "data" / "calendar" / "feriados_anbima.csv"
EXCEL_EPOCH = date(1899, 12, 30)


def main() -> None:
    sheet = xlrd.open_workbook(str(XLS)).sheet_by_index(0)
    assert sheet.row_values(0)[:3] == ["Data", "Dia da Semana", "Feriado"], "layout mudou"
    rows: list[tuple[date, str]] = []
    for r in range(1, sheet.nrows):
        serial, _weekday, name = sheet.row_values(r)[:3]
        if not isinstance(serial, float):
            break  # notas de rodapé ("Fonte: ANBIMA", …)
        rows.append((EXCEL_EPOCH + timedelta(days=int(serial)), str(name).strip()))
    assert [d for d, _ in rows] == sorted(d for d, _ in rows), "datas fora de ordem"
    # Dois feriados podem cair no mesmo dia (ex.: 21/04/2079, Paixão e Tiradentes).
    merged: dict[date, list[str]] = {}
    for d, name in rows:
        merged.setdefault(d, []).append(name)
    rows = [(d, " / ".join(names)) for d, names in merged.items()]

    sha = hashlib.sha256(XLS.read_bytes()).hexdigest()
    with CSV.open("w", newline="", encoding="utf-8") as fh:
        fh.write(f"# fonte: ANBIMA feriados_nacionais.xls sha256={sha}\n")
        fh.write(f"# cobertura: {rows[0][0].year}-01-01 a {rows[-1][0].year}-12-31\n")
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(["data", "feriado"])
        for d, name in rows:
            writer.writerow([d.isoformat(), name])
    print(f"{len(rows)} feriados de {rows[0][0]} a {rows[-1][0]} → {CSV.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
