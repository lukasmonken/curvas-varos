"""Figuras Plotly do site, no tema da identidade visual (Q5).

``THEME`` espelha ``static/tokens.css`` (conferido em ``tests/test_site.py``). Todos os
traços saem prontos daqui, com ``meta`` = {mode, role, date}; o ``site.js`` só alterna
a visibilidade (``Plotly.restyle``) conforme o modo e a data de comparação.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Any, Literal

import plotly.graph_objects as go

from curvas.models import CurvePoint, RunOutput, Vertex
from curvas.site.view import MODES, day, vertex_factor

THEME: dict[str, str] = {
    "font-sans": (
        '"Instrument Sans", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif'
    ),
    "font-mono": "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace",
    "bg": "#131313",
    "surface": "#1C1D1F",
    "text": "#E2E5EB",
    "text-2": "#878D96",
    "axis": "#C6CAD2",
    "series-1": "#12D8B2",
    "series-2": "#43AF43",
    "series-3": "#239B84",
    "series-4": "#296055",
    "ok": "#43AF43",
    "stale": "#E0A526",
    "error": "#E5534B",
}

CONFIG: dict[str, Any] = {
    "responsive": True,
    "displaylogo": False,
    # O plotly.js liga por padrão o botão "Share chart...", que manda a figura inteira
    # (todos os traços, até os ocultos) para o Plotly Cloud.
    "showSendToCloud": False,
    "modeBarButtonsToRemove": ["select2d", "lasso2d"],
}
HEIGHT = "360px"
# A linha vai até o fim da grade de amostra (2646 d.u., 2036); o vértice de 20A do
# CDS (5040 d.u.) só serve para interpolar e aparece na tabela.
MAX_DAYS = 2646
Measure = Literal["rate", "factor"]


def _rgb(color: str) -> tuple[int, int, int]:
    h = color.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def rgba(color: str, alpha: float) -> str:
    r, g, b = _rgb(color)
    return f"rgba({r},{g},{b},{alpha})"


RAMP = (THEME["text"], THEME["series-1"], THEME["series-2"], THEME["series-3"])


def ramp(n: int, anchors: Sequence[str] = RAMP) -> list[str]:
    """``n`` cores interpoladas entre as âncoras (anos próximos mais claros)."""
    points = [_rgb(c) for c in anchors]
    out = []
    for i in range(n):
        t = (i / (n - 1) if n > 1 else 0.0) * (len(points) - 1)
        k = min(int(t), len(points) - 2)
        a, b, f = points[k], points[k + 1], t - k
        r, g, bl = (round(x + (y - x) * f) for x, y in zip(a, b, strict=True))
        out.append(f"#{r:02X}{g:02X}{bl:02X}")
    return out


def _axis(title: str, **kw: Any) -> dict[str, Any]:
    return {
        "title": {"text": title, "font": {"color": THEME["text-2"], "size": 12}},
        "color": THEME["axis"],
        "gridcolor": rgba(THEME["text-2"], 0.22),
        "linecolor": rgba(THEME["text-2"], 0.5),
        "zeroline": False,
        "automargin": True,
        **kw,
    }


# Legenda presa ao pé do contêiner, não à área do gráfico: no celular ela quebra em várias
# linhas e, ancorada na área (y negativo em "paper"), cobria o título do eixo X. Com
# yref="container", o Plotly reserva a altura dela na margem de baixo.
LEGEND: dict[str, Any] = {
    "orientation": "h",
    "x": 0,
    "xanchor": "left",
    "y": 0,
    "yref": "container",
    "yanchor": "bottom",
    "font": {"color": THEME["text"]},
}


def _layout(**kw: Any) -> dict[str, Any]:
    return {
        "template": "none",
        "paper_bgcolor": THEME["bg"],
        "plot_bgcolor": THEME["bg"],
        "font": {"family": THEME["font-sans"], "color": THEME["text"], "size": 13},
        "separators": ",.",
        "margin": {"l": 8, "r": 8, "t": 8, "b": 8},
        "hovermode": "x unified",
        "hoverlabel": {
            "bgcolor": THEME["surface"],
            "bordercolor": THEME["text-2"],
            "font": {"family": THEME["font-sans"], "color": THEME["text"]},
        },
        "legend": LEGEND,
        **kw,
    }


def to_html(fig: go.Figure, div_id: str) -> str:
    """HTML do gráfico, sem o plotly.js (servido uma vez em ``assets/plotly.min.js``)."""
    html: str = fig.to_html(
        full_html=False,
        include_plotlyjs=False,
        div_id=div_id,
        config=CONFIG,
        default_height=HEIGHT,
        default_width="100%",
    )
    return html


def _r(x: float | None) -> float | None:
    """Arredonda para a serialização (1e-10 basta para taxa e fator): páginas menores."""
    return None if x is None else round(x, 10)


@dataclass(frozen=True)
class CurveSpec:
    tick: str  # formato d3 do eixo de taxa
    hover: str


CURVE_SPECS = {
    "di": CurveSpec(".1%", ".2%"),
    "inflation": CurveSpec(".1%", ".2%"),
    "cds": CurveSpec(".2%", ".4%"),
}


def curve_figure(
    name: str,
    outputs: Sequence[RunOutput],
    t0: date,
    *,
    measure: Measure,
    default_mode: str,
) -> str:
    """Vértices (pontos) e curva interpolada (linha) de t0 e das datas de comparação.

    ``div_id`` fixo: ``grafico-<curva>-taxa`` ou ``grafico-<curva>-fator``.
    """
    spec = CURVE_SPECS[name]
    fmt = spec.hover if measure == "rate" else ".6f"
    fig = go.Figure()
    ordered = sorted(outputs, key=lambda o: (o.metadata.as_of_date != t0, o.metadata.as_of_date))
    for mode, mode_label in MODES:
        for out in ordered:
            curve = next(c for c in out.curves if c.name == name)
            as_of = out.metadata.as_of_date
            base = as_of == t0
            color = THEME["series-1"] if base else THEME["text-2"]
            label = day(as_of)
            meta = {"mode": mode, "role": "base" if base else "compare", "date": as_of.isoformat()}
            visible = base and mode == default_mode
            sample: Sequence[CurvePoint]
            vertices: Sequence[Vertex]
            if mode == "corrected":
                sample, vertices = curve.corrected_sample, curve.corrected_vertices
            else:
                sample, vertices = curve.legacy_sample, curve.legacy_vertices
            points = [p for p in sample if p.days <= MAX_DAYS]
            vertices = [v for v in vertices if v.days <= MAX_DAYS]
            fig.add_trace(
                go.Scatter(
                    x=[p.days for p in points],
                    y=[_r(p.rate if measure == "rate" else p.factor) for p in points],
                    mode="lines",
                    name=f"{label}: curva ({mode_label})",
                    legendgroup=f"{mode}-{as_of}",
                    line={"color": color, "width": 2, "dash": "solid" if base else "dash"},
                    hovertemplate=f"%{{x:,d}} d.u.: %{{y:{fmt}}}",
                    meta=meta,
                    visible=visible,
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=[v.days for v in vertices],
                    y=[_r(v.rate if measure == "rate" else vertex_factor(v)) for v in vertices],
                    mode="markers",
                    name=f"{label}: vértices",
                    legendgroup=f"{mode}-{as_of}",
                    marker={
                        "color": color,
                        "size": 8,
                        "symbol": "circle" if base else "circle-open",
                        "line": {"color": color, "width": 1.5},
                    },
                    hovertemplate=f"vértice de %{{x:,d}} d.u.: %{{y:{fmt}}}",
                    meta=meta,
                    visible=visible,
                )
            )
    y_title = "Taxa (a.a.)" if measure == "rate" else "Fator de t0 até o prazo"
    y_tick = spec.tick if measure == "rate" else ".2f"
    fig.update_layout(
        _layout(
            hovermode="closest",
            xaxis=_axis("Prazo (dias úteis)", range=[0, MAX_DAYS + 60], tickformat=",d"),
            yaxis=_axis(y_title, tickformat=y_tick),
        )
    )
    return to_html(fig, f"grafico-{name}-{'taxa' if measure == 'rate' else 'fator'}")


def history_figure(
    dates: Sequence[date],
    values: Mapping[str, Mapping[int, Sequence[float | None]]],
    *,
    default_mode: str,
    tick: str,
    hover: str,
    div_id: str,
) -> str:
    """Uma linha por ano civil ao longo das datas-base; ``values[mode][ano]``."""
    fig = go.Figure()
    x = [day(d) for d in dates]  # eixo de categorias: uma posição por data-base
    for mode, _ in MODES:
        years = sorted(values[mode])
        for color, year in zip(ramp(len(years)), years, strict=True):
            fig.add_trace(
                go.Scatter(
                    x=x,
                    y=[_r(v) for v in values[mode][year]],
                    mode="lines+markers",
                    name=str(year),
                    line={"color": color, "width": 2},
                    marker={"color": color, "size": 6},
                    hovertemplate=f"%{{y:{hover}}}",
                    meta={"mode": mode, "role": "base"},
                    visible=mode == default_mode,
                )
            )
    fig.update_layout(
        _layout(
            xaxis=_axis("Data-base", type="category"),
            yaxis=_axis("Taxa (a.a.)", tickformat=tick),
        )
    )
    return to_html(fig, div_id)
