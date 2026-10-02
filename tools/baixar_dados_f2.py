"""Leitura pontual dos dados da tabela da F2 (decisões Q9 e Q10). Não é coletor da F3.

    uv run python tools/baixar_dados_f2.py

Grava, sem sobrescrever o que já existe:

- ``data/calendar/feriados_nacionais.xls``: arquivo oficial de feriados da ANBIMA;
- ``tests/fixtures/f2/``: CDI diário (SGS 12), IPCA mensal (SGS 433) e o
  calendário de divulgação do IPCA (IBGE), cada um com ``manifest.json``.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parent.parent
F2 = ROOT / "tests" / "fixtures" / "f2"
CALENDAR = ROOT / "data" / "calendar"

AS_OF = "2026-09-04"  # 1ª decisão da Q8; a revisão (29/09) está nas entradas novas
SOURCES: list[dict[str, Any]] = [
    {
        "file": CALENDAR / "feriados_nacionais.xls",
        "source": "anbima_feriados_nacionais",
        "url": "https://www.anbima.com.br/feriados/arqs/feriados_nacionais.xls",
        "params": {},
    },
    {
        "file": F2 / "bcb_sgs_12_cdi_diario.json",
        "source": "bcb_sgs_12",
        "url": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados",
        "params": {"formato": "json", "dataInicial": "01/01/2026", "dataFinal": "04/09/2026"},
    },
    {
        "file": F2 / "bcb_sgs_433_ipca_mensal.json",
        "source": "bcb_sgs_433",
        "url": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados",
        "params": {"formato": "json", "dataInicial": "01/01/2026", "dataFinal": "31/12/2026"},
    },
    {
        # t0 = 29/09/2026 (Q8 revisada): CDI até t0, sem sobrescrever o arquivo até 04/09.
        "file": F2 / "bcb_sgs_12_cdi_diario_2026-09-29.json",
        "source": "bcb_sgs_12",
        "url": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados",
        "params": {"formato": "json", "dataInicial": "01/01/2026", "dataFinal": "29/09/2026"},
        "requested_date": "2026-09-29",
    },
    {
        "file": F2 / "bcb_sgs_7478_ipca15_mensal.json",
        "source": "bcb_sgs_7478",
        "url": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.7478/dados",
        "params": {"formato": "json", "dataInicial": "01/01/2026", "dataFinal": "31/12/2026"},
        "requested_date": "2026-09-29",
    },
    {
        # LEGADO diário (Q6): Selic acumulada no mês, com ano, como em Dashboard!L20:L31.
        "file": F2 / "bcb_sgs_4390_selic_mensal.json",
        "source": "bcb_sgs_4390",
        "url": "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4390/dados",
        "params": {"formato": "json", "dataInicial": "01/01/2025", "dataFinal": "30/09/2026"},
        "requested_date": "2026-09-29",
    },
    {
        "file": F2 / "ibge_calendario_2026.json",
        "source": "ibge_calendario",
        "url": "https://servicodados.ibge.gov.br/api/v3/calendario/",
        "params": {"de": "01-01-2026", "ate": "12-31-2026", "qtd": "1000"},
    },
]


def main() -> None:
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for src in SOURCES:
            path: Path = src["file"]
            path.parent.mkdir(parents=True, exist_ok=True)
            if path.exists():
                print(f"já existe, não sobrescrevo: {path.relative_to(ROOT)}")
                continue
            resp = client.get(src["url"], params=src["params"])
            resp.raise_for_status()
            path.write_bytes(resp.content)
            _append_manifest(
                path.parent,
                {
                    "file": path.name,
                    "source": src["source"],
                    "url": str(resp.url),
                    "requested_date": src.get("requested_date", AS_OF),
                    "retrieved_at": datetime.now(UTC).isoformat(timespec="seconds"),
                    "sha256": hashlib.sha256(resp.content).hexdigest(),
                    "bytes": len(resp.content),
                },
            )
            print(f"ok: {path.relative_to(ROOT)} ({len(resp.content)} bytes)")


def _append_manifest(folder: Path, entry: dict[str, Any]) -> None:
    """Registra cada arquivo logo depois de gravá-lo: uma falha no meio não deixa órfão."""
    manifest = folder / "manifest.json"
    old = json.loads(manifest.read_text()) if manifest.exists() else []
    manifest.write_text(json.dumps([*old, entry], ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
