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
# Capa visual. No calcula nada: solo tema, tipografia y estilo de figuras.
# La logica sigue llamando a src/ con los mismos argumentos.
# ---------------------------------------------------------------------------
_INK = "#1A2421"
_PAPER = "#F7F4EE"

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:ital,wght@0,400;0,500;0,600;1,400&family=Newsreader:opsz,wght@6..72,500;6..72,600&display=swap');

    html, body, [class*="css"] {
        font-family: "IBM Plex Sans", "Segoe UI", sans-serif;
    }
    .stApp {
        background:
            linear-gradient(180deg, rgba(20, 92, 86, 0.05), rgba(20, 92, 86, 0) 220px),
            #F3EFE7;
        color: #1A2421;
    }
    header[data-testid="stHeader"] { background: transparent; }
    .block-container {
        padding-top: 1.4rem;
        padding-bottom: 3rem;
        max-width: 1240px;
    }
    .bp-mast {
        border-top: 3px solid #145C56;
        border-bottom: 1px solid #DDD4C6;
        padding: 1.15rem 0 1rem;
        margin: 0 0 1.15rem;
    }
    .bp-kicker {
        margin: 0 0 0.35rem;
        font-size: 0.74rem;
        letter-spacing: 0.14em;
        text-transform: uppercase;
        color: #6A6256;
        font-weight: 500;
    }
    .bp-mast h1 {
        font-family: Newsreader, "Iowan Old Style", Georgia, serif;
        font-weight: 500;
        font-size: 2.35rem;
        line-height: 1.08;
        letter-spacing: -0.02em;
        color: #14211E;
        margin: 0;
    }
    .bp-lead {
        margin: 0.55rem 0 0;
        max-width: 72ch;
        color: #3E4744;
        font-size: 1.02rem;
        line-height: 1.45;
    }
    .bp-lead code {
        font-family: "IBM Plex Mono", ui-monospace, monospace;
        font-size: 0.86em;
        background: #E7E1D6;
        padding: 0.05rem 0.3rem;
    }
    h2, h3 {
        font-family: Newsreader, Georgia, serif;
        letter-spacing: -0.015em;
        color: #14211E;
    }
    div[data-testid="stMetric"] {
        background: #FBF9F4;
        border: 1px solid #E3DACB;
        border-top: 3px solid #145C56;
        padding: 0.72rem 0.9rem 0.55rem;
    }
    div[data-testid="stMetricLabel"] {
        letter-spacing: 0.06em;
        text-transform: uppercase;
        font-size: 0.68rem !important;
        color: #665F54 !important;
    }
    div[data-testid="stMetricValue"] {
        font-family: "IBM Plex Mono", ui-monospace, monospace;
        font-weight: 500;
        color: #14211E;
    }
    div[data-testid="stMetricDelta"] {
        font-family: "IBM Plex Mono", ui-monospace, monospace;
    }
    .stTabs [data-baseweb="tab-list"] {
        gap: 0;
        border-bottom: 1px solid #DDD4C6;
    }
    .stTabs [data-baseweb="tab"] {
        height: 2.7rem;
        padding: 0 1rem;
        background: transparent;
        color: #5C564C;
        font-weight: 500;
        border-radius: 0;
    }
    .stTabs [aria-selected="true"] {
        color: #145C56 !important;
        border-bottom: 2px solid #145C56;
    }
    div[data-testid="stAlert"] {
        border-radius: 0;
        border-width: 1px;
    }
    .stButton > button, .stFormSubmitButton > button {
        border-radius: 0;
        border: 1px solid #145C56;
        background: #145C56;
        color: #F7F4EE;
        font-weight: 500;
    }
    .stButton > button:hover, .stFormSubmitButton > button:hover {
        background: #0E433E;
        border-color: #0E433E;
        color: #F7F4EE;
    }
    div[data-testid="stForm"] {
        border: 1px solid #E3DACB;
        background: #FBF9F4;
        padding: 0.4rem 0.9rem 0.8rem;
    }
    div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
        border: 1px solid #E3DACB;
    }
    hr { border-color: #DDD4C6 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="bp-mast">
      <p class="bp-kicker">Ingenieria Biologica · Universidad Nacional de Colombia</p>
      <h1>Control y validacion de bioprocesos</h1>
      <p class="bp-lead">Alejandro Timaran. Tablero de presentacion sobre las funciones reales de <code>src/</code>: gemelo CHO-K1, espacio de diseno A-Mab, cadena de frio, SPC y audit trail. La interfaz no duplica la logica.</p>
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
        plot_bgcolor="rgba(251,249,244,0.9)",
        font=dict(family="IBM Plex Sans, Segoe UI, sans-serif", color=_INK, size=13),
        title=dict(
            font=dict(family="Newsreader, Georgia, serif", size=18, color=_INK),
            x=0,
            xanchor="left",
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            x=0,
            bgcolor="rgba(0,0,0,0)",
            font=dict(size=12),
        ),
        margin=dict(l=52, r=20, t=72, b=42),
        hoverlabel=dict(
            bgcolor=_INK,
            font=dict(color=_PAPER, family="IBM Plex Sans, sans-serif"),
        ),
    )
    fig.update_xaxes(
        showgrid=True, gridcolor="#E7E0D4", zeroline=False,
        linecolor="#D5CBBA", tickfont=dict(size=11), title_font=dict(size=12),
    )
    fig.update_yaxes(
        showgrid=True, gridcolor="#E7E0D4", zeroline=False,
        linecolor="#D5CBBA", tickfont=dict(size=11), title_font=dict(size=12),
    )
    if height:
        fig.update_layout(height=height)
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

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        vessel_volume_L = st.slider(
            "Volumen del biorreactor (L)",
            min_value=0.25,
            max_value=35000.0,
            value=2.0,
            step=0.25,
            help="Bounds ProcessDescription: (0, 35000] L.",
        )
    with c2:
        power_density_W_m3 = st.slider(
            "Densidad de potencia P/V (W/m3)",
            min_value=2.0,
            max_value=100.0,
            value=30.0,
            step=0.5,
            help="Ventana operativa recomendada 19-30 W/m3. Bounds [2, 100].",
        )
    with c3:
        temp_shift_day = st.slider(
            "Dia del cambio termico",
            min_value=1.0,
            max_value=14.0,
            value=7.0,
            step=0.5,
            help="Bounds temp_shift_day [1, 14] d.",
        )
    with c4:
        ph_deadband = st.slider(
            "Banda muerta de pH",
            min_value=0.01,
            max_value=1.0,
            value=0.20,
            step=0.01,
            help="Bounds ph_deadband (0, 1]. Minimo 0.01 para evitar ValidationError.",
        )

    sparge_vvm = st.slider(
        "Flujo de burbujeo sparge (vvm)",
        min_value=0.0,
        max_value=1.0,
        value=0.10,
        step=0.01,
        help="Bounds sparge_vvm [0, 1].",
    )

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

    st.markdown("**KPIs extensivos acoplados al volumen del vaso (variables extensivas)**")
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
                    line=dict(color="#A33B2B", dash="dash", width=2),
                )
            )
            fig.add_trace(
                go.Scatter(
                    x=t_closed,
                    y=closed_res[key],
                    mode="lines",
                    name="Closed-Loop Digital Twin",
                    line=dict(color="#145C56", width=2.2),
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
                line=dict(color="#A33B2B", dash="dash", width=2),
            )
        )
        fig.add_trace(
            go.Scatter(
                x=t_closed,
                y=closed_res[key],
                mode="lines",
                name="Closed-Loop Digital Twin",
                line=dict(color="#145C56", width=2.4),
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
            line=dict(color="#A33B2B", dash="dash", width=2),
        )
    )
    fig_mass.add_trace(
        go.Scatter(
            x=t_closed,
            y=closed_mass_curve,
            mode="lines",
            name="Closed-Loop Digital Twin",
            line=dict(color="#145C56", width=2.4),
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

    st.divider()
    st.subheader("Panel de estado de interlocks de seguridad")
    ic1, ic2, ic3 = st.columns(3)
    with ic1:
        cip_valve_requested = st.toggle("CIP solicitado (valvula)", value=False)
    with ic2:
        cip_pipe_velocity_m_s = st.slider(
            "Velocidad de tuberia CIP (m/s)",
            min_value=0.5,
            max_value=3.0,
            value=1.52,
            step=0.01,
            help="ASME BPE-2014: cumple si >= 1.52 m/s (5 ft/s).",
        )
    with ic3:
        sip_temp_C = st.slider(
            "Temperatura SIP (C)",
            min_value=100.0,
            max_value=135.0,
            value=123.0,
            step=0.1,
        )
    n_sip = st.slider("Numero de sensores SIP", min_value=1, max_value=10, value=20 // 4)

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

    def _flag(col, label, ok_true_is_good, value):
        with col:
            st.caption(label)
            good = value if ok_true_is_good else (not value)
            if good:
                st.success(str(value))
            else:
                st.error(str(value))

    _flag(k1, "Alarma de cizalla alta", False, interlocks["high_shear_alarm"])
    _flag(k2, "Interlock CIP bloqueado", False, interlocks["cip_interlock_blocked"])
    _flag(k3, "Velocidad CIP conforme (ASME BPE)", True, interlocks["cip_velocity_compliant"])
    with k4:
        st.caption("F0 acumulado (min)")
        st.metric("F0", f"{interlocks['f0_minutes']:.2f}")
    _flag(k5, "SIP esteril conforme (F0>=15)", True, interlocks["sip_sterile_compliant"])

    with st.expander("Controlador split-range de pH (CO2 vs bomba de base)"):
        current_ph = st.slider(
            "pH medido actual",
            min_value=6.0,
            max_value=8.0,
            value=7.0,
            step=0.01,
        )
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

    s1, s2, s3 = st.columns(3)
    with s1:
        cd_days = st.slider("Duracion de cultivo (dias)", 15.0, 19.0, 17.0, 0.1)
        co2_mmHg = st.slider("pCO2 (mmHg)", 40.0, 160.0, 100.0, 1.0)
    with s2:
        osm_mOsm = st.slider("Osmolalidad (mOsm)", 360.0, 440.0, 400.0, 1.0)
        ph_val = st.slider("pH", 6.6, 7.1, 6.85, 0.01)
    with s3:
        temp_C = st.slider("Temperatura (C)", 34.0, 36.0, 35.0, 0.05)

    ds = evaluate_amab_design_space(
        cd_days=cd_days, co2_mmHg=co2_mmHg, osm_mOsm=osm_mOsm, ph_val=ph_val, temp_C=temp_C
    )

    z1, z2, z3, z4 = st.columns(4)
    LIMIT = 4.60

    def _z(col, label, value):
        with col:
            st.metric(label, f"{value:.2f}", delta=f"{value - LIMIT:+.2f} vs 4.60")
            if value >= LIMIT:
                st.success("Cumple (>= 4.60)")
            else:
                st.error("No cumple (< 4.60)")

    _z(z1, "z1 afuc max", ds["z1_afuc_max"])
    _z(z2, "z2 afuc min", ds["z2_afuc_min"])
    _z(z3, "z3 gal max", ds["z3_gal_max"])
    _z(z4, "z4 gal min", ds["z4_gal_min"])

    b1, b2 = st.columns(2)
    with b1:
        if ds["in_bounds"]:
            st.success("in_bounds = True")
        else:
            st.error("in_bounds = False")
    with b2:
        if ds["design_space_holds"]:
            st.success("design_space_holds = True")
        else:
            st.error("design_space_holds = False")

    st.divider()
    st.subheader("Mapa de calor de cumplimiento: Temperatura vs pH")
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
            colorscale=[[0.0, "#A33B2B"], [1.0, "#2F6B4F"]],
            zmin=0.0,
            zmax=1.0,
            colorbar=dict(title="holds", tickvals=[0, 1], ticktext=["No", "Si"]),
        )
    )
    heat.update_layout(
        title="design_space_holds (verde=cumple) sobre barrido Temp x pH",
        xaxis_title="Temperatura (C)",
        yaxis_title="pH",
        height=420,
    )
    st.plotly_chart(_apply_figure(heat), width="stretch")

    st.divider()
    st.subheader("Calculadora de kLa y OUR (escalamiento)")
    e1, e2, e3 = st.columns(3)
    with e1:
        superficial_gas_vel_m_s = st.slider(
            "Velocidad superficial de gas (m/s)", 0.001, 0.05, 0.01, 0.001
        )
    with e2:
        power_per_vol_W_m3 = st.slider(
            "Potencia por volumen (W/m3)", 2.0, 250.0, 50.0, 1.0
        )
    with e3:
        vcc = st.slider("VCC (1e6 cel/mL)", 1.0, 60.0, 15.0, 0.5)

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

    e1, e2, e3 = st.columns(3)
    with e1:
        duration_h = st.slider("Duracion del registro (horas)", 6, 72, 24, 1)
    with e2:
        sampling_interval_min = st.selectbox(
            "Intervalo de muestreo (min)", [1.0, 2.0, 5.0, 10.0, 15.0], index=2
        )
    with e3:
        excursion_peak_C = st.slider("Pico de excursion (C)", 8.0, 25.0, 15.0, 0.5)

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
                   line=dict(color="#6E675C", width=1))
    )
    colors = {"1 mL": "#145C56", "20 mL (Glycol Ref)": "#2F6B4F", "300 mL (Bulk)": "#6B5344"}
    for k in volume_keys:
        fig_t.add_trace(
            go.Scatter(x=t_hours, y=vtb_traces[k], mode="lines", name=f"VTB {k}",
                       line=dict(color=colors[k]))
        )
    fig_t.add_hrect(y0=2.0, y1=8.0, fillcolor="#2F6B4F", opacity=0.08, line_width=0,
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
    fig_f.add_trace(go.Scatter(x=freqs_cph, y=spectrum, mode="lines", name="|FFT|", line=dict(color="#145C56", width=1.6)))
    fig_f.add_vline(
        x=fft_res["nyquist_limit_cph"],
        line=dict(color="#A33B2B", dash="dash"),
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
        if fft_res["aliasing_risk"]:
            st.error("True")
        else:
            st.success("False")


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

    st.subheader("Grafica de control de Shewhart (n=30, Tabla 6-2)")
    x_idx = list(range(1, len(GORSKY_TABLE_6_2_TORQUE_N30) + 1))
    fig_sh = go.Figure()
    fig_sh.add_trace(
        go.Scatter(x=x_idx, y=GORSKY_TABLE_6_2_TORQUE_N30, mode="lines+markers",
                   name="Torque (N)", line=dict(color="#145C56"), marker=dict(color="#145C56", size=6))
    )
    fig_sh.add_hline(y=cap["ucl"], line=dict(color="#A33B2B", dash="dash"),
                     annotation_text=f"UCL {cap['ucl']:.2f}")
    fig_sh.add_hline(y=cap["lcl"], line=dict(color="#A33B2B", dash="dash"),
                     annotation_text=f"LCL {cap['lcl']:.2f}")
    fig_sh.add_hline(y=cap["mean"], line=dict(color="#2F6B4F"),
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
        if cap["capable_4sigma"]:
            st.success("True")
        else:
            st.error("False")

    st.subheader("Histograma de capacidad vs LSL/USL")
    fig_h = go.Figure()
    fig_h.add_trace(go.Histogram(x=GORSKY_TABLE_6_2_TORQUE_N30, nbinsx=12, name="Torque", marker_color="#145C56"))
    fig_h.add_vline(x=5.0, line=dict(color="#A33B2B", dash="dash"), annotation_text="LSL 5.0")
    fig_h.add_vline(x=12.0, line=dict(color="#A33B2B", dash="dash"), annotation_text="USL 12.0")
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
    st.subheader("Prueba t de Welch entre dos reactores (datos editables)")
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
            if tt["statistically_significant_diff"]:
                st.error("True")
            else:
                st.success("False")
    else:
        st.warning("Ingresa al menos 2 valores numericos validos por reactor.")


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
            st.success("Registro agregado a la cadena de auditoria.")
        except PermissionError as exc:
            st.error(f"PermissionError: {exc}")
        except ValueError as exc:
            st.error(f"ValueError: {exc}")

    st.subheader("Audit trail")
    if logger.records:
        st.dataframe(pd.DataFrame(logger.records), width="stretch")
    else:
        st.info("Aun no hay registros en la cadena de auditoria.")

    bcol1, bcol2 = st.columns(2)
    with bcol1:
        if st.button("Verificar cadena SHA-256"):
            ok = logger.verify_chain_integrity()
            if ok:
                st.success(f"Integridad de la cadena: {ok}")
            else:
                st.error(f"Integridad de la cadena: {ok}")
    with bcol2:
        if st.button("Demostrar falla de integridad"):
            if logger.records:
                logger.records[0]["new_value"] = "TAMPERED"
                ok = logger.verify_chain_integrity()
                st.error(
                    f"Se altero records[0]['new_value'] = 'TAMPERED'. "
                    f"verify_chain_integrity() = {ok}"
                )
            else:
                st.warning("No hay registros para alterar. Agrega uno primero.")
