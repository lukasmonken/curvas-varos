"""Configuração central: URLs, timeouts, retry, faixas plausíveis e limites de alerta."""

from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"


@dataclass(frozen=True)
class HttpConfig:
    connect_timeout_s: float = 10.0
    read_timeout_s: float = 60.0
    max_attempts: int = 4
    backoff_base_s: float = 2.0  # espera 2, 4, 8 s entre tentativas
    backoff_max_s: float = 30.0
    user_agent: str = "curvas-varos/0.1 (+pipeline de premissas; contato: equipe VAROS)"
    retry_statuses: tuple[int, ...] = (408, 429, 500, 502, 503, 504)


@dataclass(frozen=True)
class Urls:
    anbima_ettj_download: str = "https://www.anbima.com.br/informacoes/est-termo/CZ-down.asp"
    bcb_sgs: str = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{code}/dados"
    ibge_calendario: str = "https://servicodados.ibge.gov.br/api/v3/calendario/"


@dataclass(frozen=True)
class SgsSeries:
    """Séries do SGS/BCB usadas (E9)."""

    cdi_daily: int = 12  # % a.d., realizado do CORRIGIDO
    cdi_monthly: int = 4391  # % no mês
    selic_daily: int = 11  # % a.d.
    selic_monthly: int = 4390  # % no mês, realizado do LEGADO (Dashboard!L20:L31)
    ipca_monthly: int = 433  # % no mês
    ipca15_monthly: int = 7478  # % no mês (Forma A do IPCA-15, Q13)


@dataclass(frozen=True)
class PlausibleRanges:
    """Faixas para validação dos dados coletados (% a.a. ou % no mês)."""

    pre_pct: tuple[float, float] = (0.0, 60.0)
    real_pct: tuple[float, float] = (-5.0, 25.0)
    implied_inflation_pct: tuple[float, float] = (-5.0, 40.0)
    cdi_daily_pct: tuple[float, float] = (0.0, 0.2)
    ipca_monthly_pct: tuple[float, float] = (-3.0, 5.0)
    selic_monthly_pct: tuple[float, float] = (0.0, 5.0)
    min_ettj_vertices: int = 15  # a ANBIMA publica 19 (252 a 2520) para PREF e implícita


@dataclass(frozen=True)
class AlertConfig:
    max_daily_change_bps: float = 50.0  # seção 12: alerta, não bloqueia


@dataclass(frozen=True)
class Config:
    # Primeiro t0 do pipeline (o CDS manual começa em 29/09/2026): o modo de
    # recuperação não tenta datas anteriores, que nunca teriam CDS.
    pipeline_start: date | None = date(2026, 9, 29)
    http: HttpConfig = field(default_factory=HttpConfig)
    urls: Urls = field(default_factory=Urls)
    sgs: SgsSeries = field(default_factory=SgsSeries)
    ranges: PlausibleRanges = field(default_factory=PlausibleRanges)
    alerts: AlertConfig = field(default_factory=AlertConfig)


DEFAULT = Config()
