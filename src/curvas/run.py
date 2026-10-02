"""Pipeline diário (Parte 1, seções 6, 7, 11, 12 e 13).

    python -m curvas.run [--as-of AAAA-MM-DD] [--offline] [--today AAAA-MM-DD]
    python -m curvas.run --catch-up        # modo do workflow diário

fetch → validate → normalize → compute → compare → alerts → write. O build do site
é da F5. Sem ``--as-of``, t0 = hoje (horário de Brasília) se for dia útil ANBIMA;
em dia não útil o pipeline encerra sem publicar.

``--offline`` refaz o cálculo só com os brutos já gravados em ``data/raw`` (nada de
rede). Mesmos t0, brutos e configuração produzem exatamente a mesma saída (16.7).
"""

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal

import httpx
from pydantic import ValidationError as SchemaError

from curvas import __version__, logs
from curvas.calendar import BusinessCalendar, load_anbima_calendar
from curvas.config import DATA_DIR, DEFAULT, RAW_DIR, ROOT, Config
from curvas.engine.corrected import InflationGapRule, IpcaRelease, compute_corrected
from curvas.engine.legacy import compute_legacy
from curvas.fetch.http import FetchError, make_client
from curvas.fetch.raw import (
    RawEntry,
    compact_old_months,
    read_raw,
    store_raw,
)
from curvas.fetch.sources import Fetched, fetch_anbima_ettj, fetch_ibge_calendar, fetch_sgs
from curvas.models import Alert, RunOutput, SourceRecord
from curvas.normalize.anbima_ettj import (
    AnbimaEttj,
    AnbimaFormatError,
    NotPublishedError,
    corrected_curves,
    parse_anbima_ettj,
)
from curvas.normalize.bcb_sgs import monthly_by_reference, parse_sgs
from curvas.normalize.cds_manual import DEFAULT_PATH as CDS_MANUAL_PATH
from curvas.normalize.cds_manual import CdsSnapshot, ManualCdsError, load_cds
from curvas.normalize.corrected_inputs import build_corrected_inputs
from curvas.normalize.ibge import IPCA15_TITLE, parse_ipca_releases
from curvas.normalize.legacy_inputs import build_legacy_inputs
from curvas.output.json_out import ComputeBundle, assemble_output, daily_change_alerts
from curvas.validate.checks import ValidationError, validate_anbima

log = logs.get("run")
BRT = timezone(timedelta(hours=-3))  # sem horário de verão desde 2019


class BlockingError(RuntimeError):
    """Falha que bloqueia a publicação (seção 12)."""


class NotReadyError(RuntimeError):
    """A ETTJ de t0 ainda não saiu; no modo de recuperação o dia fica para a próxima."""


@dataclass(frozen=True)
class Paths:
    raw_root: Path = RAW_DIR
    out_root: Path = DATA_DIR
    manual_cds: Path = CDS_MANUAL_PATH
    holidays: Path | None = None

    @property
    def curves_dir(self) -> Path:
        return self.out_root / "curves"

    @property
    def latest(self) -> Path:
        return self.out_root / "latest.json"


@dataclass(frozen=True)
class RunResult:
    status: Literal["published", "skipped"]
    as_of: date | None
    reason: str
    output: RunOutput | None = None
    path: Path | None = None


# ---------------------------------------------------------------- coleta com fallback


@dataclass(frozen=True)
class SourceSpec:
    source: str
    file_name: str
    fetch: Callable[[], Fetched]
    check: Callable[[bytes, date], Any]  # levanta se o bruto for inválido
    source_date: Callable[[bytes, date], date | None]


@dataclass
class Collected:
    content: bytes
    record: SourceRecord
    alerts: list[Alert] = field(default_factory=list)
    failure: str | None = None  # causa real quando caiu no fallback
    not_published: bool = False  # a fonte respondeu "ainda não publicado" (corpo vazio)


_SOURCE_ERRORS = (
    FetchError,
    NotPublishedError,
    AnbimaFormatError,
    ValidationError,
    ValueError,
    KeyError,
    json.JSONDecodeError,
)


def _record(
    spec: SourceSpec, raw: RawEntry, as_of: date, *, stale: bool, reason: str | None
) -> SourceRecord:
    entry = raw.entry
    return SourceRecord(
        source=spec.source,
        requested_date=as_of,
        source_date=spec.source_date(raw.content, raw.as_of),
        publication_date=entry.get("publication_date"),
        retrieved_at=entry["retrieved_at"],
        stale=stale,
        fallback_reason=reason,
        url=entry.get("url"),
        sha256=entry.get("sha256"),
        raw_path=f"{raw.as_of:%Y/%m/%Y-%m-%d}/{entry['file']}",
    )


def collect(spec: SourceSpec, as_of: date, *, offline: bool, raw_root: Path) -> Collected:
    """Bruto válido de ``spec`` para t0; se falhar, o último válido anterior (stale)."""
    problem: str | None = None
    fetch_error: Exception | None = None
    if not offline:
        try:
            fetched = spec.fetch()
            spec.check(fetched.content, as_of)
            store_raw(
                as_of,
                spec.file_name,
                fetched.content,
                source=spec.source,
                url=fetched.url,
                requested_date=fetched.requested_date,
                retrieved_at=fetched.retrieved_at,
                source_date=spec.source_date(fetched.content, as_of),
                root=raw_root,
            )
        except _SOURCE_ERRORS as exc:
            fetch_error = exc
            problem = f"{type(exc).__name__}: {exc}"
            log.warning("fonte falhou", extra={"source": spec.source, "error": problem})

    same_day = read_raw(as_of, spec.source, raw_root)
    if same_day is not None:
        try:
            spec.check(same_day.content, as_of)
            got = Collected(
                same_day.content,
                _record(spec, same_day, as_of, stale=False, reason=None),
            )
            if problem is not None:  # coleta de agora falhou, mas há bruto válido de hoje
                got.alerts.append(
                    Alert(
                        level="info",
                        code="fonte_bruto_do_dia",
                        message=f"{spec.source}: {problem}; usado o bruto gravado antes, de t0",
                        source=spec.source,
                    )
                )
            return got
        except _SOURCE_ERRORS as exc:
            problem = f"bruto gravado inválido: {type(exc).__name__}: {exc}"
    if problem is None:
        problem = "sem bruto gravado para t0 (modo offline)"

    for back in range(1, 61):
        older = read_raw(as_of - timedelta(days=back), spec.source, raw_root)
        if older is None:
            continue
        try:
            spec.check(older.content, older.as_of)
        except _SOURCE_ERRORS:
            continue
        reason = f"{problem}; usado o bruto de {older.as_of:%d/%m/%Y}"
        alert = Alert(
            level="warning",
            code="fonte_defasada",
            message=f"{spec.source}: {reason}",
            source=spec.source,
        )
        return Collected(
            older.content,
            _record(spec, older, as_of, stale=True, reason=reason),
            [alert],
            failure=problem,
            not_published=isinstance(fetch_error, NotPublishedError),
        )
    raise BlockingError(f"{spec.source}: {problem}; nenhum bruto válido anterior")


# ---------------------------------------------------------------- especificação das fontes


def _check_anbima(content: bytes, day: date) -> AnbimaEttj:
    ettj = parse_anbima_ettj(content)
    validate_anbima(ettj, day)
    return ettj


def _sgs_check(bounds: tuple[float, float], what: str) -> Callable[[bytes, date], None]:
    """Seção 12: série não vazia e todos os valores dentro da faixa plausível."""
    lo, hi = bounds

    def check(content: bytes, _day: date) -> None:
        rows = parse_sgs(content)
        if not rows:
            raise ValueError("série vazia")
        bad = [(d.isoformat(), v) for d, v in rows if not lo <= v <= hi]
        if bad:
            raise ValueError(f"{what} fora da faixa [{lo}, {hi}]: {bad[:3]}")

    return check


def _check_ibge(content: bytes, _day: date) -> None:
    if not parse_ipca_releases(content):
        raise ValueError("agenda sem divulgações do IPCA")


def _last_obs(content: bytes, day: date) -> date | None:
    """Data econômica: a última observação até t0 (o bruto pode trazer dias posteriores)."""
    dates = [d for d, _ in parse_sgs(content) if d <= day]
    return max(dates) if dates else None


def source_specs(client: httpx.Client | None, as_of: date, cfg: Config) -> list[SourceSpec]:
    year = as_of.year

    def need() -> httpx.Client:
        if client is None:
            raise FetchError("sem cliente HTTP")
        return client

    def sgs(code: int, start: date, end: date) -> Callable[[], Fetched]:
        return lambda: fetch_sgs(need(), code, start, end, as_of=as_of, cfg=cfg)

    first, last = date(year - 1, 1, 1), date(year, 12, 31)
    # A agenda vai até o fim do ano seguinte: depois do IPCA de novembro (~10/12), a
    # próxima divulgação já é de janeiro, e o montador exige uma divulgação após t0.
    agenda_last = date(year + 1, 12, 31)
    r = cfg.ranges
    return [
        SourceSpec(
            "anbima_ettj",
            "anbima_ettj.csv",
            lambda: fetch_anbima_ettj(need(), as_of, cfg=cfg),
            _check_anbima,
            lambda c, d: parse_anbima_ettj(c).reference_date,
        ),
        SourceSpec(
            "bcb_sgs_12",
            "bcb_sgs_12.json",
            sgs(cfg.sgs.cdi_daily, date(year, 1, 1), as_of),
            _sgs_check(r.cdi_daily_pct, "CDI diário"),
            _last_obs,
        ),
        SourceSpec(
            "bcb_sgs_433",
            "bcb_sgs_433.json",
            sgs(cfg.sgs.ipca_monthly, first, last),
            _sgs_check(r.ipca_monthly_pct, "IPCA mensal"),
            _last_obs,
        ),
        SourceSpec(
            "bcb_sgs_4390",
            "bcb_sgs_4390.json",
            sgs(cfg.sgs.selic_monthly, first, last),
            _sgs_check(r.selic_monthly_pct, "Selic mensal"),
            _last_obs,
        ),
        SourceSpec(
            "bcb_sgs_7478",
            "bcb_sgs_7478.json",
            sgs(cfg.sgs.ipca15_monthly, first, last),
            _sgs_check(r.ipca_monthly_pct, "IPCA-15 mensal"),
            _last_obs,
        ),
        SourceSpec(
            "ibge_calendario",
            "ibge_calendario.json",
            lambda: fetch_ibge_calendar(need(), first, agenda_last, as_of=as_of, cfg=cfg),
            _check_ibge,
            lambda c, d: None,
        ),
    ]


# ---------------------------------------------------------------- execução


def _ipca_cutoff(
    releases: list[IpcaRelease], ipca: dict[tuple[int, int], float], as_of: date
) -> tuple[date, list[Alert]]:
    """Se o IBGE já divulgou um IPCA que ainda não está no SGS, antecipa o corte."""
    cutoff, alerts = as_of, []
    # Do último IPCA divulgado para trás, até o primeiro mês que já tem valor no SGS.
    for rel in sorted(
        (r for r in releases if r.release_date <= as_of),
        key=lambda r: r.release_date,
        reverse=True,
    ):
        if (rel.ref_year, rel.ref_month) in ipca:
            break
        cutoff = rel.release_date - timedelta(days=1)
        alerts.append(
            Alert(
                level="warning",
                code="ipca_sem_valor_no_sgs",
                message=(
                    f"IPCA de {rel.ref_month:02d}/{rel.ref_year} divulgado em "
                    f"{rel.release_date:%d/%m/%Y}, mas ainda sem valor no SGS 433: "
                    "tratado como não divulgado (coberto pela curva)"
                ),
                source="bcb_sgs_433",
            )
        )
    return cutoff, alerts


def _cdi_with_fill(
    cdi: list[tuple[date, float]], cal: BusinessCalendar, as_of: date
) -> tuple[list[tuple[date, float]], list[Alert], str | None]:
    """Q18 (provisório): dias finais sem CDI (atraso do SGS) repetem a última observação.

    Só cobre a ponta, nunca um buraco no meio, e sempre com alerta.
    """
    if not cdi:
        return cdi, [], None
    needed = cal.business_days_list(date(as_of.year, 1, 1), as_of)
    have = {d for d, _ in cdi}
    missing = [d for d in needed if d not in have]
    if not missing:
        return cdi, [], None
    last_day, last_rate = cdi[-1]
    if any(d < last_day for d in missing):
        return cdi, [], None  # buraco no meio: deixa o montador falhar alto
    filled = [*cdi, *((d, last_rate) for d in missing)]
    alert = Alert(
        level="warning",
        code="cdi_preenchido",
        message=(
            f"CDI de {missing[0]:%d/%m/%Y} a {missing[-1]:%d/%m/%Y} ainda sem valor no SGS 12: "
            f"repetida a taxa de {last_day:%d/%m/%Y} ({last_rate}% a.d.) (Q18)"
        ),
        source="bcb_sgs_12",
    )
    return filled, [alert], alert.message


def _git_commit() -> str | None:
    if os.environ.get("GITHUB_SHA"):
        return os.environ["GITHUB_SHA"]
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return out.stdout.strip() or None


def _previous_output(curves_dir: Path, as_of: date, cal: BusinessCalendar) -> dict[str, Any] | None:
    """Saída do dia útil imediatamente anterior a t0 (referência fixa da variação diária)."""
    target = curves_dir / f"{cal.preceding(as_of - timedelta(days=1)):%Y-%m-%d}.json"
    return json.loads(target.read_text("utf-8")) if target.exists() else None


def _compute(
    sources: dict[str, Collected],
    cds: CdsSnapshot,
    cal: BusinessCalendar,
    as_of: date,
    gap_rule: InflationGapRule,
) -> tuple[ComputeBundle, list[Alert]]:
    """normalize → compute: LEGADO (b) e CORRIGIDO a partir dos brutos validados."""
    anbima = sources["anbima_ettj"]
    ettj = _check_anbima(anbima.content, anbima.record.source_date or as_of)
    cdi = parse_sgs(sources["bcb_sgs_12"].content)
    ipca = monthly_by_reference(parse_sgs(sources["bcb_sgs_433"].content))
    selic = monthly_by_reference(parse_sgs(sources["bcb_sgs_4390"].content))
    ipca15 = monthly_by_reference(parse_sgs(sources["bcb_sgs_7478"].content))
    agenda = sources["ibge_calendario"].content
    releases = parse_ipca_releases(agenda)

    cutoff, alerts = _ipca_cutoff(releases, ipca, as_of)
    observed = [d for d, _ in cdi if d < as_of]
    cdi, cdi_alerts, filled = _cdi_with_fill(cdi, cal, as_of)
    alerts += cdi_alerts
    if filled is not None:
        src = sources["bcb_sgs_12"]
        src.record = src.record.model_copy(update={"stale": True, "fallback_reason": filled})
    di_curve, inflation_curve = corrected_curves(ettj)
    try:
        corrected_inputs = build_corrected_inputs(
            as_of=as_of,
            calendar=cal,
            di_curve=di_curve,
            inflation_curve=inflation_curve,
            cds_curve=cds.curve(),
            cdi_daily_pct=cdi,
            ipca_monthly_pct=ipca,
            ipca_releases=releases,
            gap_rule=gap_rule,
            ipca15_monthly_pct=ipca15,
            ipca15_releases=parse_ipca_releases(agenda, IPCA15_TITLE),
            ipca_cutoff=cutoff,
        )
        legacy_daily = build_legacy_inputs(
            as_of=as_of,
            ettj=ettj,
            cds_bps=cds.bps,
            last_ipca=corrected_inputs.ipca_last_published or (as_of.year, 0),
            ipca_monthly_pct=ipca,
            selic_monthly_pct=selic,
        )
        bundle = ComputeBundle(
            as_of=as_of,
            ettj=ettj,
            corrected_inputs=corrected_inputs,
            corrected=compute_corrected(corrected_inputs),
            legacy_daily=legacy_daily,
            legacy=compute_legacy(legacy_daily.inputs),
            cdi=cdi,
            cdi_last_observed=max(observed) if observed else None,
            ipca=ipca,
            selic=selic,
            releases=releases,
            cds_source=cds.record.url or "cds_manual",
        )
    except (ValueError, ArithmeticError) as exc:
        raise BlockingError(f"cálculo: {type(exc).__name__}: {exc}") from exc
    # Seção 7: data de divulgação do IPCA e do IPCA-15 usados (agenda do IBGE, Q9).
    ipca_src = sources["bcb_sgs_433"]
    ipca_src.record = ipca_src.record.model_copy(
        update={"publication_date": corrected_inputs.ipca_last_release_date}
    )
    if corrected_inputs.ipca15_used is not None:
        src15 = sources["bcb_sgs_7478"]
        src15.record = src15.record.model_copy(
            update={"publication_date": corrected_inputs.ipca15_used.release_date}
        )
    return bundle, alerts


def run(
    *,
    as_of: date | None = None,
    today: date | None = None,
    offline: bool = False,
    client: httpx.Client | None = None,
    paths: Paths = Paths(),  # noqa: B008
    cfg: Config = DEFAULT,
    git_commit: str | None = None,
    gap_rule: InflationGapRule = InflationGapRule.CURVE,
    retrieved_at: datetime | None = None,
    require_fresh_curves: bool = False,
) -> RunResult:
    cal = load_anbima_calendar(paths.holidays) if paths.holidays else load_anbima_calendar()
    today = today or datetime.now(BRT).date()
    if as_of is None:
        if not cal.is_business_day(today):
            return RunResult("skipped", None, f"{today:%d/%m/%Y} não é dia útil ANBIMA")
        as_of = today
    elif not cal.is_business_day(as_of):
        raise BlockingError(f"t0 = {as_of} não é dia útil ANBIMA")
    if as_of > today:
        raise BlockingError(f"t0 = {as_of} está no futuro (hoje = {today})")

    alerts: list[Alert] = []
    sources: dict[str, Collected] = {}
    for spec in source_specs(client, as_of, cfg):
        got = collect(spec, as_of, offline=offline, raw_root=paths.raw_root)
        if require_fresh_curves and spec.source == "anbima_ettj" and got.record.stale:
            # E8.1: t0 é um dia com curvas; sem a ETTJ do dia, não há o que publicar.
            # Só "ainda não publicado" no próprio dia é espera normal; qualquer outra
            # falha (rede, formato, validação, dia passado vazio) é erro visível.
            if got.not_published and as_of >= today:
                raise NotReadyError(f"ETTJ da ANBIMA de {as_of:%d/%m/%Y} ainda não publicada")
            raise BlockingError(f"anbima_ettj de {as_of:%d/%m/%Y}: {got.failure}")
        sources[spec.source] = got
        alerts += got.alerts
    try:
        cds = load_cds(as_of, retrieved_at=retrieved_at, path=paths.manual_cds, calendar=cal)
    except (ManualCdsError, OSError) as exc:
        raise BlockingError(f"CDS manual: {exc}") from exc
    alerts += [
        Alert(level="warning", code="cds_manual", message=a, source="cds_manual")
        for a in cds.alerts
    ]
    bundle, compute_alerts = _compute(sources, cds, cal, as_of, gap_rule)
    alerts += compute_alerts
    records = [s.record for s in sources.values()] + [cds.record]
    try:
        output = assemble_output(
            bundle,
            sources=records,
            alerts=alerts,
            code_version=__version__,
            git_commit=git_commit if git_commit is not None else _git_commit(),
        )
        previous = _previous_output(paths.curves_dir, as_of, cal)
        if previous is not None:
            extra = daily_change_alerts(previous, output, cfg.alerts.max_daily_change_bps)
            output = output.model_copy(update={"alerts": [*output.alerts, *extra]})
        output = RunOutput.model_validate(output.model_dump())  # schema completo de novo
    except SchemaError as exc:
        raise BlockingError(f"schema inválido: {exc}") from exc

    path = write_output(output, paths)
    if not offline:
        for archive in compact_old_months(as_of, paths.raw_root):
            log.info("brutos compactados", extra={"archive": str(archive)})
    return RunResult("published", as_of, "ok", output, path)


ANBIMA_WINDOW = 5  # a página pública da ANBIMA só guarda os últimos 5 dias úteis


def _needs_run(path: Path) -> bool:
    """Sem saída, ou saída publicada com a ETTJ de outro dia (stale): refazer."""
    if not path.exists():
        return True
    out = json.loads(path.read_text("utf-8"))
    return any(s["source"] == "anbima_ettj" and s["stale"] for s in out["sources"])


def pending_dates(
    today: date, paths: Paths, cal: BusinessCalendar, start: date | None = None
) -> list[date]:
    """Dias úteis da janela da ANBIMA (até hoje, a partir de ``start``) ainda por fazer."""
    window: list[date] = []
    day = today
    while len(window) < ANBIMA_WINDOW:
        if cal.is_business_day(day):
            window.append(day)
        day -= timedelta(days=1)
    return sorted(
        d
        for d in window
        if (start is None or d >= start) and _needs_run(paths.curves_dir / f"{d:%Y-%m-%d}.json")
    )


@dataclass(frozen=True)
class CatchUpResult:
    published: list[RunResult]
    not_ready: list[tuple[date, str]]
    blocked: list[tuple[date, str]]


def catch_up(
    *,
    today: date | None = None,
    client: httpx.Client | None = None,
    paths: Paths = Paths(),  # noqa: B008
    cfg: Config = DEFAULT,
    git_commit: str | None = None,
    gap_rule: InflationGapRule = InflationGapRule.CURVE,
) -> CatchUpResult:
    """Modo de recuperação do workflow diário (seção 13).

    O agendamento do GitHub atrasa e às vezes descarta execuções; por isso cada
    execução processa todos os dias úteis pendentes dentro da janela da ANBIMA. Dia
    sem ETTJ publicada fica para a próxima execução (nunca sai como dado defasado).
    """
    cal = load_anbima_calendar(paths.holidays) if paths.holidays else load_anbima_calendar()
    today = today or datetime.now(BRT).date()
    published: list[RunResult] = []
    not_ready: list[tuple[date, str]] = []
    blocked: list[tuple[date, str]] = []
    for day in pending_dates(today, paths, cal, cfg.pipeline_start):
        try:
            published.append(
                run(
                    as_of=day,
                    today=today,
                    client=client,
                    paths=paths,
                    cfg=cfg,
                    git_commit=git_commit,
                    gap_rule=gap_rule,
                    require_fresh_curves=True,
                )
            )
        except NotReadyError as exc:
            not_ready.append((day, str(exc)))
        except BlockingError as exc:
            blocked.append((day, str(exc)))
    return CatchUpResult(published, not_ready, blocked)


def write_output(output: RunOutput, paths: Paths) -> Path:
    """``data/curves/AAAA-MM-DD.json`` e, se for a data mais recente, ``data/latest.json``."""
    text = output.model_dump_json(indent=1) + "\n"
    paths.curves_dir.mkdir(parents=True, exist_ok=True)
    as_of = output.metadata.as_of_date
    target = paths.curves_dir / f"{as_of:%Y-%m-%d}.json"
    target.write_text(text, "utf-8")
    current = None
    if paths.latest.exists():
        current = json.loads(paths.latest.read_text("utf-8"))["metadata"]["as_of_date"]
    if current is None or current <= f"{as_of:%Y-%m-%d}":
        paths.latest.write_text(text, "utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m curvas.run", description=__doc__)
    parser.add_argument("--as-of", type=date.fromisoformat, help="t0 (AAAA-MM-DD)")
    parser.add_argument("--today", type=date.fromisoformat, help="simula a data de hoje")
    parser.add_argument("--offline", action="store_true", help="só brutos já gravados")
    parser.add_argument(
        "--ipca15", action="store_true", help="Forma A do IPCA-15 (Q13; desligada por padrão)"
    )
    parser.add_argument(
        "--catch-up",
        action="store_true",
        help="processa os dias úteis pendentes da janela da ANBIMA (modo do workflow diário)",
    )
    args = parser.parse_args(argv)
    logs.configure()
    gap_rule = InflationGapRule.IPCA15_SAME_MONTH if args.ipca15 else InflationGapRule.CURVE
    client = None if args.offline else make_client(DEFAULT.http)
    if args.catch_up:
        try:
            return _main_catch_up(args.today, client, gap_rule)
        finally:
            if client is not None:
                client.close()
    try:
        result = run(
            as_of=args.as_of, today=args.today, offline=args.offline, client=client,
            gap_rule=gap_rule,
        )  # fmt: skip
    except BlockingError as exc:
        log.error("publicação bloqueada", extra={"error": str(exc)})
        _github_output(published=False, as_of=None)
        print(f"BLOQUEADO: {exc}", file=sys.stderr)
        return 1
    finally:
        if client is not None:
            client.close()
    _github_output(published=result.status == "published", as_of=result.as_of)
    if result.status == "skipped":
        print(f"Sem publicação: {result.reason}")
        return 0
    assert result.output is not None
    n = len(result.output.alerts)
    print(f"Publicado: t0 = {result.as_of}, {n} alerta(s), {result.path}")
    return 0


def _main_catch_up(
    today: date | None, client: httpx.Client | None, gap_rule: InflationGapRule
) -> int:
    res = catch_up(today=today, client=client, gap_rule=gap_rule)
    for r in res.published:
        assert r.output is not None
        print(f"Publicado: t0 = {r.as_of}, {len(r.output.alerts)} alerta(s), {r.path}")
    for day, why in res.not_ready:
        print(f"Pendente: {day}: {why}")
    for day, why in res.blocked:
        log.error("publicação bloqueada", extra={"as_of": str(day), "error": why})
        print(f"BLOQUEADO: {day}: {why}", file=sys.stderr)
    if not (res.published or res.not_ready or res.blocked):
        print("Nada pendente.")
    last = max((r.as_of for r in res.published if r.as_of), default=None)
    _github_output(published=bool(res.published), as_of=last)
    return 1 if res.blocked else 0


def _github_output(*, published: bool, as_of: date | None) -> None:
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as fh:
            fh.write(f"published={'true' if published else 'false'}\n")
            fh.write(f"as_of={as_of.isoformat() if as_of else ''}\n")


if __name__ == "__main__":
    raise SystemExit(main())
