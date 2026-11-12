"""Tablero Streamlit del portafolio de bioprocesos GxP (FASE 4 de 4).

Dashboard interactivo con 5 pestanas que consume EXCLUSIVAMENTE las funciones
reales de src/: ningun KPI se estima ni se fija en el tablero. Se lanza con:

    streamlit run app/dashboard.py

Autor del portafolio: Alejandro Timaran, Ingenieria Biologica, UNAL.
"""

import ast
import copy
import hashlib
import inspect
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

# Inserta la raiz del repositorio en sys.path para que 'from src...' resuelva
# cuando el script se lanza como 'streamlit run app/dashboard.py' desde la raiz.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.models import ProcessDescription
from src.bioreactor_twin import (
    compute_split_range_ph_actuators,
    get_temperature_setpoint,
    check_safety_interlocks,
    simulate_cho_fed_batch,
)
from src.amab_design_space import (
    KLA_COEFF,
    KLA_EXP_PV,
    KLA_EXP_VS,
    evaluate_amab_design_space,
    compute_scale_up_engineering,
)
from src.thermal_vtb_mkt import (
    VTB_CALIBRATION_TABLE,
    calculate_mkt_celsius,
    apply_vtb_filter,
    analyze_fft_nyquist,
)
from src.spc_six_sigma import (
    GORSKY_TABLE_6_1_TORQUE_N10,
    GORSKY_TABLE_6_2_TORQUE_N30,
    compute_iso16269_tolerance_interval,
    compute_process_capability,
    compute_moving_range_summary,
    compare_bioreactor_equivalence_ttest,
)
from src.audit_trail_part11 import AuditTrailLogger


st.set_page_config(
    page_title="Portafolio Bioprocesos GxP | Alejandro Timaran UNAL",
    page_icon="B",
    layout="wide",
    initial_sidebar_state="collapsed",
)


# ---------------------------------------------------------------------------
# Capa visual. No calcula nada: tema, tipografia, leyendas y distribucion.
# Claro y noche comparten los mismos significados de color.
# ---------------------------------------------------------------------------
def _is_night() -> bool:
    """Lee el tema que el usuario elige en el menu de tres puntos. No pinta un control propio."""
    try:
        kind = st.context.theme.type
    except Exception:
        return False
    return kind == "dark"


def _palette(night: bool) -> dict:
    """Naranja y azul para series. Rojo y verde solo para no/si. Siempre saturados."""
    if not night:
        return {
            "bg": "#F3EFE7",
            "bg_fade": "rgba(29, 78, 137, 0.05)",
            "paper": "rgba(251,249,244,0.94)",
            "ink": "#1A2421",
            "muted": "#3E4744",
            "card": "#FBF9F4",
            "line": "#E0D8C8",
            "grid": "#E4DCCE",
            "axis": "#CDBFA8",
            "code_bg": "#E7E1D6",
            "static": "#C4271A",
            "closed": "#1D4E89",
            "air": "#1C1917",
            "v1": "#1D4E89",
            "v20": "#C2410C",
            "v300": "#047857",
            "limit": "#C4271A",
            "mean": "#047857",
            "heat_no": "#C4271A",
            "heat_yes": "#067647",
            "tip_bg": "#1A2421",
            "tip_fg": "#F7F4EE",
            "chip_ok": "#067647",
            "chip_bad": "#C4271A",
            "chip_warn": "#B45309",
        }
    return {
        "bg": "#101614",
        "bg_fade": "rgba(77, 163, 255, 0.08)",
        "paper": "rgba(16, 22, 20, 0.96)",
        "ink": "#F4F0E8",
        "muted": "#E4DDD2",
        "card": "#1B2420",
        "line": "#31403A",
        "grid": "#2A3832",
        "axis": "#8A948E",
        "code_bg": "#24302B",
        "static": "#FF5C4D",
        "closed": "#4DA3FF",
        "air": "#F4F0E8",
        "v1": "#4DA3FF",
        "v20": "#FF8A3D",
        "v300": "#3DDC97",
        "limit": "#FF5C4D",
        "mean": "#3DDC97",
        "heat_no": "#FF5C4D",
        "heat_yes": "#2FBF71",
        "tip_bg": "#F4F0E8",
        "tip_fg": "#101614",
        "chip_ok": "#067647",
        "chip_bad": "#C4271A",
        "chip_warn": "#B45309",
    }


def _css(c: dict) -> str:
    return f"""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap');
    html, body, [class*="css"] {{
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    }}
    .block-container {{
        padding-top: 1.15rem;
        padding-bottom: 3rem;
        max-width: 1180px;
    }}
    .bp-mast {{
        border-top: 3px solid {c["closed"]};
        border-bottom: 1px solid {c["line"]};
        padding: 0.9rem 0 0.8rem;
        margin: 0 0 0.8rem;
    }}
    .bp-kicker, .bp-band {{
        margin: 0 0 0.3rem;
        font-size: 0.72rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: inherit !important;
        font-weight: 500;
    }}
    .bp-band {{
        margin: 1.15rem 0 0.4rem;
        padding-top: 0.55rem;
        border-top: 1px solid {c["line"]};
    }}
    .bp-mast h1 {{
        font-family: Newsreader, Georgia, serif;
        font-weight: 500;
        font-size: 2.2rem;
        line-height: 1.08;
        letter-spacing: -0.02em;
        color: inherit !important;
        margin: 0;
    }}
    .bp-lead {{
        margin: 0.45rem 0 0;
        max-width: 68ch;
        color: inherit !important;
        font-size: 1rem;
        line-height: 1.45;
    }}
    .bp-note {{
        margin: 0.05rem 0 0.55rem;
        color: inherit !important;
        font-size: 0.86rem;
        line-height: 1.35;
    }}
    .bp-lead code {{
        font-family: "IBM Plex Mono", ui-monospace, monospace;
        font-size: 0.86em;
        background: {c["code_bg"]};
        color: {c["ink"]};
        padding: 0.05rem 0.3rem;
    }}
    .bp-swatch {{
        display: inline-block;
        width: 0.8rem;
        height: 0.8rem;
        margin: 0 0.3rem 0 0.15rem;
        vertical-align: -0.1rem;
        border: 1px solid {c["ink"]};
    }}
    h2, h3 {{
        font-family: Newsreader, Georgia, serif;
        letter-spacing: -0.015em;
        color: {c["ink"]};
    }}
    div[data-testid="stMetric"] {{
        background: {c["card"]};
        border: 1px solid {c["line"]};
        border-top: 3px solid {c["closed"]};
        padding: 0.7rem 0.85rem 0.5rem;
    }}
    div[data-testid="stMetricLabel"] p {{
        color: {c["muted"]} !important;
    }}
    /* Etiquetas largas: se parten en dos lineas en vez de cortarse con "...". */
    [data-testid="stMetricLabel"],
    [data-testid="stMetricLabel"] * {{
        white-space: normal !important;
        overflow: visible !important;
        text-overflow: clip !important;
    }}
    div[data-testid="stMetricValue"] {{
        font-family: "IBM Plex Mono", ui-monospace, monospace;
        color: {c["ink"]};
        font-size: clamp(1.55rem, 2.6vw, 2.25rem);
    }}
    .bp-mono {{
        font-family: "IBM Plex Mono", ui-monospace, monospace;
        font-size: 0.86rem;
        word-break: break-all;
    }}
    .bp-chip, .bp-banner {{
        border-radius: 0;
        color: #FFFFFF;
    }}
    .bp-chip {{
        padding: 0.6rem 0.7rem 0.5rem;
        min-height: 4.4rem;
        margin: 0 0 0.35rem;
    }}
    .bp-chip span {{
        display: block;
        font-size: 0.68rem;
        letter-spacing: 0.05em;
        text-transform: uppercase;
        color: #FFFFFF !important;
    }}
    .bp-chip strong {{
        display: block;
        margin-top: 0.2rem;
        font-size: 1.15rem;
        line-height: 1.1;
        color: #FFFFFF !important;
    }}
    .bp-chip em {{
        display: block;
        margin-top: 0.15rem;
        font-style: normal;
        font-family: "IBM Plex Mono", ui-monospace, monospace;
        font-size: 0.75rem;
        color: #FFFFFF !important;
    }}
    .bp-banner {{
        padding: 0.65rem 0.8rem;
        margin: 0.35rem 0 0.6rem;
        font-weight: 500;
        color: #FFFFFF !important;
    }}
    .stTabs [data-baseweb="tab-list"] {{
        gap: 0;
        border-bottom: 1px solid {c["line"]};
    }}
    .stTabs [aria-selected="true"] {{
        border-bottom: 2px solid {c["closed"]};
    }}
    </style>
    """


def _band(text: str) -> None:
    st.markdown(f'<p class="bp-band">{text}</p>', unsafe_allow_html=True)


def _leyenda(text: str) -> None:
    st.markdown(f'<p class="bp-note">{text}</p>', unsafe_allow_html=True)


def _chip(col, label: str, good: bool, word: str, detail: str) -> None:
    bg = P["chip_ok"] if good else P["chip_bad"]
    html = (
        f'<div class="bp-chip" style="background:{bg};color:#FFFFFF">'
        f'<span style="color:#FFFFFF">{label}</span>'
        f'<strong style="color:#FFFFFF">{word}</strong>'
        f'<em style="color:#FFFFFF">{detail}</em></div>'
    )
    with col:
        st.markdown(html, unsafe_allow_html=True)


def _banner(kind: str, text: str) -> None:
    bg = {"ok": P["chip_ok"], "bad": P["chip_bad"], "warn": P["chip_warn"]}[kind]
    st.markdown(
        f'<div class="bp-banner" style="background:{bg};color:#FFFFFF">{text}</div>',
        unsafe_allow_html=True,
    )


P = _palette(_is_night())
st.markdown(_css(P), unsafe_allow_html=True)
st.markdown(
    """
    <div class="bp-mast">
      <p class="bp-kicker">Ingenieria Biologica · Universidad Nacional de Colombia</p>
      <h1>Control y validacion de bioprocesos</h1>
      <p class="bp-lead">Alejandro Timaran. Tablero sobre las funciones reales de <code>src/</code>.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def _apply_figure(fig, legend_rows=None):
    """Unifica fondo, ejes y tipografia de Plotly sin tocar los datos.

    La leyenda va DEBAJO del grafico (horizontal, anclada al contenedor) para que
    nunca se monte sobre el titulo ni sobre las anotaciones de lineas verticales.
    El margen inferior y la altura crecen segun las filas de leyenda estimadas.
    """
    height = fig.layout.height
    n_legend = sum(
        1 for tr in fig.data
        if tr.type in ("scatter", "histogram", "bar") and tr.showlegend is not False
    )
    if legend_rows is None:
        legend_rows = 0 if len(fig.data) <= 1 else math.ceil(n_legend / 2)
    legend_px = 24 * legend_rows
    fig.update_layout(
        template="plotly_white",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor=P["paper"],
        font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", color=P["ink"], size=13),
        title=dict(
            font=dict(family="Newsreader, Georgia, serif", size=18, color=P["ink"]),
            x=0,
            xanchor="left",
        ),
        legend=dict(
            orientation="h",
            yref="container",
            yanchor="bottom",
            y=0,
            xanchor="left",
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12, color=P["ink"]),
        ),
        margin=dict(l=52, r=20, t=72, b=58 + legend_px),
        hoverlabel=dict(
            bgcolor=P["tip_bg"],
            font=dict(color=P["tip_fg"], family="IBM Plex Sans, sans-serif"),
        ),
    )
    fig.update_xaxes(
        showgrid=True, gridcolor=P["grid"], zeroline=False,
        linecolor=P["axis"], tickfont=dict(size=12, color=P["ink"]),
        title_font=dict(size=13, color=P["ink"]),
    )
    fig.update_yaxes(
        showgrid=True, gridcolor=P["grid"], zeroline=False,
        linecolor=P["axis"], tickfont=dict(size=12, color=P["ink"]),
        title_font=dict(size=13, color=P["ink"]),
    )
    if height:
        fig.update_layout(height=height + legend_px)
    fig.update_annotations(font_color=P["ink"])
    return fig


ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OQ_LOG_REL = os.path.join("docs", "04_Automated_OQ_Execution_Log.md")
OQ_LOG_PATH = os.path.join(ROOT_DIR, OQ_LOG_REL)
TESTS_DIR = os.path.join(ROOT_DIR, "tests")
OQ_TEST_FILE = os.path.join(TESTS_DIR, "test_csa_oq_validation.py")
CONFTEST_PATH = os.path.join(TESTS_DIR, "conftest.py")


# ---------------------------------------------------------------------------
# Formato y graficos compartidos. Solo dan formato a valores que ya vienen de src/.
# ---------------------------------------------------------------------------
def _fmt_mass(mass_g: float, in_kg: bool, signed: bool = False) -> str:
    """Masa en g o kg segun la escala. No calcula nada nuevo."""
    sign = "+" if signed else ""
    if in_kg:
        return f"{mass_g / 1000.0:{sign},.3f} kg"
    return f"{mass_g:{sign},.3f} g"


def _fmt_volume(volume_L: float, signed: bool = False) -> str:
    """Volumen en mL por debajo de 1 L, en L por encima."""
    sign = "+" if signed else ""
    if abs(volume_L) < 1.0:
        return f"{volume_L * 1000.0:{sign},.1f} mL"
    return f"{volume_L:{sign},.3f} L"


def _pct_gain(new: float, ref: float) -> float:
    return (new - ref) / ref * 100.0 if ref > 0 else float("nan")


def _bolus_days(res: dict) -> list[float]:
    """Dias en que V(t) del modelo sube: los bolos de feed que aplico simulate_cho_fed_batch."""
    vol = res["volume_L"]
    t = res["time_days"]
    return [t[i] for i in range(1, len(vol)) if vol[i] > vol[i - 1]]


def _compare_fig(t_s, y_s, t_c, y_c, title, ytitle, height=300, bolus_days=(), line_shape="linear"):
    """Figura estatico (rojo, discontinuo) vs lazo cerrado (azul) con bolos opcionales."""
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=t_s, y=y_s, mode="lines", name="Static Recipe", line_shape=line_shape,
            line=dict(color=P["static"], dash="dash", width=2.6),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=t_c, y=y_c, mode="lines", name="Closed-Loop Digital Twin", line_shape=line_shape,
            line=dict(color=P["closed"], width=2.6),
        )
    )
    for d in bolus_days:
        fig.add_vline(
            x=d, line=dict(color=P["axis"], dash="dot", width=1.4),
            annotation_text=f"d{d:g}", annotation_position="top",
            annotation_font_size=10,
        )
    fig.update_layout(title=title, xaxis_title="Tiempo (d)", yaxis_title=ytitle, height=height)
    return _apply_figure(fig)


tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "1. Gemelo Digital CHO-K1",
        "2. Espacio de Diseno A-Mab y Escalamiento",
        "3. Cadena de Frio: MKT, VTB y FFT",
        "4. SPC Six Sigma",
        "5. Gobernanza GxP y OQ",
    ]
)


# ---------------------------------------------------------------------------
# TAB 1 - Gemelo Digital CHO-K1 Fed-Batch y Lazo Cerrado (Bionova / Ark)
# ---------------------------------------------------------------------------
with tab1:
    st.header("Gemelo Digital CHO-K1 Fed-Batch y Lazo Cerrado (Bionova / Ark)")
    st.markdown(
        "Comparacion en vivo entre la receta **estatica** (Static Recipe) y el "
        "**gemelo digital de lazo cerrado** (Closed-Loop Digital Twin). Todos los "
        "indicadores salen de `simulate_cho_fed_batch`, incluido el balance de "
        "volumen variable V(t)."
    )

    with st.container(border=True):
        _band("Parametros del cultivo")
        g1, g2, g3 = st.columns(3)
        with g1:
            power_density_W_m3 = st.slider(
                "Densidad de potencia P/V (W/m3)",
                min_value=2.0,
                max_value=100.0,
                value=30.0,
                step=0.5,
                help="Bionova usa 19 y 30 W/m3 (Ref. 2). 47.6 W/m3 es el P/V maximo demostrado aceptable a 2 L (A-Mab Tabla 3.22), criterio conservador, no umbral de dano. Bounds [2, 100].",
            )
            _leyenda("A la derecha, hasta 30 W/m3, el titulo sube un poco. Por encima de 47.6 W/m3 salta la alarma de cizalla aunque el sparge sea bajo (P/V > 47.6 O sparge > 0.15). Cada exceso sube kd y baja qp de forma continua: caen viabilidad y titulo.")
        with g2:
            temp_shift_day = st.slider(
                "Dia del cambio termico (d)",
                min_value=1.0,
                max_value=14.0,
                value=7.0,
                step=0.5,
                help="Bounds temp_shift_day [1, 14] d.",
            )
            _leyenda("A la izquierda el cultivo pasa antes a la temperatura de produccion y crece mas lento. A la derecha crece mas tiempo a la temperatura inicial.")
        with g3:
            sparge_vvm = st.slider(
                "Flujo de burbujeo sparge (vvm)",
                min_value=0.0,
                max_value=1.0,
                value=0.10,
                step=0.01,
                help="Bounds sparge_vvm [0, 1]. El umbral de 0.15 vvm es un supuesto de modelado (sin fuente).",
            )
            _leyenda("Hasta 0.15 vvm el sparge no agrega cizalla. Por encima de 0.15 salta la alarma aunque P/V sea bajo (P/V > 47.6 O sparge > 0.15), y el exceso sube kd y baja qp de forma continua: caen viabilidad y titulo. Si ambos se pasan, el efecto se combina.")

        _band("Volumen y controlador de pH")
        g4, g5 = st.columns(2)
        with g4:
            vessel_volume_L = st.slider(
                "Volumen nominal del biorreactor (L)",
                min_value=0.25,
                max_value=35000.0,
                value=2.0,
                step=0.25,
                help="Bounds ProcessDescription: (0, 35000] L. El modelo arranca con V_0 = 70 % del nominal y nunca supera el volumen del recipiente. La ley de kLa del gemelo esta anclada en el punto de 15,000 L de A-Mab; en 0.25 L y 2 L es una extrapolacion.",
            )
            _leyenda("A la derecha hay mas litros: suben la masa de anticuerpo, el feed y V(t). Los g/L de las curvas no cambian.")
        with g5:
            ph_deadband = st.slider(
                "Banda muerta de pH",
                min_value=0.01,
                max_value=1.0,
                value=0.20,
                step=0.01,
                help="Bounds ph_deadband (0, 1]. Minimo 0.01 para evitar ValidationError.",
            )
            _leyenda("A la derecha la banda es mas ancha y el controlador actua mas tarde. A la izquierda actua ante un desvio chico. Gobierna el controlador split-range del expansor inferior.")

    shared = dict(
        vessel_volume_L=vessel_volume_L,
        power_density_W_m3=power_density_W_m3,
        temp_shift_day=temp_shift_day,
        ph_deadband=ph_deadband,
        sparge_vvm=sparge_vvm,
        # DO set-point from the scale-up slider (key "do_setpoint_pct"); Streamlit
        # stores it in session_state before each rerun, so both twin runs use it.
        do_setpoint_pct=float(
            st.session_state.get("do_setpoint_pct", ProcessDescription().do_setpoint_pct)
        ),
    )
    static_res = simulate_cho_fed_batch(ProcessDescription(mode="static", **shared))
    closed_res = simulate_cho_fed_batch(ProcessDescription(mode="closed_loop", **shared))

    # Todos los KPI se leen de los dicts del modelo. Nada se estima en el tablero.
    s_titer = static_res["final_titer_g_L"]
    c_titer = closed_res["final_titer_g_L"]
    s_via = static_res["final_viability_pct"]
    c_via = closed_res["final_viability_pct"]
    s_mass = static_res["harvested_mass_g"]
    c_mass = closed_res["harvested_mass_g"]
    s_feed = static_res["total_feed_volume_L"]
    c_feed = closed_res["total_feed_volume_L"]
    titer_gain_pct = _pct_gain(c_titer, s_titer)
    mass_gain_pct = _pct_gain(c_mass, s_mass)
    mass_in_kg = max(s_mass, c_mass) >= 1000.0
    mass_unit = "kg" if mass_in_kg else "g"

    clipped = {n: r for n, r in (("receta estatica", static_res), ("lazo cerrado", closed_res))
               if r["bolus_clipped_alarm"]}
    if clipped:
        st.warning(
            "Volumen util al 100 %: el recipiente se lleno y los bolos fueron recortados ("
            + "; ".join(f"{n}: {r['n_bolus_clipped']} bolos, {r['clipped_volume_L']:.4f} L no inyectados"
                        for n, r in clipped.items())
            + ")."
        )

    _band("Cosecha al dia final: receta estatica vs lazo cerrado")
    col_s, col_c = st.columns(2)
    with col_s:
        with st.container(border=True):
            st.markdown("**Static Recipe**")
            r1 = st.columns(2)
            r1[0].metric("Titulo final (g/L)", f"{s_titer:.4f}")
            r1[1].metric("Viabilidad final (%)", f"{s_via:.2f}")
            r2 = st.columns(2)
            r2[0].metric(
                f"Masa cosechada de mAb ({mass_unit})",
                _fmt_mass(s_mass, mass_in_kg),
                help="harvested_mass_g = final_titer_g_L * final_volume_L (modelo).",
            )
            r2[1].metric(
                "Volumen de feed acumulado",
                _fmt_volume(s_feed),
                help="total_feed_volume_L = final_volume_L - V_0 (modelo).",
            )
    with col_c:
        with st.container(border=True):
            st.markdown("**Closed-Loop Digital Twin**")
            r1 = st.columns(2)
            r1[0].metric(
                "Titulo final (g/L)", f"{c_titer:.4f}", delta=f"{c_titer - s_titer:+.4f} g/L"
            )
            r1[1].metric(
                "Viabilidad final (%)", f"{c_via:.2f}", delta=f"{c_via - s_via:+.2f} pp"
            )
            r2 = st.columns(2)
            r2[0].metric(
                f"Masa cosechada de mAb ({mass_unit})",
                _fmt_mass(c_mass, mass_in_kg),
                delta=_fmt_mass(c_mass - s_mass, mass_in_kg, signed=True),
                help="harvested_mass_g = final_titer_g_L * final_volume_L (modelo).",
            )
            r2[1].metric(
                "Volumen de feed acumulado",
                _fmt_volume(c_feed),
                delta=_fmt_volume(c_feed - s_feed, signed=True),
                delta_color="off",
                help="total_feed_volume_L = final_volume_L - V_0 (modelo).",
            )

    k1, k2, k3, k4 = st.columns(4)
    k1.metric(
        "Ganancia real de titulo (%)",
        f"{titer_gain_pct:+.2f}",
        help="(closed.final_titer_g_L - static.final_titer_g_L) / static.final_titer_g_L * 100",
    )
    k2.metric(
        "Ganancia de masa cosechada (%)",
        f"{mass_gain_pct:+.2f}",
        help="(closed.harvested_mass_g - static.harvested_mass_g) / static.harvested_mass_g * 100",
    )
    k3.metric("Volumen final lazo cerrado", _fmt_volume(closed_res["volume_L"][-1]))
    k4.metric("VCD pico lazo cerrado (1e6 cel/mL)", f"{closed_res['peak_vcd']:.2f}")

    _band("Balance de volumen fed-batch y masa acumulada")
    bolus = _bolus_days(closed_res)
    vc1, vc2 = st.columns(2)
    with vc1:
        st.plotly_chart(
            _compare_fig(
                static_res["time_days"], static_res["volume_L"],
                closed_res["time_days"], closed_res["volume_L"],
                "Volumen liquido V(t)", "Volumen (L)", height=340,
                bolus_days=bolus, line_shape="hv",
            ),
            width="stretch",
        )
    with vc2:
        div = 1000.0 if mass_in_kg else 1.0
        s_mass_curve = [tt * vv / div for tt, vv in zip(static_res["titer_g_L"], static_res["volume_L"])]
        c_mass_curve = [tt * vv / div for tt, vv in zip(closed_res["titer_g_L"], closed_res["volume_L"])]
        st.plotly_chart(
            _compare_fig(
                static_res["time_days"], s_mass_curve,
                closed_res["time_days"], c_mass_curve,
                "Masa acumulada de IgG = titulo(t) x V(t)", f"Masa de IgG ({mass_unit})",
                height=340, bolus_days=bolus,
            ),
            width="stretch",
        )
    _leyenda(
        "Lineas punteadas: dias en que V(t) del modelo sube por un bolo de feed "
        f"({', '.join(f'd{d:g}' for d in bolus)}). El escalon de volumen diluye el titulo, "
        "pero la masa de IgG sigue creciendo. El slider de volumen escala V(t) y la masa; "
        "los g/L no cambian."
    )

    _band("Trayectorias de concentracion")
    traj = [
        ("vcd", "VCD", "VCD (1e6 cel/mL)"),
        ("viability_pct", "Viabilidad", "Viabilidad (%)"),
        ("glucose_g_L", "Glucosa", "Glucosa (g/L)"),
        ("lactate_g_L", "Lactato", "Lactato (g/L)"),
        ("titer_g_L", "Titulo de mAb", "Titulo (g/L)"),
        ("temp_C", "Setpoint de temperatura", "Temperatura (C)"),
    ]
    for row_start in range(0, len(traj), 2):
        cols = st.columns(2)
        for slot, (key, title, ytitle) in zip(cols, traj[row_start:row_start + 2]):
            with slot:
                st.plotly_chart(
                    _compare_fig(
                        static_res["time_days"], static_res[key],
                        closed_res["time_days"], closed_res[key],
                        title, ytitle, height=300,
                        line_shape="hv" if key == "temp_C" else "linear",
                    ),
                    width="stretch",
                )

    with st.container(border=True):
        _band("Limpieza y esterilizacion")
        st.subheader("Panel de estado de interlocks de seguridad")
        ic1, ic2, ic3, ic4 = st.columns(4)
        with ic1:
            cip_valve_requested = st.toggle("CIP solicitado (valvula)", value=False)
            _leyenda("Encendido con lote activo: la valvula de limpieza queda bloqueada.")
        with ic2:
            cip_pipe_velocity_m_s = st.slider(
                "Velocidad de tuberia CIP (m/s)",
                min_value=0.5,
                max_value=3.0,
                value=1.52,
                step=0.01,
                help="ASME BPE-2014: cumple si >= 1.52 m/s (5 ft/s).",
            )
            _leyenda("A la izquierda de 1.52 m/s la limpieza no cumple.")
        with ic3:
            sip_temp_C = st.slider(
                "Temperatura SIP (C)",
                min_value=100.0,
                max_value=135.0,
                value=123.0,
                step=0.1,
            )
            _leyenda("Desde 121.1 C el F0 puede alcanzar los 15 min de esterilidad.")
        with ic4:
            n_sip = st.slider(
                "Lecturas SIP (1 min c/u)", min_value=1, max_value=10, value=5,
                help="Cada lectura aporta dt_min = 1 min a la integral de F0.",
            )
            _leyenda("Mas lecturas suman mas F0. Bajo 121.1 C el lote no queda esteril.")

        interlocks = check_safety_interlocks(
            power_density_W_m3=power_density_W_m3,
            sparge_vvm=sparge_vvm,
            batch_active=True,
            cip_valve_requested=cip_valve_requested,
            cip_pipe_velocity_m_s=cip_pipe_velocity_m_s,
            sip_temps_C=[sip_temp_C] * int(n_sip),
            dt_min=1.0,
        )

        k1, k2, k3, k4, k5 = st.columns(5)

        def _flag(col, label, ok_true_is_good, value, yes_word, no_word):
            good = bool(value) if ok_true_is_good else (not bool(value))
            _chip(col, label, good, yes_word if value else no_word, "True" if value else "False")

        _flag(k1, "Alarma de cizalla", False, interlocks["high_shear_alarm"], "Alarma", "Normal")
        _flag(k2, "CIP bloqueado", False, interlocks["cip_interlock_blocked"], "Bloqueado", "Libre")
        _flag(k3, "Velocidad CIP", True, interlocks["cip_velocity_compliant"], "Cumple", "No cumple")
        k4.metric("F0 acumulado (min)", f"{interlocks['f0_minutes']:.2f}")
        _flag(k5, "SIP", True, interlocks["sip_sterile_compliant"], "Esteril", "No esteril")

    with st.expander("Controlador split-range de pH (CO2 vs bomba de base)"):
        current_ph = st.slider(
            "pH medido actual",
            min_value=6.0,
            max_value=8.0,
            value=7.0,
            step=0.01,
        )
        _leyenda("A la derecha, mas basico, abre CO2. A la izquierda, mas acido, prende la base. Dentro de la banda muerta los dos quedan quietos.")
        act = compute_split_range_ph_actuators(
            current_ph, setpoint=7.0, deadband=ph_deadband, kp=150.0
        )
        a1, a2, a3 = st.columns(3)
        a1.metric("Valvula CO2 (%)", f"{act['co2_valve_pct']:.2f}")
        a2.metric("Bomba de base (%)", f"{act['base_pump_pct']:.2f}")
        a3.metric(
            "Setpoint termico (C)",
            f"{get_temperature_setpoint(0.0, shift_day=temp_shift_day):.1f} -> "
            f"{get_temperature_setpoint(temp_shift_day, shift_day=temp_shift_day):.1f}",
            help=f"get_temperature_setpoint antes y desde el dia {temp_shift_day:.1f}.",
        )
        # Carga acida de lactato al final del cultivo, leida de la simulacion en vivo.
        LACTATE_MW_G_MOL = 90.08
        s_lac_final = static_res["lactate_g_L"][-1]
        c_lac_final = closed_res["lactate_g_L"][-1]
        st.caption(
            "Carga acida de lactato final (la base debe neutralizarla): "
            f"receta estatica {s_lac_final:.3f} g/L = "
            f"{s_lac_final / LACTATE_MW_G_MOL * 1000.0:.2f} mmol/L; "
            f"lazo cerrado {c_lac_final:.3f} g/L = "
            f"{c_lac_final / LACTATE_MW_G_MOL * 1000.0:.2f} mmol/L "
            f"(MW lactato {LACTATE_MW_G_MOL} g/mol)."
        )

    st.caption(
        "Fuentes: Quint et al., Ark Biotech & Culture Biosciences 2026 (lazo cerrado); "
        "Kulkarni et al., Culture Biosciences & Bionova Scientific 2026 (base 0.25 L Stratyx, "
        "perfil 36.5 -> 34 C en el dia 7 con NISTCHO, CHO-K1); "
        "ASME BPE-2014 (CIP). Valores calculados en vivo por src/bioreactor_twin.py. "
        "La ganancia de titulo es la que producen las ecuaciones (misma cinetica en ambos "
        "modos). El +43 % de Quint et al. es un dato de literatura, no un resultado de este modelo."
    )


# ---------------------------------------------------------------------------
# TAB 2 - Espacio de Diseno Multivariado ISPE A-Mab y Escalamiento
# ---------------------------------------------------------------------------
# Constantes de referencia de entrada (no son KPI): punto de anclaje A-Mab a
# 15,000 L (Tabla 3.22: Vs 0.015 m/s, P/V 26 W/m3, kLa 20 h^-1). La banda de Vs
# 0.005-0.017 m/s y el rango de escala 500-25,000 L son supuestos de modelado del
# tablero (sin fuente); P/V 19-30 W/m3 viene de Bionova (Ref. 2).
AMAB_REF_VS_M_S = 0.015
AMAB_REF_PV_W_M3 = 26.0
VS_VALID_MIN, VS_VALID_MAX = 0.005, 0.017
SCALE_VALID_MIN_L, SCALE_VALID_MAX_L = 500.0, 25000.0
PV_WINDOW_W_M3 = (19.0, 30.0)
SCALE_PRESETS = {
    "Personalizado": None,
    "0.25 L Stratyx (micro-escala)": 0.25,
    "500 L piloto": 500.0,
    "2,000 L clinico": 2000.0,
    "15,000 L comercial (referencia A-Mab)": 15000.0,
}

st.session_state.setdefault("scale_preset", "15,000 L comercial (referencia A-Mab)")
st.session_state.setdefault("scale_vs", AMAB_REF_VS_M_S)
st.session_state.setdefault("scale_pv", AMAB_REF_PV_W_M3)


def _apply_scale_preset() -> None:
    """Presets: escalamiento a P/V y Vs constantes desde la referencia A-Mab 15,000 L."""
    if SCALE_PRESETS[st.session_state.scale_preset] is not None:
        st.session_state.scale_vs = AMAB_REF_VS_M_S
        st.session_state.scale_pv = AMAB_REF_PV_W_M3


with tab2:
    st.header("Espacio de Diseno Multivariado ISPE A-Mab y Escalamiento (0.25 L a 15,000 L)")
    st.markdown(
        "Evaluador en tiempo real de las 4 inecuaciones de respuesta N-glicano "
        "(z1..z4). El espacio de diseno se sostiene (`design_space_holds`) cuando "
        "los parametros estan en limites **y** z1..z4 >= 4.60."
    )

    with st.container(border=True):
        _band("Fuente del coeficiente de osmolalidad en z1")
        mode_label = st.radio(
            "table_3_8_mode",
            [
                "Tabla Fig. 3.8 (p.92): Osm +1.54, aFuc < 11 %",
                "Texto p.90: Osm +0.51, aFuc < 13 %",
            ],
            horizontal=True,
            key="amab_mode",
            help="evaluate_amab_design_space(table_3_8_mode=True/False). True es el valor validado por defecto.",
        )
        table_3_8_mode = mode_label.startswith("Tabla")
        _leyenda(
            "El caso A-Mab trae dos valores para el efecto principal de Osm en la inecuacion 1: "
            "la tabla de la Fig. 3.8 (p.92, aFuc < 11 %) usa +1.54 y el texto de la p.90 "
            "(aFuc < 13 %) usa +0.51. Solo cambia z1; en el centro (400 mOsm) da lo mismo."
        )

        _band("Factores del espacio de diseno")
        _leyenda("Centro: 17 dias, 100 mmHg, 400 mOsm, pH 6.85 y 35 C. Si una z baja de 4.60, el espacio se cae.")
        s1, s2, s3 = st.columns(3)
        with s1:
            cd_days = st.slider("Duracion de cultivo (d)", 15.0, 19.0, 17.0, 0.1)
            co2_mmHg = st.slider("pCO2 (mmHg)", 40.0, 160.0, 100.0, 1.0)
        with s2:
            osm_mOsm = st.slider("Osmolalidad (mOsm/kg)", 360.0, 440.0, 400.0, 1.0)
            ph_val = st.slider("pH", 6.6, 7.1, 6.85, 0.01)
        with s3:
            temp_C = st.slider("Temperatura (C)", 34.0, 36.0, 35.0, 0.05)
            _leyenda("Mueve osmolalidad lejos de 400 para ver la diferencia entre las dos fuentes de z1.")

    ds = evaluate_amab_design_space(
        cd_days=cd_days, co2_mmHg=co2_mmHg, osm_mOsm=osm_mOsm, ph_val=ph_val,
        temp_C=temp_C, table_3_8_mode=table_3_8_mode,
    )

    _band("Respuestas de N-glicano")
    z1, z2, z3, z4, z5 = st.columns(5)
    LIMIT = 4.60

    def _z(col, label, value):
        with col:
            st.metric(label, f"{value:.2f}", delta=f"{value - LIMIT:+.2f} vs 4.60")
            _chip(col, "limite 4.60", value >= LIMIT, "Cumple" if value >= LIMIT else "No cumple", f"{value:.2f}")

    _z(z1, "z1 afuc max", ds["z1_afuc_max"])
    _z(z2, "z2 afuc min", ds["z2_afuc_min"])
    _z(z3, "z3 gal max", ds["z3_gal_max"])
    _z(z4, "z4 gal min", ds["z4_gal_min"])
    _chip(z5, "in_bounds", ds["in_bounds"], "Dentro" if ds["in_bounds"] else "Fuera", str(ds["in_bounds"]))
    _chip(
        z5,
        "design_space_holds",
        ds["design_space_holds"],
        "Se sostiene" if ds["design_space_holds"] else "No se sostiene",
        str(ds["design_space_holds"]),
    )

    _band("Mapa de cumplimiento")
    _leyenda("El mapa solo mueve temperatura y pH, con la fuente de z1 elegida arriba. Lo demas queda como lo dejaste.")
    n_grid = 25
    temp_axis = np.linspace(34.0, 36.0, n_grid)
    ph_axis = np.linspace(6.6, 7.1, n_grid)
    z_grid = np.zeros((n_grid, n_grid))  # filas = pH, columnas = temp
    for i, ph_i in enumerate(ph_axis):
        for j, t_j in enumerate(temp_axis):
            cell = evaluate_amab_design_space(
                cd_days=cd_days,
                co2_mmHg=co2_mmHg,
                osm_mOsm=osm_mOsm,
                ph_val=float(ph_i),
                temp_C=float(t_j),
                table_3_8_mode=table_3_8_mode,
            )
            z_grid[i, j] = 1.0 if cell["design_space_holds"] else 0.0

    heat = go.Figure(
        data=go.Heatmap(
            z=z_grid,
            x=temp_axis,
            y=ph_axis,
            # design_space_holds is boolean: discrete two-colour scale, no gradient.
            colorscale=[[0.0, "#ef553b"], [0.5, "#ef553b"], [0.5, "#00cc96"], [1.0, "#00cc96"]],
            zmin=0,
            zmax=1,
            hovertemplate="T %{x:.2f} C<br>pH %{y:.3f}<extra></extra>",
            colorbar=dict(
                title="espacio",
                tickvals=[0.25, 0.75],
                ticktext=["No (Fallo CQA)", "Sí (Cumple)"],
                tickfont=dict(color=P["ink"]),
            ),
        )
    )
    heat.add_trace(
        go.Scatter(
            x=[temp_C], y=[ph_val], mode="markers", name="Punto actual",
            marker=dict(symbol="x", size=13, color=P["ink"], line=dict(width=2)),
        )
    )
    heat.update_layout(
        title="Temperatura vs pH: rojo no se sostiene, verde se sostiene",
        xaxis_title="Temperatura (C)",
        yaxis_title="pH",
        height=420,
    )
    st.markdown(
        f'<p class="bp-note"><span class="bp-swatch" style="background:#ef553b"></span>'
        "Rojo: design_space_holds es falso. "
        f'<span class="bp-swatch" style="background:#00cc96"></span>'
        "Verde: es verdadero. La X marca el punto de los sliders.</p>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(_apply_figure(heat), width="stretch")

    with st.container(border=True):
        _band("Transferencia de oxigeno")
        st.subheader("Calculadora de kLa, OTR y OUR (escalamiento)")
        # Same law as src/amab_design_space.compute_kla_h_inv, read from its constants.
        st.latex(
            rf"k_La\,[h^{{-1}}] = {KLA_COEFF:g}\cdot V_s^{{{KLA_EXP_VS:g}}}\cdot (P/V)^{{{KLA_EXP_PV:g}}}"
        )
        st.caption(
            f"kLa = {KLA_COEFF:g} * Vs^{KLA_EXP_VS:g} * (P/V)^{KLA_EXP_PV:g}, con Vs en m/s y P/V en "
            "W/m3 (compute_kla_h_inv en src/amab_design_space.py). Forma de A-Mab Ec. 4 (p.101), "
            "con k, a, b dependientes de la configuracion; anclada en el punto de 15,000 L de "
            "A-Mab (Tabla 3.22, kLa medido 8-20 h^-1). El coeficiente se recalibro en este repo; "
            "en 0.25 L y 2 L la ley es una extrapolacion."
        )
        st.selectbox(
            "Preset de escala",
            list(SCALE_PRESETS.keys()),
            key="scale_preset",
            on_change=_apply_scale_preset,
            help="Los presets fijan Vs = 0.015 m/s y P/V = 26.0 W/m3 (referencia A-Mab 15,000 L) "
                 "bajo un criterio de escalamiento a P/V y Vs constantes.",
        )
        preset_volume_L = SCALE_PRESETS[st.session_state.scale_preset]
        e1, e2, e3, e4 = st.columns(4)
        with e1:
            superficial_gas_vel_m_s = st.slider(
                "Velocidad superficial de gas Vs (m/s)",
                VS_VALID_MIN, VS_VALID_MAX, step=0.0005, format="%.4f", key="scale_vs",
                help="Banda de prueba 0.005-0.017 m/s (supuesto de modelado). A-Mab Tabla 3.22: 0.015 m/s a 15,000 L.",
            )
        with e2:
            power_per_vol_W_m3 = st.slider(
                "Potencia por volumen P/V (W/m3)", 2.0, 100.0, step=0.5, key="scale_pv",
                help="Bionova usa 19 y 30 W/m3 (Ref. 2). A-Mab Tabla 3.22: 26 W/m3 a 15,000 L.",
            )
        with e3:
            vcc = st.slider("VCC (1e6 cel/mL)", 1.0, 60.0, 15.0, 0.5)
        with e4:
            do_slider_pct = st.slider(
                "Setpoint de DO (% saturacion de aire)",
                min_value=10.0,
                max_value=90.0,
                value=float(ProcessDescription().do_setpoint_pct),
                step=1.0,
                key="do_setpoint_pct",
                help="ProcessDescription.do_setpoint_pct; bounds del modelo [10, 100] %.",
            )
            _leyenda(
                "Fuerza impulsora = C* (0.210 mmol/L, supuesto de modelado) x (1 - DO/100); OTR = kLa x fuerza "
                "impulsora. Afecta tanto el margen OTR >= OUR de escalamiento como la cinetica "
                "CHO (hipoxia/efecto Pasteur bajo 20% DO, banda supuesta y no calibrada, y limitacion "
                "de transferencia si OTR < OUR)."
            )
        # El setpoint pasa por el esquema validado (ProcessDescription) antes de usarse.
        do_setpoint_pct = ProcessDescription(do_setpoint_pct=do_slider_pct).do_setpoint_pct

        scale = compute_scale_up_engineering(
            superficial_gas_vel_m_s=superficial_gas_vel_m_s,
            power_per_vol_W_m3=power_per_vol_W_m3,
            vcc_1e6_cells_mL=vcc,
            do_percent=do_setpoint_pct,
        )
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("kLa (1/h)", f"{scale['kla_h_inv']:.2f}")
        sc2.metric(
            "OTR (mmol/L/h)",
            f"{scale['otr_mmol_L_h']:.2f}",
            help=f"OTR = kLa * 0.210 * (1 - DO/100) mmol/L con DO = {do_setpoint_pct:g} % (C* = 0.210 mmol/L, supuesto de modelado).",
        )
        sc3.metric("OUR max (mmol/L/h)", f"{scale['our_max_mmol_L_h']:.2f}")
        _chip(
            sc4,
            "oxygen_sufficient (OTR >= OUR)",
            scale["oxygen_sufficient"],
            "Suficiente" if scale["oxygen_sufficient"] else "Insuficiente",
            str(scale["oxygen_sufficient"]),
        )
        if scale["oxygen_sufficient"]:
            st.success(
                f"URS-06 OK: con DO {do_setpoint_pct:g} %, OTR {scale['otr_mmol_L_h']:.2f} "
                f">= OUR {scale['our_max_mmol_L_h']:.2f} mmol/L/h."
            )
        else:
            st.error(
                f"URS-06 oxigeno insuficiente: con DO {do_setpoint_pct:g} %, OTR "
                f"{scale['otr_mmol_L_h']:.2f} < OUR {scale['our_max_mmol_L_h']:.2f} mmol/L/h. "
                "Baja el setpoint de DO o sube kLa (Vs, P/V)."
            )

        v1, v2, v3 = st.columns(3)
        if preset_volume_L is None:
            _chip(v1, "Escala del preset", True, "Sin escala", "preset personalizado")
        else:
            scale_ok = SCALE_VALID_MIN_L <= preset_volume_L <= SCALE_VALID_MAX_L
            _chip(
                v1, "Escala del preset", scale_ok,
                "Dentro" if scale_ok else "Fuera",
                f"{preset_volume_L:,.2f} L vs 500-25,000 L (supuesto del tablero, sin fuente)",
            )
        vs_ok = VS_VALID_MIN <= superficial_gas_vel_m_s <= VS_VALID_MAX
        _chip(v2, "Vs en banda de prueba", vs_ok, "Dentro" if vs_ok else "Fuera", f"{superficial_gas_vel_m_s:.4f} m/s")
        pv_ok = PV_WINDOW_W_M3[0] <= power_per_vol_W_m3 <= PV_WINDOW_W_M3[1]
        _chip(v3, "P/V 19-30 (Bionova)", pv_ok, "Dentro" if pv_ok else "Fuera", f"{power_per_vol_W_m3:.1f} W/m3")
        if preset_volume_L is not None and preset_volume_L < SCALE_VALID_MIN_L:
            _banner(
                "warn",
                "0.25 L Stratyx: la ley de kLa esta anclada en el punto de 15,000 L de A-Mab "
                "(Tabla 3.22). En 0.25 L el resultado es una extrapolacion; los sliders no se "
                "fuerzan.",
            )

        vs_axis = np.linspace(VS_VALID_MIN, VS_VALID_MAX, 25)
        otr_axis = [
            compute_scale_up_engineering(
                float(v), power_per_vol_W_m3, vcc, do_percent=do_setpoint_pct
            )["otr_mmol_L_h"]
            for v in vs_axis
        ]
        fig_o = go.Figure()
        fig_o.add_trace(
            go.Scatter(x=vs_axis, y=otr_axis, mode="lines", name="OTR a P/V actual",
                       line=dict(color=P["closed"], width=2.6))
        )
        fig_o.add_hline(
            y=scale["our_max_mmol_L_h"], line=dict(color=P["limit"], dash="dash", width=2.6),
            annotation_text=f"OUR max {scale['our_max_mmol_L_h']:.2f}", annotation_position="top left",
        )
        fig_o.add_trace(
            go.Scatter(x=[superficial_gas_vel_m_s], y=[scale["otr_mmol_L_h"]], mode="markers",
                       name="Punto actual", marker=dict(color=P["ink"], size=11, symbol="x"))
        )
        fig_o.update_layout(
            title="OTR vs Vs en la banda de prueba",
            xaxis_title="Velocidad superficial Vs (m/s)",
            yaxis_title="OTR / OUR (mmol/L/h)",
            height=320,
        )
        st.plotly_chart(_apply_figure(fig_o), width="stretch")

    st.caption(
        "Fuente: CMC Biotech Working Group, A-Mab Case Study v2.1, CASSS/ISPE 2009 "
        "(pp. 90-92 y 100-106; Ec. 4 p.101, Fig. 3.11 p.102 y Tabla 3.22). Los presets aplican "
        "P/V y Vs constantes desde el punto de 15,000 L, un supuesto del tablero (A-Mab p.98 "
        "indica que no tienen por que mantenerse constantes al escalar). Valores en vivo de "
        "src/amab_design_space.py."
    )


# ---------------------------------------------------------------------------
# TAB 3 - Cadena de frio: MKT, filtro VTB y FFT/Nyquist (Rusnack 2026)
# ---------------------------------------------------------------------------
BASE_DT_MIN = 5.0  # analyze_fft_nyquist siempre recibe una senal de 5 min

with tab3:
    st.header("Cadena de Frio: MKT, Filtro VTB y FFT/Nyquist (USP <1079.2>)")
    st.markdown(
        "Registro sintetico de aire de un refrigerador farmaceutico 2-8 C a 5 min, con "
        "ciclado de compresor y una excursion. Se compara el **aire crudo** contra viales "
        "filtrados por el buffer termico virtual (VTB) de 1 mL, 20 mL y 300 L (bulk, tau ~35 h) "
        "(Rusnack, Pharm. Eng. 2026)."
    )

    with st.container(border=True):
        _band("Senal base de aire (5 min)")
        e1, e2, e3, e4 = st.columns(4)
        with e1:
            duration_h = st.slider("Duracion del registro (h)", 6, 72, 24, 1)
        with e2:
            excursion_peak_C = st.slider("Pico de excursion (C)", 8.0, 25.0, 15.0, 0.5)
        with e3:
            compressor_cph = st.slider(
                "Ciclado del compresor (cph)", 2.8, 3.0, 2.9, 0.05,
                help="Rusnack (Pharm. Eng. 2026): compresor de ~2.8-3.0 ciclos/hora.",
            )
        with e4:
            compressor_amp_C = st.slider("Amplitud del compresor (C)", 0.2, 2.0, 1.0, 0.1)
        _leyenda(
            "La excursion sube la MKT; el vial de 1 mL la sigue y el bulk de 300 L casi no. "
            "El compresor es la oscilacion rapida que debe resolver el monitor."
        )

    # 0 a duration_h exclusivo (24 h -> N = 288, igual que test_oq_07).
    n_samples = int((duration_h * 60.0) / BASE_DT_MIN)
    t_min = np.arange(n_samples) * BASE_DT_MIN
    t_hours = t_min / 60.0

    rng = np.random.default_rng(42)
    baseline = 5.0 + 0.4 * np.sin(2.0 * np.pi * t_hours / 6.0)
    compressor = compressor_amp_C * np.sin(2.0 * np.pi * compressor_cph * t_hours)
    center = duration_h * 0.45
    width = max(1.0, duration_h * 0.08)
    excursion = (excursion_peak_C - 5.0) * np.exp(-0.5 * ((t_hours - center) / width) ** 2)
    noise = rng.normal(0.0, 0.15, size=n_samples)
    air_steady = baseline + compressor + noise
    air = (air_steady + excursion).tolist()

    volume_keys = ["1 mL", "20 mL (Glycol Ref)", "300 L (Bulk)"]
    vtb_traces = {k: apply_vtb_filter(air, volume_key=k) for k in volume_keys}

    fig_t = go.Figure()
    fig_t.add_trace(
        go.Scatter(x=t_hours, y=air, mode="lines", name="Aire crudo (5 min)",
                   line=dict(color=P["air"], width=1.4))
    )
    colors = {"1 mL": P["v1"], "20 mL (Glycol Ref)": P["v20"], "300 L (Bulk)": P["v300"]}
    for k in volume_keys:
        fig_t.add_trace(
            go.Scatter(x=t_hours, y=vtb_traces[k], mode="lines", name=f"VTB {k}",
                       line=dict(color=colors[k], width=2.6))
        )
    fig_t.add_hrect(y0=2.0, y1=8.0, fillcolor=P["mean"], opacity=0.16, line_width=0,
                    annotation_text="Rango 2-8 C", annotation_position="top left")
    fig_t.update_layout(
        title="Aire crudo vs trazas VTB por volumen",
        xaxis_title="Tiempo (h)",
        yaxis_title="Temperatura (C)",
        height=420,
    )
    st.plotly_chart(_apply_figure(fig_t), width="stretch")

    _band("Temperatura cinetica media (MKT)")
    mk_cols = st.columns(4)
    mk_cols[0].metric("MKT aire crudo (C)", f"{calculate_mkt_celsius(air):.3f}")
    for idx, k in enumerate(volume_keys):
        mk_cols[idx + 1].metric(f"MKT VTB {k} (C)", f"{calculate_mkt_celsius(vtb_traces[k]):.3f}")

    with st.container(border=True):
        _band("Cualificacion del intervalo de muestreo (FFT / Nyquist)")
        q1, q2 = st.columns(2)
        with q1:
            target_dt = st.selectbox(
                "target_sampling_interval_min (min)", [5.0, 15.0, 30.0, 60.0], index=0,
                format_func=lambda v: f"{v:g} min",
                help="Intervalo del monitor candidato que se cualifica contra la senal base de 5 min.",
            )
        with q2:
            fft_source = st.radio(
                "Senal analizada",
                ["Linea base estable (sin excursion)", "Registro completo (con excursion)"],
                horizontal=True,
                help="Una excursion lenta concentra energia cerca de 0 cph y puede tapar el compresor como pico dominante.",
            )
        fft_signal = air_steady.tolist() if fft_source.startswith("Linea") else air
        fft_res = analyze_fft_nyquist(fft_signal, target_sampling_interval_min=target_dt)

    f1, f2, f3, f4 = st.columns(4)
    f1.metric("Frecuencia dominante real (cph)", f"{fft_res['true_dominant_freq_cph']:.2f}")
    f2.metric("Nyquist objetivo (cph)", f"{fft_res['target_nyquist_cph']:.2f}",
              help="target_nyquist_cph = 60 / (2 * dt)")
    f3.metric(
        "Alias plegado (cph)",
        f"{fft_res['folded_alias_freq_cph']:.2f}",
        help="|f_real - fs * round(f_real / fs)| con fs = 60/dt cuando hay aliasing; 0 si no.",
    )
    _chip(
        f4,
        "aliasing_risk",
        not fft_res["aliasing_risk"],
        "Con aliasing" if fft_res["aliasing_risk"] else "Sin aliasing",
        str(fft_res["aliasing_risk"]),
    )
    if fft_res["aliasing_risk"]:
        _banner(
            "bad",
            f"Riesgo de aliasing: un monitor a {target_dt:g} min (Nyquist "
            f"{fft_res['target_nyquist_cph']:.2f} cph) no resuelve la senal de "
            f"{fft_res['true_dominant_freq_cph']:.2f} cph y la veria como "
            f"{fft_res['folded_alias_freq_cph']:.2f} cph.",
        )
    else:
        _banner(
            "ok",
            f"Sin aliasing: a {target_dt:g} min el Nyquist ({fft_res['target_nyquist_cph']:.2f} cph) "
            f"supera la frecuencia dominante ({fft_res['true_dominant_freq_cph']:.2f} cph).",
        )

    # Espectro para visualizar: mismo calculo que analyze_fft_nyquist (rfft de la
    # senal de 5 min sin media). Los KPI de arriba salen de src; esto solo dibuja.
    sig = np.asarray(fft_signal, dtype=float)
    sig = sig - sig.mean()
    spectrum = np.abs(np.fft.rfft(sig))
    freqs_cph = np.fft.rfftfreq(sig.size, d=BASE_DT_MIN) * 60.0
    plot_dom = float(freqs_cph[int(np.argmax(spectrum[1:]) + 1)]) if spectrum.size > 1 else 0.0
    if round(plot_dom, 2) != fft_res["true_dominant_freq_cph"]:
        _banner("warn", "El espectro dibujado no coincide con analyze_fft_nyquist; revisar.")

    sp1, sp2 = st.columns(2)
    with sp1:
        fig_f = go.Figure()
        fig_f.add_trace(go.Scatter(x=freqs_cph, y=spectrum, mode="lines", name="|FFT|",
                                   line=dict(color=P["closed"], width=2.2)))
        fig_f.add_vline(
            x=fft_res["target_nyquist_cph"],
            line=dict(color=P["limit"], dash="dash", width=2.4),
            annotation_text=f"Nyquist {fft_res['target_nyquist_cph']:.2f}",
            annotation_position="top",
        )
        fig_f.add_vline(
            x=fft_res["true_dominant_freq_cph"],
            line=dict(color=P["mean"], width=2.4),
            annotation_text=f"Dominante {fft_res['true_dominant_freq_cph']:.2f}",
            annotation_position="bottom right",
        )
        if fft_res["aliasing_risk"]:
            fig_f.add_vline(
                x=fft_res["folded_alias_freq_cph"],
                line=dict(color=P["v20"], dash="dot", width=2.4),
                annotation_text=f"Alias {fft_res['folded_alias_freq_cph']:.2f}",
                annotation_position="bottom left",
            )
        fig_f.update_layout(
            title="Espectro de amplitud (base 5 min)",
            xaxis_title="Frecuencia (cph)",
            yaxis_title="Amplitud |FFT| (C)",
            height=360,
        )
        st.plotly_chart(_apply_figure(fig_f), width="stretch")
    with sp2:
        step = int(round(target_dt / BASE_DT_MIN))
        win = t_hours <= min(6.0, float(duration_h))
        sig_arr = np.asarray(fft_signal, dtype=float)
        fig_a = go.Figure()
        fig_a.add_trace(go.Scatter(x=t_hours[win], y=sig_arr[win], mode="lines",
                                   name="Senal base 5 min", line=dict(color=P["air"], width=1.4)))
        fig_a.add_trace(go.Scatter(x=t_hours[::step][win[::step]], y=sig_arr[::step][win[::step]],
                                   mode="lines+markers", name=f"Monitor cada {target_dt:g} min",
                                   line=dict(color=P["v20"], width=2.4), marker=dict(size=7)))
        fig_a.update_layout(
            title="Lo que ve el monitor (primeras 6 h)",
            xaxis_title="Tiempo (h)",
            yaxis_title="Temperatura (C)",
            height=360,
        )
        st.plotly_chart(_apply_figure(fig_a), width="stretch")

    st.caption(
        "Fuente: Rusnack, Quantifying the Limitations of Fixed Physical Temperature Buffers, "
        "Pharm. Eng. 46(5), 2026. La FFT corre siempre sobre la senal base de 5 min "
        "(Nyquist base 6.0 cph); la resolucion espectral es 1/duracion. Valores en vivo de "
        "src/thermal_vtb_mkt.py."
    )


# ---------------------------------------------------------------------------
# TAB 4 - SPC Six Sigma
# ---------------------------------------------------------------------------
with tab4:
    st.header("SPC Six Sigma (Gorsky 2020 / ISO 16269 / ASTM E2281)")
    # Limites de especificacion: los valores por defecto de compute_process_capability.
    _cap_params = inspect.signature(compute_process_capability).parameters
    SPC_LSL = float(_cap_params["lsl"].default)
    SPC_USL = float(_cap_params["usl"].default)
    st.markdown(
        "Control estadistico de procesos usando los datasets de torque de Gorsky "
        f"(Tablas 6-1 n={len(GORSKY_TABLE_6_1_TORQUE_N10)} y 6-2 "
        f"n={len(GORSKY_TABLE_6_2_TORQUE_N30)}). Unidades: Tabla 6-1 en kp, Tabla 6-2 en lb/in; "
        f"LSL {SPC_LSL:g} lb/in y USL {SPC_USL:g} lb/in (Tabla 6-2). La unidad lb/in esta "
        "impresa asi en Gorsky, Tabla 6-2; dimensionalmente un torque se expresaria en lbf·in "
        "(observacion del repo, no de la fuente)."
    )

    cap = compute_process_capability(GORSKY_TABLE_6_2_TORQUE_N30, lsl=SPC_LSL, usl=SPC_USL)
    mr = compute_moving_range_summary(GORSKY_TABLE_6_2_TORQUE_N30)
    ti = compute_iso16269_tolerance_interval(GORSKY_TABLE_6_1_TORQUE_N10)

    # Cada bloque ocupa el ancho completo: con 4 tarjetas en media columna el valor
    # (p. ej. "0.61") no cabia y Streamlit lo cortaba a "0. ...", que se leia como cero.
    with st.container(border=True):
        _band("Desempeno global (largo plazo): Pp / Ppk con std global, ddof=1")
        st.caption(
            "Lo que el proceso entrego frente a la especificacion en todo el periodo: "
            "usa la dispersion total de las muestras, incluida la deriva entre ellas."
        )
        p = st.columns(5)
        p[0].metric("Pp", f"{cap['pp']:.2f}", help="Pp = (USL-LSL)/(6*std_global)")
        p[1].metric("Ppk", f"{cap['ppk']:.2f}", help="Ppk = min(Ppu, Ppl)")
        p[2].metric("Ppu", f"{cap['ppu']:.2f}", help="Ppu = (USL-media)/(3*std_global)")
        p[3].metric("Ppl", f"{cap['ppl']:.2f}", help="Ppl = (media-LSL)/(3*std_global)")
        p[4].metric("Std global (lb/in)", f"{cap['std']:.2f}", help="std_overall = std(data, ddof=1)")
    with st.container(border=True):
        _band(f"Capacidad within (corto plazo): std_within = MR-bar / d2, d2 = {mr['d2']:.3f}")
        st.caption(
            "Lo que el proceso puede lograr en el corto plazo: usa solo la variacion "
            "entre muestras consecutivas (rango movil de 2), sin la deriva de largo plazo."
        )
        w = st.columns(6)
        w[0].metric("Cp within", f"{cap['cp_within']:.2f}", help="Cp = (USL-LSL)/(6*std_within)")
        w[1].metric("Cpk within", f"{cap['cpk_within']:.2f}", help="Cpk = min(Cpu, Cpl) within")
        w[2].metric("Cpu within", f"{cap['cpu_within']:.2f}")
        w[3].metric("Cpl within", f"{cap['cpl_within']:.2f}")
        w[4].metric("Std within (lb/in)", f"{cap['std_within']:.2f}", help="std_within = MR-bar / d2")
        w[5].metric("MR-bar (lb/in)", f"{mr['mr_bar']:.2f}", help="mean(|x[i] - x[i-1]|), compute_moving_range_summary")

    n1, n2, n3, n4, n5 = st.columns(5)
    n1.metric("Shapiro-Wilk p-value", f"{cap['normality_p_value']:.4f}")
    _chip(n2, "is_normal (p >= 0.05)", cap["is_normal"],
          "Normal" if cap["is_normal"] else "No normal", str(cap["is_normal"]))
    _chip(n3, "capable_4sigma (Ppk >= 1.33)", cap["capable_4sigma"],
          "Capaz" if cap["capable_4sigma"] else "No capaz", str(cap["capable_4sigma"]))
    n4.metric("Media global (lb/in)", f"{cap['mean']:.2f}")
    n5.metric("N (muestras)", f"{mr['n']}")

    ch1, ch2 = st.columns(2)
    with ch1:
        x_idx = list(range(1, len(GORSKY_TABLE_6_2_TORQUE_N30) + 1))
        fig_sh = go.Figure()
        fig_sh.add_trace(
            go.Scatter(x=x_idx, y=GORSKY_TABLE_6_2_TORQUE_N30, mode="lines+markers",
                       name="Torque (lb/in)", line=dict(color=P["closed"]), marker=dict(color=P["closed"], size=6))
        )
        x_span = [x_idx[0], x_idx[-1]]

        def _limit_trace(y, name, color, dash, width=2.4):
            fig_sh.add_trace(
                go.Scatter(x=x_span, y=[y, y], mode="lines", name=name,
                           line=dict(color=color, dash=dash, width=width))
            )

        # Limites I-MR within (corto plazo): X-bar +/- 3*std_within = X-bar +/- 2.66*MR-bar
        _limit_trace(cap["ucl_within"], f"UCL within I-MR {cap['ucl_within']:.2f}", P["limit"], "dash")
        _limit_trace(cap["lcl_within"], f"LCL within I-MR {cap['lcl_within']:.2f}", P["limit"], "dash")
        # Limites globales (largo plazo): media +/- 3*std global
        _limit_trace(cap["ucl"], f"UCL global {cap['ucl']:.2f}", P["closed"], "dot", 1.8)
        _limit_trace(cap["lcl"], f"LCL global {cap['lcl']:.2f}", P["closed"], "dot", 1.8)
        _limit_trace(cap["mean"], f"Media {cap['mean']:.2f}", P["mean"], "solid")
        fig_sh.update_layout(
            title=f"Carta de Shewhart I-MR, Tabla 6-2 (n={len(GORSKY_TABLE_6_2_TORQUE_N30)})",
            xaxis_title="Muestra (#)", yaxis_title="Torque (lb/in)", height=360,
        )
        # 6 entradas de leyenda -> 3 filas de 2 debajo del grafico, lejos del titulo.
        st.plotly_chart(_apply_figure(fig_sh, legend_rows=3), width="stretch")
    with ch2:
        fig_h = go.Figure()
        fig_h.add_trace(go.Histogram(x=GORSKY_TABLE_6_2_TORQUE_N30, nbinsx=12, name="Torque",
                                     marker_color=P["closed"]))
        fig_h.add_vline(x=SPC_LSL, line=dict(color=P["limit"], dash="dash", width=2.4),
                        annotation_text=f"LSL {SPC_LSL:g}")
        fig_h.add_vline(x=SPC_USL, line=dict(color=P["limit"], dash="dash", width=2.4),
                        annotation_text=f"USL {SPC_USL:g}")
        fig_h.update_layout(
            title=f"Distribucion de torque | Pp {cap['pp']:.2f}, Ppk {cap['ppk']:.2f}",
            xaxis_title="Torque (lb/in)", yaxis_title="Frecuencia (conteo)", height=360,
        )
        # Misma altura total que la carta de Shewhart para alinear las dos columnas.
        st.plotly_chart(_apply_figure(fig_h, legend_rows=3), width="stretch")
    _leyenda(
        "UCL/LCL within I-MR = media +/- 3 std_within = media +/- 2.66 MR-bar (corto plazo, Shewhart). "
        "UCL/LCL global = media +/- 3 std global (largo plazo). Ambos los calcula "
        "compute_process_capability. Los datos de Gorsky son fijos."
    )

    with st.container(border=True):
        _band("Intervalo de tolerancia ISO 16269-6 (n=10, Tabla 6-1)")
        ti_cols = st.columns(5)
        ti_cols[0].metric("Factor k", f"{ti['k_factor']:.3f}", help="k_factor por defecto de compute_iso16269_tolerance_interval.")
        ti_cols[1].metric("Media (kp)", f"{ti['mean']:.2f}")
        ti_cols[2].metric("Desv. std (kp)", f"{ti['std']:.2f}")
        ti_cols[3].metric("Limite inferior (kp)", f"{ti['lower_tolerance']:.2f}")
        ti_cols[4].metric("Limite superior (kp)", f"{ti['upper_tolerance']:.2f}")

    _band("Comparar dos reactores")
    st.subheader("Prueba t de Welch entre dos reactores (datos editables)")
    _leyenda("Si separas los valores de A y de B, el p-valor baja y la prueba marca diferencia.")
    default_a = pd.DataFrame({"Reactor A": [8.1, 7.9, 8.4, 8.0, 8.3, 7.8]})
    default_b = pd.DataFrame({"Reactor B": [8.6, 8.9, 9.1, 8.7, 9.0, 8.8]})
    ca, cb = st.columns(2)
    with ca:
        edited_a = st.data_editor(default_a, num_rows="dynamic", key="reactor_a", width="stretch")
    with cb:
        edited_b = st.data_editor(default_b, num_rows="dynamic", key="reactor_b", width="stretch")

    def _clean(df, col):
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        return series.astype(float).tolist()

    group_a = _clean(edited_a, "Reactor A")
    group_b = _clean(edited_b, "Reactor B")

    if len(group_a) >= 2 and len(group_b) >= 2:
        tt = compare_bioreactor_equivalence_ttest(group_a, group_b, alpha=0.05)
        tc = st.columns(3)
        tc[0].metric("t-stat", f"{tt['t_stat']:.4f}")
        tc[1].metric("p-value", f"{tt['p_value']:.6f}")
        _chip(
            tc[2],
            "Diferencia significativa (alpha 0.05)",
            not tt["statistically_significant_diff"],
            "Hay diferencia" if tt["statistically_significant_diff"] else "Sin diferencia",
            f"p = {tt['p_value']:.4f}",
        )
    else:
        _banner("warn", "Hacen falta al menos dos numeros validos en cada reactor.")

    st.caption(
        "Fuentes: Gorsky, Principles of Parenteral Solution Validation, Elsevier 2020, cap. 6; "
        "ISO 16269-6:2014; ASTM E2281. Valores en vivo de src/spc_six_sigma.py."
    )


# ---------------------------------------------------------------------------
# TAB 5 - Gobernanza GxP (21 CFR Part 11 / Annex 22 / FDA CSA OQ)
# ---------------------------------------------------------------------------
def _load_oq_log(path: str):
    """Lee el log OQ generado por tests/conftest.py. Devuelve None si no existe."""
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return None
    meta, packages, rows = {}, [], []
    for line in text.splitlines():
        s = line.strip()
        m = re.match(r"^- \*\*(.+?):\*\*\s*(.*)$", s)
        if m:
            meta[m.group(1)] = m.group(2)
            continue
        m = re.match(r"^- ([A-Za-z0-9_.\-]+): (.+)$", s)
        if m:
            packages.append({"Paquete": m.group(1), "Version": m.group(2)})
            continue
        if s.startswith("| tests/"):
            cells = [c.strip() for c in s.strip("|").split("|")]
            if len(cells) == 4:
                try:
                    duration = float(cells[3])
                except ValueError:
                    duration = None
                rows.append(
                    {
                        "Prueba": cells[0].split("::")[-1],
                        "Categoria CSA": cells[1],
                        "Resultado": cells[2],
                        "Duracion (s)": duration,
                    }
                )
    verdict = re.search(r"declared \*\*(NOT ACCEPTABLE|ACCEPTABLE)\*\*", text)
    return {
        "text": text,
        "meta": meta,
        "packages": packages,
        "rows": rows,
        "verdict": verdict.group(1) if verdict else None,
    }


def _sha256_file(path: str):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return None


def _oq_requirements(path: str) -> dict:
    """Primera linea del docstring de cada test_* (lo que verifica cada prueba OQ)."""
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (OSError, SyntaxError):
        return {}
    reqs = {}
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
            doc = (ast.get_docstring(node) or "").strip()
            reqs[node.name] = doc.splitlines()[0] if doc else "n/d"
    return reqs


def _verdict_code_path(path: str):
    """Lineas de tests/conftest.py::pytest_sessionfinish que derivan el veredicto."""
    try:
        with open(path, encoding="utf-8") as fh:
            src_text = fh.read()
        tree = ast.parse(src_text)
    except (OSError, SyntaxError):
        return None
    lines = src_text.splitlines()
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "pytest_sessionfinish":
            picked = []
            for lineno in range(node.lineno, node.end_lineno + 1):
                text = lines[lineno - 1]
                if re.match(r"^\s*(def pytest_sessionfinish|total|passed|failed|errored|skipped|overall)\b", text):
                    picked.append(f"{lineno:>4}  {text.strip()}")
            return "\n".join(picked)
    return None


def _oq_short_id(name: str) -> str:
    m = re.match(r"^test_(oq|exploratory)_(\d+[a-z]?)_", name)
    if not m:
        return name
    return f"{'OQ' if m.group(1) == 'oq' else 'EXP'}-{m.group(2)}"


def _oq_table(oq: dict, reqs: dict) -> pd.DataFrame:
    rows = []
    for r in oq["rows"]:
        name = r["Prueba"]
        rows.append(
            {
                "ID": _oq_short_id(name),
                "Prueba": name,
                "Requisito verificado (docstring)": reqs.get(name, "n/d"),
                "Categoria CSA": r["Categoria CSA"],
                "Resultado": r["Resultado"],
                "Duracion (s)": r["Duracion (s)"],
            }
        )
    return pd.DataFrame(rows)


def _oq_summary(oq: dict) -> dict:
    total = len(oq["rows"])
    passed = sum(1 for r in oq["rows"] if r["Resultado"] == "PASSED")
    return {"total": total, "passed": passed, "not_passed": total - passed}


def _run_oq_in_temp() -> dict:
    """Re-ejecuta tests/ en una COPIA temporal del repo.

    tests/conftest.py escribe el log en <raiz>/docs/04_...md relativo a su propia
    ubicacion, asi que al copiar src/, tests/ y pytest.ini a un directorio temporal
    el log nuevo cae en <tmp>/docs/ y el log comprometido del repo no se toca.
    """
    before = _sha256_file(OQ_LOG_PATH)
    tmp = tempfile.mkdtemp(prefix="oq_rerun_")
    result = {"ok": False, "error": None, "returncode": None, "stdout_tail": "",
              "oq": None, "log_text": None, "elapsed_s": None}
    try:
        ignore = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache")
        shutil.copytree(os.path.join(ROOT_DIR, "src"), os.path.join(tmp, "src"), ignore=ignore)
        shutil.copytree(TESTS_DIR, os.path.join(tmp, "tests"), ignore=ignore)
        shutil.copy2(os.path.join(ROOT_DIR, "pytest.ini"), os.path.join(tmp, "pytest.ini"))
        os.makedirs(os.path.join(tmp, "docs"), exist_ok=True)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        t0 = time.perf_counter()
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider"],
            cwd=tmp, capture_output=True, text=True, timeout=180, env=env,
        )
        result["elapsed_s"] = time.perf_counter() - t0
        result["returncode"] = proc.returncode
        result["stdout_tail"] = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-15:])
        tmp_log = os.path.join(tmp, OQ_LOG_REL)
        oq = _load_oq_log(tmp_log)
        if oq is None:
            result["error"] = "pytest corrio pero no genero el log temporal."
        else:
            result["oq"] = oq
            result["log_text"] = oq["text"]
            result["ok"] = True
    except (OSError, subprocess.SubprocessError) as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    result["temp_dir"] = tmp
    result["committed_unchanged"] = before == _sha256_file(OQ_LOG_PATH)
    result["committed_sha256"] = before
    return result


def _first_broken_index(records: list):
    """Primer registro donde verify_chain_integrity() falla, verificando prefijos."""
    for k in range(1, len(records) + 1):
        probe = AuditTrailLogger()
        probe.records = records[:k]
        if not probe.verify_chain_integrity():
            return k - 1
    return None


with tab5:
    st.header("Gobernanza GxP: 21 CFR Part 11, Annex 22 y FDA CSA OQ")
    st.markdown(
        "Evidencia de calificacion operacional automatizada (OQ) y registro de cambios "
        "de parametro con firma electronica y cadena de hashes SHA-256."
    )

    reqs = _oq_requirements(OQ_TEST_FILE)

    # ---------------- Que significa ACCEPTABLE ----------------
    with st.container(border=True):
        _band("Que significa ACCEPTABLE")
        st.markdown(
            "Bajo la guia FDA *Computer Software Assurance* (Feb 2026), el log "
            "OQ es la **evidencia objetiva** de que el software hace lo que debe para su uso "
            "segun riesgo. El veredicto **no es un texto fijo**: lo calcula `tests/conftest.py` "
            "al cerrar cada corrida de pytest con los resultados reales de las pruebas. "
            "Es ACCEPTABLE solo si ninguna prueba fallo ni dio error."
        )
        code_path = _verdict_code_path(CONFTEST_PATH)
        if code_path:
            st.caption("Ruta de codigo que deriva el veredicto (tests/conftest.py, numero de linea a la izquierda):")
            st.code(code_path, language="python")
        else:
            _banner("warn", "No se pudo leer tests/conftest.py para mostrar la ruta del veredicto.")

    # ---------------- Evidencia comprometida ----------------
    _band(f"Evidencia OQ comprometida ({OQ_LOG_REL})")
    oq = _load_oq_log(OQ_LOG_PATH)
    if oq is None:
        _banner("warn", f"No se encontro {OQ_LOG_REL}. Ejecuta python -m pytest -v.")
    else:
        s = _oq_summary(oq)
        o1, o2, o3 = st.columns(3)
        o1.metric("Pruebas aprobadas", f"{s['passed']}/{s['total']}")
        o2.metric("Fallidas o con error", f"{s['not_passed']}")
        verdict = oq["verdict"] or "SIN VEREDICTO"
        _chip(o3, "FDA CSA V.A.6", verdict == "ACCEPTABLE" and s["not_passed"] == 0, verdict,
              f"exit status {oq['meta'].get('Pytest exit status', 'n/d')}")
        st.caption(
            f"Ejecucion (UTC): {oq['meta'].get('Execution timestamp (UTC)', 'n/d')} · "
            f"Python {oq['meta'].get('Python version', 'n/d')} · "
            f"Plataforma: {oq['meta'].get('Platform', 'n/d')}"
        )
        if oq["rows"]:
            st.dataframe(
                _oq_table(oq, reqs),
                width="stretch",
                hide_index=True,
                column_config={"Duracion (s)": st.column_config.NumberColumn(format="%.4f")},
            )
        with st.expander("Entorno calificado y log completo"):
            if oq["packages"]:
                st.dataframe(pd.DataFrame(oq["packages"]), hide_index=True)
            st.markdown(oq["text"])

    # ---------------- Re-ejecucion en vivo ----------------
    with st.container(border=True):
        _band("Re-ejecucion en vivo")
        _leyenda(
            "Corre las pruebas de tests/ ahora mismo, en una copia temporal del repositorio. "
            f"El log nuevo se escribe en un directorio temporal; {OQ_LOG_REL} no se modifica."
        )
        if st.button("Re-ejecutar verificacion OQ ahora"):
            with st.spinner("Ejecutando python -m pytest tests -q en una copia temporal..."):
                st.session_state.oq_rerun = _run_oq_in_temp()
        rerun = st.session_state.get("oq_rerun")
        if rerun:
            if rerun["ok"]:
                r_oq = rerun["oq"]
                rs = _oq_summary(r_oq)
                r_verdict = r_oq["verdict"] or "SIN VEREDICTO"
                r1, r2, r3 = st.columns(3)
                r1.metric("Aprobadas (re-ejecucion)", f"{rs['passed']}/{rs['total']}")
                r2.metric("Fallidas o con error (re-ejecucion)", f"{rs['not_passed']}")
                _chip(r3, "Veredicto derivado", r_verdict == "ACCEPTABLE" and rs["not_passed"] == 0,
                      r_verdict, f"exit status {rerun['returncode']}")
                st.caption(
                    f"Ejecucion (UTC): {r_oq['meta'].get('Execution timestamp (UTC)', 'n/d')} · "
                    f"duracion {rerun['elapsed_s']:.1f} s · log temporal en {rerun['temp_dir']} (eliminado al terminar)"
                )
                st.dataframe(
                    _oq_table(r_oq, reqs),
                    width="stretch",
                    hide_index=True,
                    column_config={"Duracion (s)": st.column_config.NumberColumn(format="%.4f")},
                )
                st.download_button(
                    "Descargar log OQ de esta re-ejecucion (.md)",
                    data=rerun["log_text"],
                    file_name="OQ_Execution_Log_rerun.md",
                    mime="text/markdown",
                )
                with st.expander("Salida de pytest (ultimas lineas)"):
                    st.code(rerun["stdout_tail"] or "(sin salida)", language="text")
            else:
                _banner(
                    "warn",
                    "No se pudo ejecutar pytest en este servidor "
                    f"({rerun['error']}). Respaldo seguro: se mantiene como evidencia el log "
                    f"comprometido de arriba, generado localmente al ejecutar python -m pytest -v y "
                    f"verificado de forma independiente en CI.",
                )
            if rerun["committed_unchanged"]:
                _banner("ok", f"{OQ_LOG_REL} sin cambios: SHA-256 {(rerun['committed_sha256'] or 'n/d')[:16]}...")
            else:
                _banner("bad", f"{OQ_LOG_REL} cambio durante la re-ejecucion. Revisar.")

    # ---------------- Audit trail Part 11 ----------------
    _band("Audit trail 21 CFR Part 11")
    st.caption(
        "Part 11 pide registros electronicos que digan quien, que, cuando y por que. Cada "
        "entrada guarda el SHA-256 de la anterior, asi que cambiar cualquier dato rompe la cadena."
    )
    if "audit_logger" not in st.session_state:
        st.session_state.audit_logger = AuditTrailLogger()
    logger = st.session_state.audit_logger

    with st.form("audit_form", clear_on_submit=False):
        st.subheader("Agregar entrada al audit trail")
        f1, f2 = st.columns(2)
        with f1:
            user_id = st.text_input("Usuario (user_id)", value="atimaran")
            role = st.text_input("Rol", value="Ingeniero de Proceso")
            parameter_name = st.text_input("Accion / parametro", value="temp_shift_day")
        with f2:
            old_value = st.text_input("Valor anterior", value="7.0")
            new_value = st.text_input("Valor nuevo", value="6.0")
        reason_for_change = st.text_area(
            "Razon del cambio (obligatoria)",
            value="Optimizacion de la fase de produccion",
        )
        human_approved = st.checkbox(
            "Firma electronica: aprobacion humana (Annex 22)", value=True
        )
        _leyenda("Sin la casilla, el cambio se rechaza. Con una razon vacia o demasiado corta, tambien.")
        submitted = st.form_submit_button("Registrar cambio")

    if submitted:
        try:
            logger.append_record(
                user_id=user_id,
                role=role,
                parameter_name=parameter_name,
                old_value=old_value,
                new_value=new_value,
                reason_for_change=reason_for_change,
                human_approved=human_approved,
            )
            _banner("ok", "Registro agregado a la cadena de auditoria.")
        except PermissionError as exc:
            _banner("bad", f"PermissionError: {exc}")
        except ValueError as exc:
            _banner("bad", f"ValueError: {exc}")

    st.subheader("Cadena de hashes SHA-256")
    if logger.records:
        chain_rows = []
        for i, rec in enumerate(logger.records):
            expected_prev = logger.records[i - 1]["sha256_hash"] if i else rec["prev_hash"]
            chain_rows.append(
                {
                    "#": i,
                    "timestamp (UTC)": rec["timestamp"],
                    "user_id": rec["user_id"],
                    "accion / parametro": rec["parameter_name"],
                    "cambio": f"{rec['old_value']} -> {rec['new_value']}",
                    "razon": rec["reason_for_change"],
                    "prev_hash": rec["prev_hash"],
                    "sha256_hash": rec["sha256_hash"],
                    "enlace al anterior": rec["prev_hash"] == expected_prev,
                }
            )
        st.dataframe(
            pd.DataFrame(chain_rows),
            width="stretch",
            hide_index=True,
            column_config={
                "prev_hash": st.column_config.TextColumn("prev_hash", width="medium"),
                "sha256_hash": st.column_config.TextColumn("sha256_hash", width="medium"),
                "enlace al anterior": st.column_config.CheckboxColumn("enlace al anterior"),
            },
        )
    else:
        _banner("warn", "Aun no hay registros en la cadena de auditoria.")

    bcol1, bcol2 = st.columns(2)
    with bcol1:
        _leyenda("Recalcula todos los hashes desde el bloque genesis con verify_chain_integrity().")
        if st.button("Verificar integridad"):
            ok = logger.verify_chain_integrity()
            _banner("ok" if ok else "bad", f"verify_chain_integrity() = {ok} ({len(logger.records)} registros)")
    with bcol2:
        _leyenda("Altera un registro en una COPIA de la cadena y muestra donde se rompe. El registro real no se toca.")
        tamper_idx = 0
        if len(logger.records) > 1:
            tamper_idx = st.selectbox(
                "Registro a alterar en la copia", list(range(len(logger.records))), key="tamper_idx"
            )
        if st.button("Demostrar falla de integridad"):
            if logger.records:
                demo = AuditTrailLogger()
                demo.records = copy.deepcopy(logger.records)
                demo.records[tamper_idx]["new_value"] = "TAMPERED"
                broken = _first_broken_index(demo.records)
                _banner(
                    "bad",
                    f"Copia con records[{tamper_idx}]['new_value'] = 'TAMPERED': "
                    f"verify_chain_integrity() = {demo.verify_chain_integrity()}; la cadena se rompe "
                    f"en el registro #{broken}. Cadena real: {logger.verify_chain_integrity()}.",
                )
            else:
                _banner("warn", "No hay registros para alterar. Agrega uno primero.")

    # ---------------- Annex 22 ----------------
    with st.container(border=True):
        _band("EU GMP Annex 22 (borrador): guardrail de IA")
        st.caption(
            "Un modelo de IA o el gemelo digital puede proponer cambios, pero ninguno entra al "
            "registro sin aprobacion humana explicita: append_record lanza PermissionError."
        )
        if st.button("Simular cambio del gemelo digital sin aprobacion humana"):
            sandbox = AuditTrailLogger()
            sandbox.records = copy.deepcopy(logger.records)
            n_before = len(sandbox.records)
            try:
                sandbox.append_record(
                    user_id="digital-twin",
                    role="DigitalTwin",
                    parameter_name="temp_shift_day",
                    old_value=str(temp_shift_day),
                    new_value="propuesta del modelo",
                    reason_for_change="Ajuste autonomo propuesto por el gemelo digital",
                    human_approved=False,
                )
                _banner("bad", "El cambio sin aprobacion humana NO fue bloqueado. Revisar.")
            except PermissionError as exc:
                _banner(
                    "ok",
                    f"Bloqueado. PermissionError: {exc} Registros antes/despues: "
                    f"{n_before}/{len(sandbox.records)}; cadena real intacta ({len(logger.records)} registros).",
                )

    st.caption(
        "Marco: 21 CFR Part 11; EudraLex Vol. 4 Annex 11 y Draft Annex 22; FDA Computer "
        "Software Assurance, Section V.A.6. El log OQ lo genera tests/conftest.py en cada pytest."
    )
