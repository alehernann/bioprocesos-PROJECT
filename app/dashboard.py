"""Tablero Streamlit del portafolio de bioprocesos GxP (FASE 4 de 4).

Dashboard interactivo con 5 pestanas que consume EXCLUSIVAMENTE las funciones
reales de src/. Se lanza con:

    streamlit run app/dashboard.py

Autor del portafolio: Alejandro Timaran, Ingenieria Biologica, UNAL.
"""

import os
import sys

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
    div[data-testid="stMetricValue"] {{
        font-family: "IBM Plex Mono", ui-monospace, monospace;
        color: {c["ink"]};
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


def _apply_figure(fig):
    """Unifica fondo, ejes y tipografia de Plotly sin tocar los datos."""
    height = fig.layout.height
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
            yanchor="bottom",
            y=1.02,
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12, color=P["ink"]),
        ),
        margin=dict(l=52, r=20, t=72, b=42),
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
        fig.update_layout(height=height)
    fig.update_annotations(font_color=P["ink"])
    return fig


tab1, tab2, tab3, tab4, tab5 = st.tabs(
    [
        "1. Gemelo Digital CHO-K1",
        "2. Espacio de Diseno A-Mab y Escalamiento",
        "3. Termico, MKT y Filtro VTB",
        "4. SPC Six Sigma",
        "5. Gobernanza GxP",
    ]
)


# ---------------------------------------------------------------------------
# TAB 1 - Gemelo Digital CHO-K1 Fed-Batch y Lazo Cerrado (Bionova / Ark)
# ---------------------------------------------------------------------------
with tab1:
    st.header("Gemelo Digital CHO-K1 Fed-Batch y Lazo Cerrado (Bionova / Ark)")
    st.markdown(
        "Comparacion en vivo entre la receta **estatica** (Static Recipe) y el "
        "**gemelo digital de lazo cerrado** (Closed-Loop Digital Twin), con la "
        "ganancia de titulo calculada en vivo a partir de `simulate_cho_fed_batch`."
    )

    _band("Parametros del cultivo")
    g1, g2, g3 = st.columns(3)
    with g1:
        power_density_W_m3 = st.slider(
            "Densidad de potencia P/V (W/m3)",
            min_value=2.0,
            max_value=100.0,
            value=30.0,
            step=0.5,
            help="Ventana operativa recomendada 19-30 W/m3. Bounds [2, 100].",
        )
        _leyenda("A la derecha, hasta 30 W/m3, el titulo sube un poco. Si pasas 47.6 y el sparge esta por encima de 0.15, hay cizalla: caen viabilidad y titulo.")
    with g2:
        temp_shift_day = st.slider(
            "Dia del cambio termico",
            min_value=1.0,
            max_value=14.0,
            value=7.0,
            step=0.5,
            help="Bounds temp_shift_day [1, 14] d.",
        )
        _leyenda("A la izquierda el cultivo baja antes a 34 C y crece mas lento. A la derecha sigue mas tiempo a 36.5 C, creciendo mas rapido.")
    with g3:
        sparge_vvm = st.slider(
            "Flujo de burbujeo sparge (vvm)",
            min_value=0.0,
            max_value=1.0,
            value=0.10,
            step=0.01,
            help="Bounds sparge_vvm [0, 1].",
        )
        _leyenda("Hasta 0.15 las curvas no se mueven. Por encima de 0.15, si P/V ya paso 47.6, la cizalla baja viabilidad y titulo.")

    _band("Volumen y controlador de pH")
    g4, g5 = st.columns(2)
    with g4:
        vessel_volume_L = st.slider(
            "Volumen del biorreactor (L)",
            min_value=0.25,
            max_value=35000.0,
            value=2.0,
            step=0.25,
            help="Bounds ProcessDescription: (0, 35000] L.",
        )
        _leyenda("A la derecha hay mas litros: suben la masa de anticuerpo y el feed. Los g/L de las curvas siguen igual.")
    with g5:
        ph_deadband = st.slider(
            "Banda muerta de pH",
            min_value=0.01,
            max_value=1.0,
            value=0.20,
            step=0.01,
            help="Bounds ph_deadband (0, 1]. Minimo 0.01 para evitar ValidationError.",
        )
        _leyenda("A la derecha la banda es mas ancha y el controlador actua mas tarde. A la izquierda actua ante un desvio chico: pH alto abre CO2, pH bajo prende la base.")

    shared = dict(
        vessel_volume_L=vessel_volume_L,
        power_density_W_m3=power_density_W_m3,
        temp_shift_day=temp_shift_day,
        ph_deadband=ph_deadband,
        sparge_vvm=sparge_vvm,
    )
    static_cfg = ProcessDescription(mode="static", **shared)
    closed_cfg = ProcessDescription(mode="closed_loop", **shared)

    static_res = simulate_cho_fed_batch(static_cfg)
    closed_res = simulate_cho_fed_batch(closed_cfg)

    # Ganancia de titulo calculada EN VIVO (nunca un numero fijo).
    static_titer = static_res["final_titer_g_L"]
    closed_titer = closed_res["final_titer_g_L"]
    if static_titer > 0:
        titer_gain_pct = (closed_titer - static_titer) / static_titer * 100.0
    else:
        titer_gain_pct = float("nan")

    _band("Concentraciones al cierre")
    m1, m2, m3 = st.columns(3)
    m1.metric("Titulo final estatico (g/L)", f"{static_titer:.3f}")
    m2.metric(
        "Titulo final lazo cerrado (g/L)",
        f"{closed_titer:.3f}",
        delta=f"{closed_titer - static_titer:+.3f} g/L",
    )
    m3.metric(
        "Ganancia de titulo EN VIVO",
        f"{titer_gain_pct:+.2f} %",
        help="(closed.final_titer - static.final_titer) / static.final_titer * 100",
    )

    v1, v2, v3 = st.columns(3)
    v1.metric("Viabilidad final estatica (%)", f"{static_res['final_viability_pct']:.2f}")
    v2.metric("Viabilidad final lazo cerrado (%)", f"{closed_res['final_viability_pct']:.2f}")
    v3.metric("VCD pico lazo cerrado (1e6 cel/mL)", f"{closed_res['peak_vcd']:.2f}")

    # -----------------------------------------------------------------------
    # KPIs EXTENSIVOS acoplados al volumen del biorreactor (vessel_volume_L).
    # Las concentraciones (g/L) son variables INTENSIVAS: no cambian con el
    # volumen y por eso las curvas de arriba se dejan intactas. La MASA (g o kg)
    # y el VOLUMEN de alimentacion (mL o L) son variables EXTENSIVAS: escalan
    # linealmente con el volumen del vaso, asi que se calculan aqui a partir del
    # slider vessel_volume_L sin tocar nada en src/.
    # -----------------------------------------------------------------------

    def _format_mass(titer_g_L: float, volume_L: float) -> tuple[str, str]:
        """Convierte un titulo (g/L) y un volumen (L) en masa total mostrada.

        total_mass_g = titer_g_L * volume_L. Se expresa en kg (valor/1000) cuando
        el vaso es >= 1000 L (escala industrial), de lo contrario en g.
        """
        total_mass_g = titer_g_L * volume_L
        if volume_L >= 1000.0:
            return f"{total_mass_g / 1000.0:.3f} kg", f"{total_mass_g:,.0f} g"
        return f"{total_mass_g:.2f} g", f"{total_mass_g / 1000.0:.4f} kg"

    static_mass_label, static_mass_alt = _format_mass(
        static_res["final_titer_g_L"], vessel_volume_L
    )
    closed_mass_label, closed_mass_alt = _format_mass(
        closed_res["final_titer_g_L"], vessel_volume_L
    )

    # Volumen de alimentacion acumulado (variable EXTENSIVA) derivado del
    # cronograma de alimentacion deterministico de simulate_cho_fed_batch
    # (dias de feed [2,4,6,8,10,12]) SIN importar ni modificar src/. Se mide el
    # incremento real de glucosa (g/L) en cada cruce de dia de feed directamente
    # sobre la serie glucose_g_L que ya devuelve la simulacion: cada salto
    # positivo entre dos puntos consecutivos es el bolo entregado. Se suma el
    # total de glucosa anadida (g/L acumulados) por modo.
    def _cumulative_feed_glucose_g_L(res: dict) -> float:
        g = res["glucose_g_L"]
        added = 0.0
        for a, b in zip(g[:-1], g[1:]):
            if b > a:  # un salto hacia arriba solo ocurre en un bolo de feed
                added += (b - a)
        return added

    # Suposicion de escalado g/L -> volumen de medio de alimentacion:
    # el medio de feed concentrado se asume a FEED_MEDIA_GLUCOSE_G_PER_L g/L de
    # glucosa. Para entregar X g/L de glucosa a un vaso de vessel_volume_L se
    # requiere un volumen de feed = (X g/L * vessel_volume_L) / FEED_MEDIA_GLUCOSE_G_PER_L
    # (masa de glucosa entregada [g] dividida por la concentracion del medio [g/L]).
    FEED_MEDIA_GLUCOSE_G_PER_L = 500.0  # medio de alimentacion concentrado tipico CHO
    closed_feed_glucose_g_L = _cumulative_feed_glucose_g_L(closed_res)
    closed_feed_volume_L = (
        closed_feed_glucose_g_L * vessel_volume_L
    ) / FEED_MEDIA_GLUCOSE_G_PER_L
    if closed_feed_volume_L < 1.0:
        closed_feed_label = f"{closed_feed_volume_L * 1000.0:.1f} mL"
    else:
        closed_feed_label = f"{closed_feed_volume_L:.3f} L"

    _band("Masa y alimentacion, solo por el volumen")
    e1, e2, e3 = st.columns(3)
    e1.metric(
        "Masa total de mAb estatica",
        static_mass_label,
        help=f"final_titer_g_L * vessel_volume_L = {static_mass_alt}",
    )
    e2.metric(
        "Masa total de mAb lazo cerrado",
        closed_mass_label,
        help=f"final_titer_g_L * vessel_volume_L = {closed_mass_alt}",
    )
    e3.metric(
        "Volumen de feed acumulado (lazo cerrado)",
        closed_feed_label,
        help="Estimado con stock de glucosa a 500 g/L + bolos Cell Boost 7a/7b",
    )

    _band("Trayectorias")
    metrics = [
        ("vcd", "VCD (1e6 cel/mL)"),
        ("viability_pct", "Viabilidad (%)"),
        ("glucose_g_L", "Glucosa (g/L)"),
        ("lactate_g_L", "Lactato (g/L)"),
        ("titer_g_L", "Titulo (g/L)"),
    ]
    t_static = static_res["time_days"]
    t_closed = closed_res["time_days"]

    grid_keys = metrics[:4]
    hero_keys = metrics[4:]
    for row_start in range(0, len(grid_keys), 2):
        left, right = st.columns(2)
        for slot, item in zip((left, right), grid_keys[row_start:row_start + 2]):
            key, label = item
            fig = go.Figure()
            fig.add_trace(
                go.Scatter(
                    x=t_static,
                    y=static_res[key],
                    mode="lines",
                    name="Static Recipe",
                    line=dict(color=P["static"], dash="dash", width=2.6),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=t_closed,
                    y=closed_res[key],
                    mode="lines",
                    name="Closed-Loop Digital Twin",
                    line=dict(color=P["closed"], width=2.6),
                )
            )
            fig.update_layout(
                title=label,
                xaxis_title="Tiempo (dias)",
                yaxis_title=label,
                height=300,
            )
            with slot:
                st.plotly_chart(_apply_figure(fig), width="stretch")

    for key, label in hero_keys:
        fig = go.Figure()
        fig.add_trace(
            go.Scatter(
                x=t_static,
                y=static_res[key],
                mode="lines",
                name="Static Recipe",
                line=dict(color=P["static"], dash="dash", width=2.6),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=t_closed,
                y=closed_res[key],
                mode="lines",
                name="Closed-Loop Digital Twin",
                line=dict(color=P["closed"], width=2.6),
            )
        )
        fig.update_layout(
            title=label,
            xaxis_title="Tiempo (dias)",
            yaxis_title=label,
            height=340,
        )
        st.plotly_chart(_apply_figure(fig), width="stretch")

    # -----------------------------------------------------------------------
    # Grafico SECUNDARIO (variable EXTENSIVA): masa acumulada de mAb en el
    # tiempo = titulo(t) * vessel_volume_L para ambas corridas. El titulo (g/L)
    # es intensivo, pero al multiplicarlo por el volumen del vaso obtenemos la
    # masa total producida (g o kg), que SI escala con vessel_volume_L.
    # -----------------------------------------------------------------------
    mass_in_kg = vessel_volume_L >= 1000.0
    mass_scale = vessel_volume_L / 1000.0 if mass_in_kg else vessel_volume_L
    mass_unit = "kg" if mass_in_kg else "g"
    static_mass_curve = [y * mass_scale for y in static_res["titer_g_L"]]
    closed_mass_curve = [y * mass_scale for y in closed_res["titer_g_L"]]

    fig_mass = go.Figure()
    fig_mass.add_trace(
        go.Scatter(
            x=t_static,
            y=static_mass_curve,
            mode="lines",
            name="Static Recipe",
            line=dict(color=P["static"], dash="dash", width=2.6),
        )
    )
    fig_mass.add_trace(
        go.Scatter(
            x=t_closed,
            y=closed_mass_curve,
            mode="lines",
            name="Closed-Loop Digital Twin",
            line=dict(color=P["closed"], width=2.6),
        )
    )
    fig_mass.update_layout(
        title="Masa Acumulada de mAb (g o kg) vs Tiempo",
        xaxis_title="Tiempo (dias)",
        yaxis_title=f"Masa acumulada de mAb ({mass_unit})",
        height=320,
        margin=dict(l=40, r=20, t=50, b=40),
    )
    st.plotly_chart(_apply_figure(fig_mass), width="stretch")

    _band("Limpieza y esterilizacion")
    st.subheader("Panel de estado de interlocks de seguridad")
    ic1, ic2, ic3 = st.columns(3)
    with ic1:
        cip_valve_requested = st.toggle("CIP solicitado (valvula)", value=False)
        _leyenda("Encendido: la valvula de limpieza queda bloqueada.")
    with ic2:
        cip_pipe_velocity_m_s = st.slider(
            "Velocidad de tuberia CIP (m/s)",
            min_value=0.5,
            max_value=3.0,
            value=1.52,
            step=0.01,
            help="ASME BPE-2014: cumple si >= 1.52 m/s (5 ft/s).",
        )
        _leyenda("A la izquierda de 1.52 m/s la limpieza no cumple. De ahi a la derecha, si.")
    with ic3:
        sip_temp_C = st.slider(
            "Temperatura SIP (C)",
            min_value=100.0,
            max_value=135.0,
            value=123.0,
            step=0.1,
        )
        _leyenda("A la derecha el F0 sube muy rapido. Desde 121.1 C puede alcanzar los 15 min de esterilidad.")
    n_sip = st.slider("Numero de sensores SIP", min_value=1, max_value=10, value=20 // 4)
    _leyenda("A la derecha se suman mas sensores y el F0 crece. Bajo 121.1 C el lote no queda esteril.")

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
    with k4:
        st.caption("F0 acumulado (min)")
        st.metric("F0", f"{interlocks['f0_minutes']:.2f}")
    _flag(k5, "SIP", True, interlocks["sip_sterile_compliant"], "Esteril", "No esteril")

    with st.expander("Controlador split-range de pH (CO2 vs bomba de base)"):
        current_ph = st.slider(
            "pH medido actual",
            min_value=6.0,
            max_value=8.0,
            value=7.0,
            step=0.01,
        )
        _leyenda("A la derecha, mas basico, abre CO2. A la izquierda, mas acido, prende la base. En el medio los dos quedan quietos.")
        act = compute_split_range_ph_actuators(
            current_ph, setpoint=7.0, deadband=ph_deadband, kp=150.0
        )
        a1, a2 = st.columns(2)
        a1.metric("Valvula CO2 (%)", f"{act['co2_valve_pct']:.2f}")
        a2.metric("Bomba de base (%)", f"{act['base_pump_pct']:.2f}")
        st.caption(
            f"Setpoint termico dia {temp_shift_day:.1f}: "
            f"{get_temperature_setpoint(temp_shift_day, shift_day=temp_shift_day):.2f} C "
            "(fase de produccion)."
        )


# ---------------------------------------------------------------------------
# TAB 2 - Espacio de Diseno Multivariado ISPE A-Mab y Escalamiento
# ---------------------------------------------------------------------------
with tab2:
    st.header("Espacio de Diseno Multivariado ISPE A-Mab y Escalamiento (2 L a 15,000 L)")
    st.markdown(
        "Evaluador en tiempo real de las 4 inecuaciones de respuesta N-glicano "
        "(z1..z4). El espacio de diseno se sostiene (`design_space_holds`) cuando "
        "los parametros estan en limites **y** z1..z4 >= 4.60."
    )

    _band("Factores del espacio de diseno")
    _leyenda("Centro: 17 dias, 100 mmHg, 400 mOsm, pH 6.85 y 35 C. Si una z baja de 4.60, el espacio se cae.")
    s1, s2, s3 = st.columns(3)
    with s1:
        cd_days = st.slider("Duracion de cultivo (dias)", 15.0, 19.0, 17.0, 0.1)
        _leyenda("Hacia 17 dias esta el centro. Hacia 15 o hacia 19, alguna z puede bajar de 4.60.")
        co2_mmHg = st.slider("pCO2 (mmHg)", 40.0, 160.0, 100.0, 1.0)
        _leyenda("Hacia 100 mmHg esta el centro. Hacia 40 o hacia 160 cambia la glicosilacion.")
    with s2:
        osm_mOsm = st.slider("Osmolalidad (mOsm)", 360.0, 440.0, 400.0, 1.0)
        _leyenda("Hacia 400 mOsm esta el centro. Si sube o baja, se mueven z1 a z4.")
        ph_val = st.slider("pH", 6.6, 7.1, 6.85, 0.01)
        _leyenda("A la izquierda el cultivo queda mas acido; a la derecha, mas basico. El mapa dice donde las cuatro z siguen arriba de 4.60.")
    with s3:
        temp_C = st.slider("Temperatura (C)", 34.0, 36.0, 35.0, 0.05)
        _leyenda("Hacia 35 C esta el centro. Hacia 34 o 36, con el pH, el mapa pasa a rojo si el espacio se cae.")

    ds = evaluate_amab_design_space(
        cd_days=cd_days, co2_mmHg=co2_mmHg, osm_mOsm=osm_mOsm, ph_val=ph_val, temp_C=temp_C
    )

    _band("Respuestas de N-glicano")
    z1, z2, z3, z4 = st.columns(4)
    LIMIT = 4.60

    def _z(col, label, value):
        with col:
            st.metric(label, f"{value:.2f}", delta=f"{value - LIMIT:+.2f} vs 4.60")
            _chip(col, "limite 4.60", value >= LIMIT, "Cumple" if value >= LIMIT else "No cumple", f"{value:.2f}")

    _z(z1, "z1 afuc max", ds["z1_afuc_max"])
    _z(z2, "z2 afuc min", ds["z2_afuc_min"])
    _z(z3, "z3 gal max", ds["z3_gal_max"])
    _z(z4, "z4 gal min", ds["z4_gal_min"])

    b1, b2 = st.columns(2)
    _chip(b1, "in_bounds", ds["in_bounds"], "Dentro" if ds["in_bounds"] else "Fuera", str(ds["in_bounds"]))
    _chip(
        b2,
        "design_space_holds",
        ds["design_space_holds"],
        "Se sostiene" if ds["design_space_holds"] else "No se sostiene",
        str(ds["design_space_holds"]),
    )

    _band("Mapa de cumplimiento")
    st.subheader("Mapa de calor de cumplimiento: Temperatura vs pH")
    _leyenda("El mapa solo mueve temperatura y pH. Lo demas se queda como lo dejaste arriba.")
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
            )
            z_grid[i, j] = 1.0 if cell["design_space_holds"] else 0.0

    heat = go.Figure(
        data=go.Heatmap(
            z=z_grid,
            x=[f"{t:.2f}" for t in temp_axis],
            y=[f"{p:.3f}" for p in ph_axis],
            colorscale=[[0.0, P["heat_no"]], [1.0, P["heat_yes"]]],
            zmin=0.0,
            zmax=1.0,
            colorbar=dict(
                title="espacio",
                tickvals=[0, 1],
                ticktext=["No", "Si"],
                tickfont=dict(color=P["ink"]),
            ),
        )
    )
    heat.update_layout(
        title="Rojo: no se sostiene. Verde: se sostiene.",
        xaxis_title="Temperatura (C)",
        yaxis_title="pH",
        height=420,
    )
    st.markdown(
        f'<p class="bp-note"><span class="bp-swatch" style="background:{P["heat_no"]}"></span>'
        "Rojo: design_space_holds es falso. "
        f'<span class="bp-swatch" style="background:{P["heat_yes"]}"></span>'
        "Verde: es verdadero. El rojo no pasa a ser el verde en modo noche.</p>",
        unsafe_allow_html=True,
    )
    st.plotly_chart(_apply_figure(heat), width="stretch")

    _band("Transferencia de oxigeno")
    st.subheader("Calculadora de kLa y OUR (escalamiento)")
    e1, e2, e3 = st.columns(3)
    with e1:
        superficial_gas_vel_m_s = st.slider(
            "Velocidad superficial de gas (m/s)", 0.001, 0.05, 0.01, 0.001
        )
        _leyenda("A la derecha entra mas gas y sube el kLa.")
    with e2:
        power_per_vol_W_m3 = st.slider(
            "Potencia por volumen (W/m3)", 2.0, 250.0, 50.0, 1.0
        )
        _leyenda("A la derecha tambien sube el kLa, menos que con el gas.")
    with e3:
        vcc = st.slider("VCC (1e6 cel/mL)", 1.0, 60.0, 15.0, 0.5)
        _leyenda("A la derecha hay mas celulas y el OUR sube. En 15 queda en 1.5 mmol/L/h.")

    scale = compute_scale_up_engineering(
        superficial_gas_vel_m_s=superficial_gas_vel_m_s,
        power_per_vol_W_m3=power_per_vol_W_m3,
        vcc_1e6_cells_mL=vcc,
    )
    sc1, sc2 = st.columns(2)
    sc1.metric("kLa (1/h)", f"{scale['kla_h_inv']:.2f}")
    sc2.metric("OUR max (mmol/L/h)", f"{scale['our_max_mmol_L_h']:.2f}")


# ---------------------------------------------------------------------------
# TAB 3 - Monitoreo Termico, MKT y Filtro VTB (USP <1079.2>)
# ---------------------------------------------------------------------------
with tab3:
    st.header("Monitoreo Termico, MKT y Filtro VTB (USP <1079.2>)")
    st.markdown(
        "Simulador de excursion de un refrigerador farmaceutico 2-8 C, comparando "
        "el **aire crudo** contra viales filtrados por el buffer termico virtual "
        "(VTB) de 1 mL, 20 mL y 300 mL (Rusnack, Pharm. Eng. 2026)."
    )

    _band("Registro termico")
    e1, e2, e3 = st.columns(3)
    with e1:
        duration_h = st.slider("Duracion del registro (horas)", 6, 72, 24, 1)
        _leyenda("A la derecha el registro dura mas y el pico de calor se ensancha.")
    with e2:
        sampling_interval_min = st.selectbox(
            "Intervalo de muestreo (min)", [1.0, 2.0, 5.0, 10.0, 15.0], index=2
        )
        _leyenda("Hacia intervalos mas largos se ve menos detalle y puede aparecer aliasing.")
    with e3:
        excursion_peak_C = st.slider("Pico de excursion (C)", 8.0, 25.0, 15.0, 0.5)
        _leyenda("A la derecha el pico esta mas caliente y la MKT sube. El vial de 1 mL lo sigue; el de 300 mL casi no.")

    n_samples = int((duration_h * 60.0) / sampling_interval_min) + 1
    t_min = np.arange(n_samples) * sampling_interval_min
    t_hours = t_min / 60.0

    rng = np.random.default_rng(42)
    baseline = 5.0 + 0.4 * np.sin(2.0 * np.pi * t_hours / 6.0)
    # Excursion transitoria centrada hacia la mitad del registro.
    center = duration_h * 0.45
    width = max(1.0, duration_h * 0.08)
    excursion = (excursion_peak_C - 5.0) * np.exp(-0.5 * ((t_hours - center) / width) ** 2)
    noise = rng.normal(0.0, 0.15, size=n_samples)
    air = (baseline + excursion + noise).tolist()

    volume_keys = ["1 mL", "20 mL (Glycol Ref)", "300 mL (Bulk)"]
    vtb_traces = {k: apply_vtb_filter(air, volume_key=k) for k in volume_keys}

    fig_t = go.Figure()
    fig_t.add_trace(
        go.Scatter(x=t_hours, y=air, mode="lines", name="Aire crudo",
                   line=dict(color=P["air"], width=2.6))
    )
    colors = {"1 mL": P["v1"], "20 mL (Glycol Ref)": P["v20"], "300 mL (Bulk)": P["v300"]}
    for k in volume_keys:
        fig_t.add_trace(
            go.Scatter(x=t_hours, y=vtb_traces[k], mode="lines", name=f"VTB {k}",
                       line=dict(color=colors[k], width=2.6))
        )
    fig_t.add_hrect(y0=2.0, y1=8.0, fillcolor=P["mean"], opacity=0.16, line_width=0,
                    annotation_text="Rango 2-8 C", annotation_position="top left")
    fig_t.update_layout(
        title="Aire crudo vs trazas VTB por volumen",
        xaxis_title="Tiempo (horas)",
        yaxis_title="Temperatura (C)",
        height=420,
    )
    st.plotly_chart(_apply_figure(fig_t), width="stretch")

    st.subheader("Temperatura Cinetica Media (MKT) por curva")
    mkt_air = calculate_mkt_celsius(air)
    mk_cols = st.columns(4)
    mk_cols[0].metric("MKT aire crudo (C)", f"{mkt_air:.3f}")
    for idx, k in enumerate(volume_keys):
        mk_cols[idx + 1].metric(f"MKT VTB {k} (C)", f"{calculate_mkt_celsius(vtb_traces[k]):.3f}")

    st.divider()
    st.subheader("Espectro FFT y limite de Nyquist")
    fft_res = analyze_fft_nyquist(air, sampling_interval_min=sampling_interval_min)

    signal = np.asarray(air, dtype=float)
    signal = signal - signal.mean()
    spectrum = np.abs(np.fft.rfft(signal))
    freqs_cph = np.fft.rfftfreq(signal.size, d=sampling_interval_min) * 60.0

    fig_f = go.Figure()
    fig_f.add_trace(go.Scatter(x=freqs_cph, y=spectrum, mode="lines", name="|FFT|", line=dict(color=P["closed"], width=2.6)))
    fig_f.add_vline(
        x=fft_res["nyquist_limit_cph"],
        line=dict(color=P["limit"], dash="dash", width=2.6),
        annotation_text=f"Nyquist {fft_res['nyquist_limit_cph']:.2f} cph",
        annotation_position="top",
    )
    fig_f.update_layout(
        title="Espectro de amplitud (cycles per hour) con limite de Nyquist",
        xaxis_title="Frecuencia (cph)",
        yaxis_title="Amplitud",
        height=360,
    )
    st.plotly_chart(_apply_figure(fig_f), width="stretch")

    f1, f2, f3 = st.columns(3)
    f1.metric("Limite de Nyquist (cph)", f"{fft_res['nyquist_limit_cph']:.2f}")
    f2.metric("Frecuencia dominante (cph)", f"{fft_res['dominant_freq_cph']:.2f}")
    with f3:
        st.caption("Riesgo de aliasing")
        _chip(
            f3,
            "Aliasing",
            not fft_res["aliasing_risk"],
            "Con aliasing" if fft_res["aliasing_risk"] else "Sin aliasing",
            str(fft_res["aliasing_risk"]),
        )


# ---------------------------------------------------------------------------
# TAB 4 - SPC Six Sigma
# ---------------------------------------------------------------------------
with tab4:
    st.header("SPC Six Sigma (Gorsky 2020 / ISO 16269 / ASTM E2281)")
    st.markdown(
        "Control estadistico de procesos usando los datasets de torque de Gorsky "
        "(Tablas 6-1 n=10 y 6-2 n=30)."
    )

    cap = compute_process_capability(GORSKY_TABLE_6_2_TORQUE_N30, lsl=5.0, usl=12.0)

    _band("Carta fija de Gorsky")
    st.subheader("Grafica de control de Shewhart (n=30, Tabla 6-2)")
    _leyenda("Esta carta esta fija. Los numeros de abajo no la mueven.")
    x_idx = list(range(1, len(GORSKY_TABLE_6_2_TORQUE_N30) + 1))
    fig_sh = go.Figure()
    fig_sh.add_trace(
        go.Scatter(x=x_idx, y=GORSKY_TABLE_6_2_TORQUE_N30, mode="lines+markers",
                   name="Torque (N)", line=dict(color=P["closed"]), marker=dict(color=P["closed"], size=6))
    )
    fig_sh.add_hline(y=cap["ucl"], line=dict(color=P["limit"], dash="dash", width=2.6),
                     annotation_text=f"UCL {cap['ucl']:.2f}")
    fig_sh.add_hline(y=cap["lcl"], line=dict(color=P["limit"], dash="dash", width=2.6),
                     annotation_text=f"LCL {cap['lcl']:.2f}")
    fig_sh.add_hline(y=cap["mean"], line=dict(color=P["mean"], width=2.6),
                     annotation_text=f"Media {cap['mean']:.2f}")
    fig_sh.update_layout(
        title="Carta de control: puntos con UCL/LCL (+/- 3 sigma)",
        xaxis_title="Muestra", yaxis_title="Torque (N)", height=380
    )
    st.plotly_chart(_apply_figure(fig_sh), width="stretch")

    sc = st.columns(5)
    sc[0].metric("Media", f"{cap['mean']:.2f}")
    sc[1].metric("Desv. std", f"{cap['std']:.2f}")
    sc[2].metric("Cp", f"{cap['cp']:.2f}")
    sc[3].metric("Cpk", f"{cap['cpk']:.2f}")
    with sc[4]:
        st.caption("Capaz 4 sigma (Cpk>=1.33)")
        _chip(
            sc[4],
            "Cpk >= 1.33",
            cap["capable_4sigma"],
            "Capaz" if cap["capable_4sigma"] else "No capaz",
            str(cap["capable_4sigma"]),
        )

    st.subheader("Histograma de capacidad vs LSL/USL")
    fig_h = go.Figure()
    fig_h.add_trace(go.Histogram(x=GORSKY_TABLE_6_2_TORQUE_N30, nbinsx=12, name="Torque", marker_color=P["closed"]))
    fig_h.add_vline(x=5.0, line=dict(color=P["limit"], dash="dash", width=2.6), annotation_text="LSL 5.0")
    fig_h.add_vline(x=12.0, line=dict(color=P["limit"], dash="dash", width=2.6), annotation_text="USL 12.0")
    fig_h.update_layout(
        title=f"Distribucion de torque | Cp={cap['cp']:.2f}, Cpk={cap['cpk']:.2f}",
        xaxis_title="Torque (N)", yaxis_title="Frecuencia", height=360
    )
    st.plotly_chart(_apply_figure(fig_h), width="stretch")

    st.divider()
    st.subheader("Intervalo de tolerancia ISO 16269-6 (n=10, Tabla 6-1)")
    ti = compute_iso16269_tolerance_interval(GORSKY_TABLE_6_1_TORQUE_N10, k_factor=3.394)
    ti_cols = st.columns(5)
    ti_cols[0].metric("Media", f"{ti['mean']:.2f}")
    ti_cols[1].metric("Desv. std", f"{ti['std']:.2f}")
    ti_cols[2].metric("Factor k", f"{ti['k_factor']:.2f}")
    ti_cols[3].metric("Limite inferior", f"{ti['lower_tolerance']:.2f}")
    ti_cols[4].metric("Limite superior", f"{ti['upper_tolerance']:.2f}")

    st.divider()
    _band("Comparar dos reactores")
    st.subheader("Prueba t de Welch entre dos reactores (datos editables)")
    _leyenda("Si separas los valores de A y de B, el p-valor baja y la prueba marca diferencia.")
    default_a = pd.DataFrame({"Reactor A": [8.1, 7.9, 8.4, 8.0, 8.3, 7.8]})
    default_b = pd.DataFrame({"Reactor B": [8.6, 8.9, 9.1, 8.7, 9.0, 8.8]})
    ca, cb = st.columns(2)
    with ca:
        edited_a = st.data_editor(default_a, num_rows="dynamic", key="reactor_a")
    with cb:
        edited_b = st.data_editor(default_b, num_rows="dynamic", key="reactor_b")

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
        with tc[2]:
            st.caption("Diferencia significativa (alpha=0.05)")
            _chip(
                tc[2],
                "p < 0.05",
                not tt["statistically_significant_diff"],
                "Hay diferencia" if tt["statistically_significant_diff"] else "Sin diferencia",
                f"{tt['p_value']:.4f}",
            )
    else:
        _banner("warn", "Hacen falta al menos dos numeros validos en cada reactor.")


# ---------------------------------------------------------------------------
# TAB 5 - Gobernanza GxP (21 CFR Part 11 / Annex 22)
# ---------------------------------------------------------------------------
with tab5:
    st.header("Gobernanza GxP: Audit Trail 21 CFR Part 11 / Annex 22")
    st.markdown(
        "Registro de cambios de parametro con firma electronica (aprobacion humana) "
        "y cadena de hashes SHA-256 a prueba de manipulacion."
    )

    if "audit_logger" not in st.session_state:
        st.session_state.audit_logger = AuditTrailLogger()
    logger = st.session_state.audit_logger

    with st.form("audit_form", clear_on_submit=False):
        st.subheader("Formulario de cambio de parametro")
        f1, f2 = st.columns(2)
        with f1:
            user_id = st.text_input("Usuario (user_id)", value="atimaran")
            role = st.text_input("Rol", value="Ingeniero de Proceso")
            parameter_name = st.text_input("Parametro", value="temp_shift_day")
        with f2:
            old_value = st.text_input("Valor anterior", value="7.0")
            new_value = st.text_input("Valor nuevo", value="6.0")
        reason_for_change = st.text_area(
            "Razon del cambio (>= 5 caracteres)",
            value="Optimizacion de la fase de produccion",
        )
        human_approved = st.checkbox(
            "Firma electronica: aprobacion humana (Annex 22)", value=True
        )
        _leyenda("Sin la casilla, el cambio se rechaza. Con una razon de menos de 5 letras, tambien.")
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

    st.subheader("Audit trail")
    if logger.records:
        st.dataframe(pd.DataFrame(logger.records), width="stretch")
    else:
        _banner("warn", "Aun no hay registros en la cadena de auditoria.")

    bcol1, bcol2 = st.columns(2)
    with bcol1:
        _leyenda("Recorre los hashes. Si un dato fue cambiado, la cadena sale rota.")
        if st.button("Verificar cadena SHA-256"):
            ok = logger.verify_chain_integrity()
            _banner("ok" if ok else "bad", f"Integridad de la cadena: {ok}")
    with bcol2:
        _leyenda("Altera el primer registro para que la cadena deje de cerrar.")
        if st.button("Demostrar falla de integridad"):
            if logger.records:
                logger.records[0]["new_value"] = "TAMPERED"
                ok = logger.verify_chain_integrity()
                _banner(
                    "bad",
                    f"Se altero records[0]['new_value'] = 'TAMPERED'. verify_chain_integrity() = {ok}",
                )
            else:
                _banner("warn", "No hay registros para alterar. Agrega uno primero.")
