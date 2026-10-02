"""Armazenamento dos brutos (seção 6): ``data/raw/AAAA/MM/AAAA-MM-DD/`` + ``manifest.json``.

Um bruto nunca é sobrescrito. Conteúdo novo ganha arquivo novo (``.v2``, ``.v3``…,
criado em modo exclusivo). Toda coleta vira uma entrada no manifesto, inclusive a
de um conteúdo idêntico a um arquivo já gravado (``duplicate: true``), para que a
sequência A → B → A fique registrada e nenhum arquivo fique sem entrada.

O manifesto é atualizado sob trava (``fcntl.flock``) e gravado de forma atômica
(arquivo temporário + ``os.replace``), então duas execuções simultâneas no mesmo
dia não se atropelam.
"""

import fcntl
import hashlib
import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from curvas.config import RAW_DIR


@dataclass(frozen=True)
class StoredRaw:
    path: Path
    sha256: str
    new: bool  # False se um arquivo idêntico já existia


def day_dir(as_of: date, root: Path = RAW_DIR) -> Path:
    return root / f"{as_of:%Y}" / f"{as_of:%m}" / f"{as_of:%Y-%m-%d}"


@contextmanager
def _locked(folder: Path) -> Iterator[None]:
    with (folder / ".manifest.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


def _write_atomic(path: Path, text: str) -> None:
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o644)  # mkstemp cria 0600
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def _versions(folder: Path, name: str) -> Iterator[Path]:
    stem, dot, ext = name.rpartition(".")
    if not dot:
        stem, ext = name, ""
    yield folder / name
    version = 2
    while True:
        yield folder / (f"{stem}.v{version}.{ext}" if ext else f"{stem}.v{version}")
        version += 1


def store_raw(
    as_of: date,
    name: str,
    content: bytes,
    *,
    source: str,
    url: str,
    requested_date: date,
    retrieved_at: datetime,
    source_date: date | None = None,
    publication_date: datetime | date | None = None,
    root: Path = RAW_DIR,
) -> StoredRaw:
    """Grava ``content`` em ``<dia>/<name>`` sem sobrescrever e registra no manifesto."""
    folder = day_dir(as_of, root)
    folder.mkdir(parents=True, exist_ok=True)
    sha = hashlib.sha256(content).hexdigest()
    with _locked(folder):
        target: Path | None = None
        new = False
        for candidate in _versions(folder, name):
            try:
                with candidate.open("xb") as fh:  # O_CREAT | O_EXCL: nunca sobrescreve
                    fh.write(content)
                target, new = candidate, True
                break
            except FileExistsError:
                if hashlib.sha256(candidate.read_bytes()).hexdigest() == sha:
                    target = candidate
                    break

        assert target is not None  # _versions é infinito: sempre há um candidato livre
        manifest = folder / "manifest.json"
        entries: list[dict[str, Any]] = (
            json.loads(manifest.read_text("utf-8")) if manifest.exists() else []
        )
        entries.append(
            {
                "file": target.name,
                "source": source,
                "url": url,
                "requested_date": requested_date.isoformat(),
                "source_date": source_date.isoformat() if source_date else None,
                "publication_date": publication_date.isoformat() if publication_date else None,
                "retrieved_at": retrieved_at.isoformat(timespec="seconds"),
                "sha256": sha,
                "bytes": len(content),
                "duplicate": not new,
            }
        )
        _write_atomic(manifest, json.dumps(entries, ensure_ascii=False, indent=1) + "\n")
    return StoredRaw(target, sha, new=new)


# ---------------------------------------------------------------- leitura e retenção


@dataclass(frozen=True)
class RawEntry:
    """Um bruto lido de volta, com a sua entrada no manifesto."""

    as_of: date
    content: bytes
    entry: dict[str, Any]


def _month_zip(as_of: date, root: Path) -> Path:
    return root / f"{as_of:%Y}" / f"{as_of:%m}.zip"


def _read_day(as_of: date, root: Path) -> tuple[list[dict[str, Any]], dict[str, bytes]] | None:
    """Manifesto e arquivos de um dia, da pasta solta ou do zip do mês."""
    folder = day_dir(as_of, root)
    if (folder / "manifest.json").exists():
        entries = json.loads((folder / "manifest.json").read_text("utf-8"))
        return entries, {e["file"]: (folder / e["file"]).read_bytes() for e in entries}
    archive = _month_zip(as_of, root)
    if archive.exists():
        prefix = f"{as_of:%Y-%m-%d}/"
        with zipfile.ZipFile(archive) as zf:
            names = set(zf.namelist())
            if prefix + "manifest.json" not in names:
                return None
            entries = json.loads(zf.read(prefix + "manifest.json").decode("utf-8"))
            return entries, {e["file"]: zf.read(prefix + e["file"]) for e in entries}
    return None


def read_raw(as_of: date, source: str, root: Path = RAW_DIR) -> RawEntry | None:
    """Última coleta de ``source`` gravada para o dia ``as_of`` (ordem do manifesto)."""
    day = _read_day(as_of, root)
    if day is None:
        return None
    entries, files = day
    matches = [e for e in entries if e["source"] == source]
    if not matches:
        return None
    entry = matches[-1]
    return RawEntry(as_of, files[entry["file"]], entry)


def latest_raw_before(
    source: str, before: date, root: Path = RAW_DIR, max_days: int = 60
) -> RawEntry | None:
    """Coleta mais recente de ``source`` em dias anteriores a ``before`` (fallback)."""
    for back in range(1, max_days + 1):
        found = read_raw(before - timedelta(days=back), source, root)
        if found is not None:
            return found
    return None


def compact_old_months(today: date, root: Path = RAW_DIR, keep_days: int = 90) -> list[Path]:
    """Seção 6: brutos com mais de ``keep_days`` dias vão para ``AAAA/MM.zip``.

    Só compacta um mês inteiro depois que o último dia dele sai da janela. O zip é
    criado em modo exclusivo; se já existir, o mês não é mexido (nunca sobrescreve).
    """
    limit = today - timedelta(days=keep_days)
    created: list[Path] = []
    for year_dir in sorted(p for p in root.glob("[0-9][0-9][0-9][0-9]") if p.is_dir()):
        for month_dir in sorted(p for p in year_dir.glob("[0-9][0-9]") if p.is_dir()):
            y, m = int(year_dir.name), int(month_dir.name)
            month_end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
            if month_end >= limit:
                continue
            archive = year_dir / f"{month_dir.name}.zip"
            if archive.exists():
                continue
            tmp = archive.with_suffix(".zip.tmp")
            with zipfile.ZipFile(tmp, "x", compression=zipfile.ZIP_DEFLATED) as zf:
                for f in sorted(month_dir.rglob("*")):
                    if f.is_file() and not f.name.startswith("."):
                        zf.write(f, f.relative_to(month_dir).as_posix())
            os.link(tmp, archive)  # falha se o zip aparecer no meio: nunca sobrescreve
            tmp.unlink()
            shutil.rmtree(month_dir)
            created.append(archive)
    return created
