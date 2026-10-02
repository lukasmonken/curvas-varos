"""Schemas pydantic do pipeline (Parte 1, seções 7 e 11). Exportados para ``docs/schema.json``.

Todo número é finito: o schema recusa NaN e infinito (``allow_inf_nan=False``), e um
schema inválido bloqueia a publicação (seção 12). ``None`` significa valor
indisponível (por exemplo, ``#N/A`` do LEGADO na virada do ano) e sempre vem
acompanhado de alerta.
"""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.1"  # 1.1: realized.cdi_monthly


class _Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)


class SourceRecord(_Model):
    """Registro de uma fonte numa execução, com as quatro datas da seção 7."""

    source: str
    requested_date: date = Field(description="Data pedida à fonte")
    source_date: date | None = Field(description="Data econômica do dado (nunca posterior a t0)")
    publication_date: datetime | date | None = Field(
        description=(
            "Quando a fonte publicou o dado usado; null quando a fonte não informa "
            "(ANBIMA, SGS 12 e 4390, agenda do IBGE)"
        )
    )
    retrieved_at: datetime = Field(description="Quando o pipeline baixou")
    stale: bool = False
    fallback_reason: str | None = None
    url: str | None = None
    sha256: str | None = None
    raw_path: str | None = None


class Alert(_Model):
    level: Literal["info", "warning", "error"]
    code: str
    message: str
    source: str | None = None


class Metadata(_Model):
    as_of_date: date = Field(description="Data-base única da execução (t0)")
    code_version: str
    git_commit: str | None = Field(
        description='Hash do commit que gerou a saída ("-dirty" no fim: havia alterações '
        "locais fora de data/)"
    )
    schema_version: str = SCHEMA_VERSION
    default_mode: Literal["corrected", "legacy"] = "corrected"


class Vertex(_Model):
    days: int = Field(description="Prazo em dias úteis a partir de t0")
    rate: float = Field(description="Taxa spot ao ano, em decimal, base 252")


class CurvePoint(_Model):
    days: int
    rate: float = Field(description="Taxa ao ano, em decimal (spot no CORRIGIDO; diária no LEGADO)")
    factor: float = Field(description="Fator acumulado de t0 até ``days``", gt=0)


class CurveOut(_Model):
    name: Literal["di", "inflation", "cds"]
    source: str
    corrected_vertices: list[Vertex]
    legacy_vertices: list[Vertex]
    corrected_sample: list[CurvePoint]
    legacy_sample: list[CurvePoint]


class AnnualRow(_Model):
    year: int
    di: float | None = Field(description="Taxa do ano civil (no LEGADO, a do Dashboard)")
    inflation: float | None
    cds: float | None = Field(
        description=(
            "Taxa ao ano. No ano corrente do CORRIGIDO é ``annualized_rate``: a taxa "
            "anualizada só dos dias úteis restantes até 31/12 (E8.7)."
        )
    )
    real: float | None = Field(description="(1 + DI)/(1 + Inflação) − 1 (E8.8)")
    discount: float | None = Field(
        description=(
            "(1 + DI)(1 + CDS) − 1 (Q4). No ano corrente compõe o DI do ano civil com o "
            "CDS anualizado do período restante."
        )
    )


class CdsCurrentYear(_Model):
    annualized_rate: float
    remaining_period_accumulated: float
    business_days: int


class LegacyYtg(_Model):
    """Coluna "YTG" do Dashboard (Q4:Q6), no LEGADO diário. Acumulados, não anualizados."""

    di: float | None = Field(
        description="DI!S26: acumulado do início do trimestre q até 31/12, com o realizado de q"
    )
    inflation: float | None = Field(
        description="Inflação!E4 (= S26): acumulado do início do trimestre q até 31/12"
    )
    cds: float | None = Field(
        description="CDS!J9: acumulado só da curva no YTG, sem anualizar (E6.7)"
    )


class AnnualOut(_Model):
    corrected: list[AnnualRow]
    legacy: list[AnnualRow]
    corrected_cds_current_year: CdsCurrentYear
    legacy_ytg: LegacyYtg


class MonthlyValue(_Model):
    year: int
    month: int = Field(ge=1, le=12)
    value_pct: float
    release_date: date | None = None


class CdiRealized(_Model):
    start: date
    end_exclusive: date = Field(description="t0: o CDI realizado vai até a véspera (Q11-B)")
    business_days: int
    factor: float = Field(gt=0)
    last_observation: date | None


class RealizedOut(_Model):
    ipca_monthly: list[MonthlyValue] = Field(description="IPCA do ano corrente, com mês e ano")
    ipca_ytd: float
    ipca_rule: str = Field(description="Regra aplicada ao IPCA ainda não divulgado (E8.6)")
    ipca15_used: MonthlyValue | None
    cdi: CdiRealized
    cdi_monthly: list[MonthlyValue] = Field(
        default_factory=list,
        description=(
            "CDI realizado por mês do ano corrente, em % no mês, composto do CDI diário "
            "(SGS 12) de 1º/jan até a véspera de t0. O mês de t0 é parcial."
        ),
    )
    selic_monthly_legacy: list[MonthlyValue] = Field(
        description="Selic mensal usada pelo LEGADO (Dashboard!L20:L31), com mês e ano"
    )


class LegacyInputsOut(_Model):
    first_year: int
    month: int | None = Field(description="Mês do último IPCA no ano corrente (None = nenhum)")
    quarter: int | None
    ytg_days: int
    cds_ytg_days: int
    inflation_curve_pct: list[float]
    di_curve_pct: list[float]
    cds_bps: list[float]


class CorrectedInputsOut(_Model):
    year_end_business_days: list[int]
    inflation_gap_business_days: int
    interpolation: str
    gap_rule: str
    cdi_realized_factor: float
    ipca_realized_factor: float


class InputsOut(_Model):
    legacy: LegacyInputsOut
    corrected: CorrectedInputsOut


class ComparisonRow(_Model):
    """CORRIGIDO − LEGADO, em bps (None se o LEGADO está indisponível)."""

    year: int
    di_bps: float | None
    inflation_bps: float | None
    cds_bps: float | None
    real_bps: float | None
    discount_bps: float | None


class RunOutput(_Model):
    metadata: Metadata
    sources: list[SourceRecord]
    inputs: InputsOut
    curves: list[CurveOut]
    annual: AnnualOut
    realized: RealizedOut
    comparison: list[ComparisonRow]
    alerts: list[Alert]
