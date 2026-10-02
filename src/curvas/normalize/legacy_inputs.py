"""LEGADO uso (b), execução diária (Parte 1, seção 8; Q6, Q15).

As mesmas fórmulas da planilha; mês, trimestre, realizado e YTG derivados de t0 e
iguais nas três curvas. O erro de método é preservado; o de operação, não.

- curvas: como o operador monta a partir da ANBIMA, sem o erro de colagem (Q15);
- m = último mês com IPCA divulgado até t0; trimestre = o que contém m (Q6);
- YTG = (12 − m)·21 em Inflação, DI e CDS;
- realizado: IPCA (SGS 433) e Selic (SGS 4390) mensais do ano de t0, meses 1..m;
- virada do ano (último IPCA é do ano anterior): m = 0, ano corrente indisponível.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from curvas.engine.legacy import LegacyInputs, SheetParams
from curvas.normalize.anbima_ettj import AnbimaEttj, legacy_curves_pct


@dataclass(frozen=True)
class LegacyDaily:
    inputs: LegacyInputs
    month: int  # 0 = nenhum mês do ano de t0 realizado (virada do ano)
    turn_of_year: bool


def build_legacy_inputs(
    *,
    as_of: date,
    ettj: AnbimaEttj,
    cds_bps: Sequence[float],
    last_ipca: tuple[int, int],
    ipca_monthly_pct: Mapping[tuple[int, int], float],
    selic_monthly_pct: Mapping[tuple[int, int], float],
) -> LegacyDaily:
    year = as_of.year
    ref_year, ref_month = last_ipca
    if ref_year > year:
        raise ValueError(f"IPCA de {ref_month:02d}/{ref_year} posterior a t0 = {as_of}")
    turn = ref_year < year
    month = 0 if turn else ref_month
    quarter = 1 if month == 0 else (month - 1) // 3 + 1

    def months(series: Mapping[tuple[int, int], float], what: str) -> tuple[float, ...]:
        out = []
        for m in range(1, 13):
            if m <= month:
                if (year, m) not in series:
                    raise ValueError(f"{what} de {m:02d}/{year} ausente para o LEGADO")
                out.append(series[(year, m)] / 100)  # Dashboard!I20 guarda 0,0033 = 0,33%
            else:
                out.append(0.0)  # meses > m não entram em T nem em U
        return tuple(out)

    di_pct, inflation_pct = legacy_curves_pct(ettj)
    params = SheetParams(month, quarter)
    inputs = LegacyInputs(
        first_year=year,
        inflation_curve_pct=inflation_pct,
        di_curve_pct=di_pct,
        cds_bps=tuple(cds_bps),
        ipca_monthly=months(ipca_monthly_pct, "IPCA"),
        selic_monthly=months(selic_monthly_pct, "Selic"),
        inflation_params=params,
        di_params=params,
        cds_ytg_days=(12 - month) * 21,  # Q6: o mesmo YTG nas três curvas
    )
    return LegacyDaily(inputs=inputs, month=month, turn_of_year=turn)
