"""Calendário de dias úteis ANBIMA (E8.1, E8.4).

Fonte: arquivo oficial de feriados nacionais da ANBIMA, versionado em
``data/calendar/feriados_anbima.csv`` (decisão Q10). O pacote ``bizdays`` é usado
só nos testes, como conferência cruzada.

Convenção de contagem (a mesma da B3/ANBIMA para DU): ``business_days(a, b)``
conta os dias úteis ``d`` com ``a <= d < b``.
"""

import csv
from bisect import bisect_left
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

DEFAULT_HOLIDAYS_CSV = (
    Path(__file__).resolve().parents[2] / "data" / "calendar" / "feriados_anbima.csv"
)


class CalendarRangeError(ValueError):
    """Data fora da cobertura do arquivo de feriados."""


@dataclass(frozen=True)
class BusinessCalendar:
    """Dias úteis = segunda a sexta, exceto feriados, dentro de ``[start, end]``."""

    holidays: frozenset[date]
    start: date
    end: date
    _days: tuple[date, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self.end < self.start:
            raise ValueError("end < start")
        days: list[date] = []
        d = self.start
        while d <= self.end:
            if d.weekday() < 5 and d not in self.holidays:
                days.append(d)
            d += timedelta(days=1)
        object.__setattr__(self, "_days", tuple(days))

    def _check(self, d: date) -> None:
        if not self.start <= d <= self.end:
            raise CalendarRangeError(f"{d} fora da cobertura {self.start}..{self.end}")

    def is_business_day(self, d: date) -> bool:
        self._check(d)
        return d.weekday() < 5 and d not in self.holidays

    def business_days(self, start: date, end: date) -> int:
        """Número de dias úteis em ``[start, end)``; negativo se ``end < start``."""
        self._check(start)
        self._check(end)
        return bisect_left(self._days, end) - bisect_left(self._days, start)

    def business_days_list(self, start: date, end: date) -> tuple[date, ...]:
        """Os dias úteis em ``[start, end)``."""
        self._check(start)
        self._check(end)
        return self._days[bisect_left(self._days, start) : bisect_left(self._days, end)]

    def following(self, d: date) -> date:
        """Primeiro dia útil ``>= d``."""
        self._check(d)
        i = bisect_left(self._days, d)
        if i == len(self._days):
            raise CalendarRangeError(f"sem dia útil depois de {d}")
        return self._days[i]

    def preceding(self, d: date) -> date:
        """Último dia útil ``<= d``."""
        self._check(d)
        i = bisect_left(self._days, d + timedelta(days=1))
        if i == 0:
            raise CalendarRangeError(f"sem dia útil antes de {d}")
        return self._days[i - 1]

    def year_end_business_days(self, as_of: date, years: Iterable[int]) -> tuple[int, ...]:
        """``dU(Y)``: dias úteis de ``as_of`` (inclusive) até 31/12/Y (inclusive) (E8.4)."""
        return tuple(self.business_days(as_of, date(y + 1, 1, 1)) for y in years)


def load_anbima_calendar(path: Path = DEFAULT_HOLIDAYS_CSV) -> BusinessCalendar:
    """Lê o CSV gerado por ``tools/converter_feriados_anbima.py``."""
    holidays: set[date] = set()
    first_year = last_year = None
    with path.open(encoding="utf-8") as fh:
        rows = csv.DictReader(line for line in fh if not line.startswith("#"))
        for row in rows:
            d = date.fromisoformat(row["data"])
            holidays.add(d)
            first_year = d.year if first_year is None else min(first_year, d.year)
            last_year = d.year if last_year is None else max(last_year, d.year)
    if first_year is None or last_year is None:
        raise ValueError(f"arquivo de feriados vazio: {path}")
    return BusinessCalendar(frozenset(holidays), date(first_year, 1, 1), date(last_year, 12, 31))
