"""CDS manual (Q2): validação, escolha do conjunto e marcação de defasagem (seção 12)."""

from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from conftest import ROOT
from curvas.calendar import load_anbima_calendar
from curvas.cds_add import append_cds, main
from curvas.normalize.cds_manual import (
    VERTEX_DAYS,
    ManualCdsError,
    cds_snapshot,
    load_cds,
    parse_manual_cds,
)

NOW = datetime(2026, 10, 1, 21, 0, tzinfo=UTC)
HEADER = "data_referencia,vertice,bps,fonte,preenchido_por,preenchido_em\n"


def block(day: str, base: float = 50.0, skip: str | None = None) -> str:
    lines = []
    for i, v in enumerate(VERTEX_DAYS):
        if v != skip:
            lines.append(f"{day},{v},{base + 10 * i},Investing.com,fulano,{day}T19:00:00-03:00\n")
    return "".join(lines)


FIXTURE = ROOT / "tests" / "fixtures" / "f4" / "cds_manual.csv"


def test_arquivo_de_producao_e_valido() -> None:
    """data/manual/cds.csv muda todo dia; aqui só se exige que continue válido."""
    path = ROOT / "data" / "manual" / "cds.csv"
    text = path.read_text(encoding="utf-8").splitlines(True)
    quotes = parse_manual_cds(text, load_anbima_calendar())
    latest = max(q.reference_date for q in quotes)
    assert not cds_snapshot(quotes, latest).stale


def test_arquivo_congelado() -> None:
    snap = load_cds(date(2026, 9, 29), retrieved_at=NOW, path=FIXTURE)
    assert snap.reference_date == date(2026, 9, 29)
    assert not snap.stale
    assert snap.bps[0] == 45.67
    assert snap.bps[-1] == 245.59
    assert snap.curve().days == (126, 252, 504, 756, 1008, 1260, 1764, 2520, 5040)
    assert snap.curve().rates[0] == pytest.approx(0.004567)


def test_usa_o_ultimo_completo_e_marca_stale() -> None:
    text = HEADER + block("2026-09-28") + block("2026-09-29", 60, skip="20A")
    snap = cds_snapshot(
        parse_manual_cds(text.splitlines(True)), date(2026, 9, 30), retrieved_at=NOW
    )
    assert snap.reference_date == date(2026, 9, 28)  # o de 29/09 está incompleto
    assert snap.stale
    assert snap.record.source_date == date(2026, 9, 28)
    assert snap.record.requested_date == date(2026, 9, 30)
    assert snap.record.fallback_reason is not None
    assert "28/09/2026" in snap.record.fallback_reason


def test_ignora_dados_depois_de_t0() -> None:
    text = HEADER + block("2026-09-28") + block("2026-10-02", 70)
    snap = cds_snapshot(
        parse_manual_cds(text.splitlines(True)), date(2026, 9, 28), retrieved_at=NOW
    )
    assert snap.reference_date == date(2026, 9, 28)
    assert not snap.stale


@pytest.mark.parametrize(
    ("line", "msg"),
    [
        ("2026-09-29,8A,50,x,y,2026-09-29T19:00:00\n", "desconhecido"),
        ("2026-09-29,5A,-3,x,y,2026-09-29T19:00:00\n", "faixa"),
        ("2026-09-29,5A,nan,x,y,2026-09-29T19:00:00\n", "faixa"),
        ("29/09/2026,5A,50,x,y,2026-09-29T19:00:00\n", "inválida"),
    ],
)
def test_linhas_invalidas(line: str, msg: str) -> None:
    with pytest.raises(ManualCdsError, match=msg):
        parse_manual_cds((HEADER + line).splitlines(True))


def test_repetido_sem_preenchimento_posterior() -> None:
    text = HEADER + block("2026-09-29") + block("2026-09-29")
    with pytest.raises(ManualCdsError, match="posterior"):
        parse_manual_cds(text.splitlines(True))


def test_correcao_por_linha_nova() -> None:
    fix = "2026-09-29,5A,99.5,Investing.com,beltrano,2026-09-30T10:00:00-03:00\n"
    text = HEADER + block("2026-09-29") + fix
    snap = cds_snapshot(
        parse_manual_cds(text.splitlines(True)), date(2026, 9, 29), retrieved_at=NOW
    )
    assert snap.bps[5] == 99.5
    assert any("corrigido" in a for a in snap.alerts)


def test_alertas() -> None:
    text = HEADER + block("2026-09-28") + block("2026-09-29", 60, skip="20A")
    snap = cds_snapshot(
        parse_manual_cds(text.splitlines(True)), date(2026, 9, 29), retrieved_at=NOW
    )
    assert snap.stale
    assert any("incompleto (faltam 20A)" in a for a in snap.alerts)
    assert any("defasado" in a for a in snap.alerts)
    assert snap.record.fallback_reason is not None
    assert "incompleto" in snap.record.fallback_reason


@pytest.mark.parametrize(
    ("text", "msg"),
    [
        (HEADER + "2026-09-29,5A,50,x,y,2026-09-29T19:00:00\n", "fuso"),
        (HEADER + "2026-09-29,5A,50,,y,2026-09-29T19:00:00-03:00\n", "obrigatórios"),
        (HEADER + "2026-10-30,5A,50,x,y,2026-09-30T19:00:00-03:00\n", "depois do preenchimento"),
        (HEADER + "2026-09-29,5A,50,x,y,2026-09-29T19:00:00-03:00,extra\n", "colunas"),
        ("data,vertice,bps\n2026-09-29,5A,50\n", "cabeçalho"),
    ],
)
def test_validacao_do_arquivo(text: str, msg: str) -> None:
    with pytest.raises(ManualCdsError, match=msg):
        parse_manual_cds(text.splitlines(True))


def test_dia_nao_util_com_calendario() -> None:
    text = HEADER + "2026-09-26,5A,50,x,y,2026-09-28T19:00:00-03:00\n"  # sábado
    with pytest.raises(ManualCdsError, match="dia útil"):
        parse_manual_cds(text.splitlines(True), load_anbima_calendar())


def test_sem_conjunto_completo() -> None:
    text = HEADER + block("2026-09-29", skip="6M")
    with pytest.raises(ManualCdsError, match="nenhum conjunto completo"):
        cds_snapshot(parse_manual_cds(text.splitlines(True)), date(2026, 9, 29), retrieved_at=NOW)


# ------------------------------------------------------------------ coleta manual assistida (Q16)

VALUES = [45.0, 55.0, 68.0, 87.0, 110.0, 131.0, 172.0, 213.0, 246.0]


def test_cds_add_acrescenta_e_valida(tmp_path: Path) -> None:
    target = tmp_path / "cds.csv"
    target.write_text(FIXTURE.read_text())
    when = datetime(2026, 10, 1, 19, 0, tzinfo=UTC)
    assert append_cds(target, date(2026, 10, 1), VALUES, filled_by="fulano", filled_at=when) == 9
    snap = load_cds(date(2026, 10, 1), path=target)
    assert snap.reference_date == date(2026, 10, 1)
    assert not snap.stale
    assert snap.bps == tuple(VALUES)


def test_cds_add_nao_grava_nada_se_invalido(tmp_path: Path) -> None:
    target = tmp_path / "cds.csv"
    original = FIXTURE.read_text()
    target.write_text(original)
    when = datetime(2026, 10, 3, 19, 0, tzinfo=UTC)
    with pytest.raises(ManualCdsError, match="dia útil"):  # 03/10/2026 é sábado
        append_cds(target, date(2026, 10, 3), VALUES, filled_by="x", filled_at=when)
    with pytest.raises(ManualCdsError, match="9 valores"):
        append_cds(target, date(2026, 10, 1), VALUES[:8], filled_by="x", filled_at=when)
    assert target.read_text() == original


def test_cds_add_cli_interativo(tmp_path: Path) -> None:
    target = tmp_path / "cds.csv"
    answers = iter(str(v).replace(".", ",") for v in VALUES)
    rc = main(
        ["--data", "2026-10-01", "--por", "fulano", "--arquivo", str(target)],
        prompt=lambda _p: next(answers),
    )
    assert rc == 0
    assert load_cds(date(2026, 10, 1), path=target).bps == tuple(VALUES)
