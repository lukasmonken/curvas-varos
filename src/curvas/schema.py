"""Schema da saída (seção 11).

python -m curvas.schema export            # grava docs/schema.json
python -m curvas.schema validate ARQUIVO  # valida um JSON de saída (bloqueia se inválido)
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic import ValidationError

from curvas.config import ROOT
from curvas.models import RunOutput

SCHEMA_PATH = ROOT / "docs" / "schema.json"


def schema_text() -> str:
    return json.dumps(RunOutput.model_json_schema(), ensure_ascii=False, indent=1) + "\n"


def validate_file(path: Path) -> RunOutput:
    """Valida o JSON contra o schema; levanta ``ValidationError`` se inválido."""
    return RunOutput.model_validate_json(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m curvas.schema")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export")
    check = sub.add_parser("validate")
    check.add_argument("files", nargs="+", type=Path)
    args = parser.parse_args(argv)
    if args.cmd == "export":
        SCHEMA_PATH.write_text(schema_text(), encoding="utf-8")
        print(f"ok: {SCHEMA_PATH.relative_to(ROOT)}")
        return 0
    status = 0
    for path in args.files:
        try:
            out = validate_file(path)
        except (ValidationError, OSError) as exc:
            print(f"INVÁLIDO: {path}: {exc}", file=sys.stderr)
            status = 1
        else:
            print(f"ok: {path} (t0 = {out.metadata.as_of_date})")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
