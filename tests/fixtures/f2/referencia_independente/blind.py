"""Reimplementacao cega do modo CORRIGIDO (E8), escrita sem ler src/curvas, tools/,
tests/*.py, docs/F2_LEGADO_X_CORRIGIDO.md nem docs/f2_legado_x_corrigido.csv.

Fontes lidas: docs/ESPECIFICACAO.md (E8), OPEN_QUESTIONS.md (Q8-Q10),
tests/fixtures/legacy/inputs_planilha.json, data/calendar/feriados_anbima.csv,
tests/fixtures/f2/{bcb_sgs_12_cdi_diario,bcb_sgs_433_ipca_mensal,ibge_calendario_2026}.json.

Convencoes (cada uma e uma escolha; E8 nao fixa):
  C1  dia util = seg-sex fora de feriados_anbima.csv.
  C2  dU(Y) = numero de dias uteis em (L, 31/12/Y], onde L = ultimo dia ja coberto pelo
      realizado. Variante "A": CDI realizado inclui o CDI de t0 -> L = t0 -> dU = bd(t0, 31/12].
      Variante "B": realizado ate o dia util anterior a t0 -> dU = bd[t0, 31/12].
  C3  CDI realizado = prod(1 + cdi_d/100) - 1, d em [01/01/Y0, t0] (A) ou [01/01/Y0, t0) (B).
  C4  IPCA divulgado ate t0 = meses com divulgacao IBGE (titulo exato) com data <= t0.
  C5  Lacuna do IPCA: curva contada a partir do 1o d.u. apos o ultimo mes realizado.
      Opcao "ii" (literal E8.5+E8.6): so o ano corrente usa n = bd(fim_mes, 31/12/Y0];
      anos seguintes usam dU(Y) a partir de t0.
      Opcao "i": a origem inteira da curva de inflacao passa ao fim do mes realizado.
      Opcao "iii": fator separado F(n_gap) * F(dU(Y0)).
  C6  Extrapolacao a direita: forward do ultimo segmento (E8.3); a esquerda: spot do 1o vertice.
  C7  CDS annualized_rate = (1 + remaining)^(252/dU(Y0)) - 1.
"""
from __future__ import annotations

import csv
import datetime as dt
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
T0 = dt.date(2026, 9, 4)
YEARS = list(range(2026, 2037))
IPCA_TITLE = "Índice Nacional de Preços ao Consumidor Amplo"


# ---------------------------------------------------------------- calendario
def load_holidays() -> set[dt.date]:
    out: set[dt.date] = set()
    with open(ROOT / "data/calendar/feriados_anbima.csv", encoding="utf-8") as fh:
        rows = [ln for ln in fh if not ln.startswith("#")]
    for row in csv.DictReader(rows):
        out.add(dt.date.fromisoformat(row["data"]))
    return out


HOL = load_holidays()


def is_bd(d: dt.date) -> bool:
    return d.weekday() < 5 and d not in HOL


def bd_open_closed(a: dt.date, b: dt.date) -> int:
    """Numero de dias uteis em (a, b]."""
    n = 0
    d = a + dt.timedelta(days=1)
    while d <= b:
        n += is_bd(d)
        d += dt.timedelta(days=1)
    return n


def prev_bd(d: dt.date) -> dt.date:
    d -= dt.timedelta(days=1)
    while not is_bd(d):
        d -= dt.timedelta(days=1)
    return d


# ---------------------------------------------------------------- curva
class FlatForward:
    def __init__(self, days: list[int], spots: list[float]):
        assert days == sorted(days) and len(set(days)) == len(days)
        self.v = [float(x) for x in days]
        self.s = spots
        self.lnF = [x / 252.0 * math.log1p(s) for x, s in zip(self.v, spots)]

    def lnfactor(self, d: float) -> float:
        v, lnF = self.v, self.lnF
        if d <= v[0]:
            return d / 252.0 * math.log1p(self.s[0])
        if d >= v[-1]:
            slope = (lnF[-1] - lnF[-2]) / (v[-1] - v[-2])
            return lnF[-1] + slope * (d - v[-1])
        for k in range(len(v) - 1):
            if v[k] <= d <= v[k + 1]:
                w = (d - v[k]) / (v[k + 1] - v[k])
                return lnF[k] + w * (lnF[k + 1] - lnF[k])
        raise AssertionError

    def factor(self, d: float) -> float:
        return math.exp(self.lnfactor(d))

    def factor_pow(self, d: float) -> float:
        """Mesma conta pela forma literal de E8.3 (potencias), para conferir arredondamento."""
        v, s = self.v, self.s
        F = [(1 + si) ** (vi / 252) for vi, si in zip(v, s)]
        if d <= v[0]:
            return (1 + s[0]) ** (d / 252)
        if d >= v[-1]:
            return F[-1] * (F[-1] / F[-2]) ** ((d - v[-1]) / (v[-1] - v[-2]))
        for k in range(len(v) - 1):
            if v[k] <= d <= v[k + 1]:
                return F[k] * (F[k + 1] / F[k]) ** ((d - v[k]) / (v[k + 1] - v[k]))
        raise AssertionError


def load_inputs():
    p = json.loads((ROOT / "tests/fixtures/legacy/inputs_planilha.json").read_text())
    di = FlatForward(p["di_curve_days_full"], [x / 100 for x in p["di_curve_pct"]])
    infl = FlatForward(p["inflation_curve_days_full"], [x / 100 for x in p["inflation_curve_pct_full"]])
    cds = FlatForward(p["cds_days"], [x / 10000 for x in p["cds_bps"]])
    return di, infl, cds


# ---------------------------------------------------------------- realizado
def parse_br(s: str) -> dt.date:
    d, m, y = s[:10].split("/")
    return dt.date(int(y), int(m), int(d))


def cdi_series() -> list[tuple[dt.date, float]]:
    raw = json.loads((ROOT / "tests/fixtures/f2/bcb_sgs_12_cdi_diario.json").read_text())
    return [(parse_br(r["data"]), float(r["valor"]) / 100) for r in raw]


def ipca_series() -> dict[tuple[int, int], float]:
    raw = json.loads((ROOT / "tests/fixtures/f2/bcb_sgs_433_ipca_mensal.json").read_text())
    out = {}
    for r in raw:
        d = parse_br(r["data"])
        out[(d.year, d.month)] = float(r["valor"]) / 100
    return out


def ipca_release_dates() -> dict[tuple[int, int], dt.date]:
    raw = json.loads((ROOT / "tests/fixtures/f2/ibge_calendario_2026.json").read_text())
    out = {}
    for it in raw["items"]:
        if it["titulo"] == IPCA_TITLE:
            key = (int(it["ano_referencia_inicio"]), int(it["mes_referencia_inicio"]))
            out[key] = parse_br(it["data_divulgacao"])
    return out


def last_ipca_month(t0: dt.date) -> tuple[int, int]:
    rel = ipca_release_dates()
    pub = [k for k, d in rel.items() if d <= t0]
    return max(pub)


def month_end(y: int, m: int) -> dt.date:
    nxt = dt.date(y + (m == 12), m % 12 + 1, 1)
    return nxt - dt.timedelta(days=1)


# ---------------------------------------------------------------- motor E8
def compute(variant: str = "A", infl_opt: str = "ii") -> dict:
    di, infl, cds = load_inputs()
    y0 = T0.year
    L = T0 if variant == "A" else prev_bd(T0)  # ultimo dia coberto pelo realizado do CDI
    dU = {Y: bd_open_closed(L, dt.date(Y, 12, 31)) for Y in [y0 - 1] + YEARS}
    dU[y0 - 1] = 0  # corte do ano anterior = origem

    # DI realizado
    cdi = [(d, r) for d, r in cdi_series() if d.year == y0 and d <= L]
    cdi_ytd = math.prod(1 + r for _, r in cdi) - 1

    # IPCA realizado
    ly, lm = last_ipca_month(T0)
    ipca = ipca_series()
    months = [(y0, m) for m in range(1, 13) if (y0, m) <= (ly, lm)]
    ipca_ytd = math.prod(1 + ipca[k] for k in months) - 1
    gap_origin = month_end(ly, lm)
    dI = {Y: bd_open_closed(gap_origin, dt.date(Y, 12, 31)) for Y in YEARS}
    n_gap = bd_open_closed(gap_origin, L)

    out: dict = {"meta": {
        "variant": variant, "infl_opt": infl_opt, "L": str(L), "dU": dU, "dI": dI,
        "n_gap": n_gap, "cdi_days": len(cdi), "cdi_first": str(cdi[0][0]), "cdi_last": str(cdi[-1][0]),
        "cdi_ytd": cdi_ytd, "ipca_months": months, "ipca_ytd": ipca_ytd, "last_ipca": (ly, lm),
    }, "rows": {}}

    for Y in YEARS:
        if Y == y0:
            di_r = (1 + cdi_ytd) * di.factor(dU[Y]) - 1
            if infl_opt == "i" or infl_opt == "ii":
                infl_r = (1 + ipca_ytd) * infl.factor(dI[Y]) - 1
            else:  # iii
                infl_r = (1 + ipca_ytd) * infl.factor(n_gap) * infl.factor(dU[Y]) - 1
            cds_rem = cds.factor(dU[Y]) - 1
            cds_ann = (1 + cds_rem) ** (252 / dU[Y]) - 1
            cds_r = cds_ann
        else:
            di_r = di.factor(dU[Y]) / di.factor(dU[Y - 1]) - 1
            if infl_opt == "i":
                infl_r = infl.factor(dI[Y]) / infl.factor(dI[Y - 1]) - 1
            else:
                infl_r = infl.factor(dU[Y]) / infl.factor(dU[Y - 1]) - 1
            cds_r = cds.factor(dU[Y]) / cds.factor(dU[Y - 1]) - 1
            cds_rem = cds_ann = None
        real = (1 + di_r) / (1 + infl_r) - 1
        out["rows"][Y] = {"di": di_r, "inflacao": infl_r, "cds": cds_r, "juro_real": real,
                          "cds_remaining": cds_rem, "cds_annualized": cds_ann}
    return out


def reprice_check() -> float:
    di, infl, cds = load_inputs()
    err = 0.0
    for c in (di, infl, cds):
        for v, s in zip(c.v, c.s):
            err = max(err, abs(c.factor(v) - (1 + s) ** (v / 252)), abs(c.factor_pow(v) - (1 + s) ** (v / 252)))
    return err


if __name__ == "__main__":
    import sys
    variant = sys.argv[1] if len(sys.argv) > 1 else "A"
    opt = sys.argv[2] if len(sys.argv) > 2 else "ii"
    res = compute(variant, opt)
    print(json.dumps(res["meta"], default=str, indent=1))
    print("reprice max err", reprice_check())
    print(f"{'ano':>5} {'DI':>20} {'Inflacao':>20} {'CDS':>20} {'Juro real':>20}")
    for Y, r in res["rows"].items():
        print(f"{Y:>5} {r['di']:>20.15f} {r['inflacao']:>20.15f} {r['cds']:>20.15f} {r['juro_real']:>20.15f}")
    r = res["rows"][2026]
    print("CDS 2026 remaining_period_accumulated", repr(r["cds_remaining"]), "annualized_rate", repr(r["cds_annualized"]))
    json.dump(res, open(Path(__file__).with_name(f"blind_{variant}_{opt}.json"), "w"), default=str, indent=1)
