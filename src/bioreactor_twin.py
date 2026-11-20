"""CHO-K1 fed-batch mechanistic digital twin plus control and safety logic.

This module provides:

1. A split-range pH controller (CO2 valve vs. base pump) around a deadband.
2. A biphasic temperature-shift setpoint schedule.
3. GxP safety interlocks: hydrodynamic-shear alarm (47.6 W/m3 = maximum local P/V
   demonstrated acceptable at 2 L, A-Mab Table 3.22, used as a conservative
   criterion, not a damage threshold; 0.15 vvm is a modeling assumption), CIP/SIP
   compliance indicators and sterilization F0 integration. The functions return
   indicators and, when given an audit logger, record trips; they do not abort or
   release anything. The 1.52 m/s
   (5 ft/s) CIP pipe velocity criterion follows ASME BPE-2014.
4. A mechanistic fed-batch simulation of CHO-K1 culture (v1.4.0): six biological
   states (viable cells Xv, dead cells Xd, glucose G, lactate L, ammonium NH3,
   titer P) plus the liquid volume V, integrated piecewise with
   ``scipy.integrate.solve_ivp`` (RK45, rtol 1e-6, atol 1e-9, automatic Radau
   fallback) between the discrete events (feed boluses and temperature shift).
   Ten kinetic parameters are calibrated against the Bionova Stratyx NISTCHO
   30 W/m3 run (``src/model_validation.py``) and fixed here as documented
   constants. The closed-loop adaptive feed follows the Ark Biotech & Culture
   Biosciences technical bulletin (Quint et al., 2026), which reports a +43 %
   titer gain (literature value); this model is not calibrated to that value.

References
----------
- CMC Biotech Working Group, *A-Mab: A Case Study in Bioprocess Development*, v2.1, CASSS/ISPE, Oct. 2009.
- R. Kulkarni et al., "STRATYX Delivers Superior Viable Cell Density ...", Culture Biosciences & Bionova Scientific Whitepaper, 2026.
- Y. Quint et al., "Real-Time Closed-Loop Optimization Delivers 43% Titer Improvement...", Ark Biotech & Culture Biosciences Technical Bulletin, 2026.
- ASME BPE-2014, *Bioprocessing Equipment: An International Standard*.
"""

from dataclasses import dataclass, fields

import numpy as np
from scipy.integrate import solve_ivp

from src.amab_design_space import (
    C_STAR_O2_MMOL_L,
    Q_O2_MMOL_CELL_H,
    Y_O2_AIR,
    measured_kla_for_volume,
)
from src.models import ProcessDescription


def compute_split_range_ph_actuators(
    current_ph: float,
    setpoint: float = 7.00,
    deadband: float = 0.20,
    kp: float = 150.0,
) -> dict:
    """Split-range pH control: CO2 valve above the band, base pump below it.

    When the measured pH exceeds ``setpoint + deadband`` the CO2 (acidifying) valve
    opens proportionally; when it falls below ``setpoint - deadband`` the base pump
    engages proportionally; inside the deadband both actuators rest at 0.0. Outputs
    are proportional (gain ``kp``) and saturated at 100%.

    This controller is independent of the kinetic model: ``simulate_cho_fed_batch``
    does not read ``ProcessDescription.ph_setpoint`` or ``ph_deadband``.
    """
    if current_ph > setpoint + deadband:
        co2_valve_pct = min(100, kp * (current_ph - (setpoint + deadband)))
        base_pump_pct = 0.0
    elif current_ph < setpoint - deadband:
        base_pump_pct = min(100, kp * ((setpoint - deadband) - current_ph))
        co2_valve_pct = 0.0
    else:
        co2_valve_pct = 0.0
        base_pump_pct = 0.0

    return {
        "co2_valve_pct": round(co2_valve_pct, 2),
        "base_pump_pct": round(base_pump_pct, 2),
    }


def get_temperature_setpoint(
    day: float,
    temp_initial_C: float = 36.5,
    temp_shift_C: float = 34.0,
    shift_day: float = 7.0,
) -> float:
    """Biphasic temperature-shift schedule (step change, no ramp).

    Returns the initial (growth-phase) temperature before ``shift_day`` and the
    shifted (production-phase) temperature on or after it. The 36.5 -> 34.0 C
    profile on day 7 follows Bionova (Ref. 2, NISTCHO, CHO-K1). The 36.5 C phase is
    outside the A-Mab Design Space (34-36 C, Table 3.14) but inside the A-Mab DoE
    range (34-37 C, Table 3.10); the Design Space is evaluated in the production
    phase.
    """
    return temp_initial_C if day < shift_day else temp_shift_C


def check_safety_interlocks(
    power_density_W_m3: float,
    sparge_vvm: float,
    batch_active: bool,
    cip_valve_requested: bool,
    cip_pipe_velocity_m_s: float,
    sip_temps_C: list[float],
    dt_min: float = 1.0,
    audit_logger=None,
    current_volume_L: float | None = None,
    vessel_volume_L: float | None = None,
) -> dict:
    """Evaluate the GxP safety interlocks for the bioreactor skid.

    When ``audit_logger`` (an ``AuditTrailLogger``) is given, every interlock trip
    is appended to the audit trail: high-shear alarm, CIP blocked during an active
    batch, CIP velocity below 1.52 m/s, and SIP not sterile. Logging does not change
    the returned flags.

    Returns six boolean/float flags:

    - ``high_shear_alarm``: hydrodynamic-shear alarm (P/V > 47.6 W/m^3 OR
      sparge > 0.15 vvm). 47.6 W/m3 is the maximum local P/V demonstrated
      acceptable at 2 L (A-Mab Table 3.22), applied at every scale as a
      conservative criterion, not a damage threshold (cell damage occurs at P/V
      orders of magnitude higher, A-Mab p.100 / Ma 2002). 0.15 vvm is a modeling
      assumption with no literature source. Either source of
      shear (impeller or bubble/sparge) trips the alarm on its own (v1.3.0).
    - ``cip_interlock_blocked``: CIP valve requested while a batch is active.
    - ``cip_velocity_compliant``: CIP pipe velocity >= 1.52 m/s (ASME BPE-2014, 5 ft/s).
    - ``f0_minutes``: accumulated sterilization lethality F0 at 121.1 C reference.
      121.1 C = 250 F, the conventional F0 reference temperature with z = 10 C;
      the pharmaceutical source is not in the project bibliography.
    - ``sip_sterile_compliant``: F0 >= 15 min and all SIP temperatures >= 121.1 C.
    - ``overfill_alarm``: liquid volume > vessel volume; False unless both optional
      ``current_volume_L`` and ``vessel_volume_L`` are supplied.
    """
    high_shear_alarm = bool((power_density_W_m3 > 47.6) or (sparge_vvm > 0.15))
    cip_interlock_blocked = bool(batch_active and cip_valve_requested)
    cip_velocity_compliant = bool(cip_pipe_velocity_m_s >= 1.52)
    f0_minutes = sum(
        (10.0 ** ((T - 121.1) / 10.0)) * dt_min for T in sip_temps_C if T >= 100.0
    )
    sip_sterile_compliant = bool(
        f0_minutes >= 15.0 and min(sip_temps_C, default=0.0) >= 121.1
    )
    # Overfill alarm: only evaluated when both volumes are supplied (optional).
    overfill_alarm = bool(
        current_volume_L is not None
        and vessel_volume_L is not None
        and current_volume_L > vessel_volume_L
    )

    if audit_logger is not None:
        if high_shear_alarm:
            _audit_event(
                audit_logger,
                "interlock.high_shear_alarm", "False", "True",
                f"URS-09 interlock trip (P/V > 47.6 W/m3 OR sparge > 0.15 vvm): "
                f"P/V {power_density_W_m3} W/m3, sparge {sparge_vvm} vvm",
            )
        if cip_interlock_blocked:
            _audit_event(
                audit_logger,
                "interlock.cip_interlock_blocked", "False", "True",
                "CIP interlock trip: CIP valve requested while a batch is active",
            )
        if not cip_velocity_compliant:
            _audit_event(
                audit_logger,
                "interlock.cip_velocity_compliant", "True", "False",
                f"URS-11 interlock trip: CIP velocity {cip_pipe_velocity_m_s} m/s "
                f"< 1.52 m/s (ASME BPE-2014)",
            )
        if overfill_alarm:
            _audit_event(
                audit_logger,
                "interlock.overfill_alarm", "False", "True",
                f"Overfill interlock trip: liquid volume {current_volume_L} L > "
                f"vessel volume {vessel_volume_L} L",
            )
        if not sip_sterile_compliant:
            _audit_event(
                audit_logger,
                "interlock.sip_sterile_compliant", "True", "False",
                f"URS-12 interlock trip: F0 {f0_minutes:.2f} min / min SIP T "
                f"{min(sip_temps_C, default=0.0)} C below 15 min at 121.1 C",
            )

    return {
        "high_shear_alarm": high_shear_alarm,
        "cip_interlock_blocked": cip_interlock_blocked,
        "cip_velocity_compliant": cip_velocity_compliant,
        "f0_minutes": f0_minutes,
        "sip_sterile_compliant": sip_sterile_compliant,
        "overfill_alarm": overfill_alarm,
    }


# Default initial working volume as a fraction of vessel_volume_L (30 % headroom for
# the feed train). Same value as ProcessDescription.initial_fill_fraction's default;
# the dashboard passes it explicitly. The twin reads config.initial_fill_fraction.
INITIAL_FILL_FRACTION = 0.70

# Identity used for events the system records automatically. These events execute
# the pre-approved control strategy (URS-02 schedule, URS-07 feed rule, URS-09..12
# indicators); human_approved=True records that pre-approval, which the
# AuditTrailLogger Annex 22 guardrail requires for every record.
AUDIT_SYSTEM_USER = "system:bioreactor_twin"
AUDIT_SYSTEM_ROLE = "AutomatedControl"


# ---------------------------------------------------------------------------
# Dissolved oxygen (v1.4.0): real liquid-phase DO from a quasi-steady O2 balance.
# ---------------------------------------------------------------------------
# The biological response depends ONLY on the real liquid DO (DO_real), never on the
# set-point or on controller saturation. Monod in DO_real normalised at 15 % so the
# factor is exactly 1.0 for DO_real >= 15 % and C0-continuous below it. The 15 % /
# 10 % onsets and K_DO_PCT are modeling assumptions (NOT CALIBRATED; Bionova and A-Mab
# ran at 30 % or more, so no hypoxia data exist in the project bibliography).
K_DO_PCT = 1.5               # % air saturation, Monod half-saturation for O2
DO_HYPOXIA_NORM_PCT = 15.0   # % DO_real at which do_hypoxia_factor reaches 1.0
DO_DEATH_ONSET_PCT = 10.0    # % DO_real below which hypoxic death starts


def do_hypoxia_factor(do_real_pct: float) -> float:
    """C0-continuous hypoxia factor on growth, productivity and lactate uptake.

    f_do = min(1, [DO/(DO + K_DO_PCT)] / [15/(15 + K_DO_PCT)]) with DO = DO_real (%
    air saturation). It is exactly 1.0 for DO_real >= 15 % and falls continuously
    to 0 as DO_real -> 0 (f_do(10) = 0.957, f_do(5) = 0.846, f_do(1) = 0.440).
    """
    if do_real_pct >= DO_HYPOXIA_NORM_PCT:
        return 1.0
    do = max(0.0, float(do_real_pct))
    return (do / (do + K_DO_PCT)) / (
        DO_HYPOXIA_NORM_PCT / (DO_HYPOXIA_NORM_PCT + K_DO_PCT)
    )


def compute_dissolved_oxygen_state(
    xv_1e6_cells_mL,
    do_setpoint_pct: float,
    kla_h_inv: float,
    o2_enrichment_enabled: bool = True,
    max_o2_mole_fraction: float = 1.0,
    qo2_mmol_cell_h: float = Q_O2_MMOL_CELL_H,
) -> dict:
    """Quasi-steady liquid O2 balance under a DO controller with O2 enrichment.

    O2 transfer (time constant 1/kLa ~ 6 min) is fast against the cell kinetics
    (days), so the liquid concentration is algebraic in Xv:

        OUR          = Xv * 1e9 * qO2                           [mmol/(L*h)]
        y_O2,max     = max_o2_mole_fraction if enrichment else 0.2095
        C*_max       = C*_air * y_O2,max / 0.2095               (Henry's law)
        C_sp         = C*_air * DO_sp / 100
        C_L,actual   = min(C_sp, max(0, C*_max - OUR / kLa))
        DO_real      = 100 * C_L,actual / C*_air                [% air saturation]
        required y_O2 = 0.2095 * (C_sp + OUR / kLa) / C*_air

    The controller holds DO_sp while the blender can raise y_O2; when even y_O2,max
    is not enough it saturates (``do_controller_saturated``) and DO_real falls
    below the set-point. Saturation alone is not hypoxia: the biological factors
    use DO_real only (``do_hypoxia_factor``; Pasteur deficit below 15 %, death
    deficit below 10 %). ``oxygen_supply_ratio`` = min(1, kLa*(C*_max - C_sp)/OUR)
    is the fraction of the demand that can be met while holding the set-point.

    Accepts a scalar or an array of Xv; returns floats or arrays accordingly.
    """
    xv = np.maximum(np.asarray(xv_1e6_cells_mL, dtype=float), 0.0)
    y_max = float(max_o2_mole_fraction) if o2_enrichment_enabled else Y_O2_AIR
    c_star_max = C_STAR_O2_MMOL_L * y_max / Y_O2_AIR
    c_sp = C_STAR_O2_MMOL_L * float(do_setpoint_pct) / 100.0
    our = xv * 1.0e9 * qo2_mmol_cell_h
    o2_gradient = our / float(kla_h_inv)
    c_l = np.minimum(c_sp, np.maximum(0.0, c_star_max - o2_gradient))
    do_real = 100.0 * c_l / C_STAR_O2_MMOL_L
    saturated = c_l < c_sp - 1e-9
    required_y = Y_O2_AIR * (c_sp + o2_gradient) / C_STAR_O2_MMOL_L
    capacity = float(kla_h_inv) * max(0.0, c_star_max - c_sp)
    with np.errstate(divide="ignore", invalid="ignore"):
        ratio = np.where(our > 0.0, np.minimum(1.0, capacity / np.where(our > 0.0, our, 1.0)), 1.0)
    f_do = np.where(
        do_real >= DO_HYPOXIA_NORM_PCT,
        1.0,
        (do_real / (do_real + K_DO_PCT))
        / (DO_HYPOXIA_NORM_PCT / (DO_HYPOXIA_NORM_PCT + K_DO_PCT)),
    )
    pasteur = np.maximum(0.0, (DO_HYPOXIA_NORM_PCT - do_real) / DO_HYPOXIA_NORM_PCT)
    death = np.maximum(0.0, (DO_DEATH_ONSET_PCT - do_real) / DO_DEATH_ONSET_PCT)
    out = {
        "our_mmol_L_h": our,
        "y_o2_max": y_max,
        "c_star_max_mmol_L": c_star_max,
        "c_setpoint_mmol_L": c_sp,
        "c_l_actual_mmol_L": c_l,
        "do_real_pct": do_real,
        "do_controller_saturated": saturated,
        "required_y_o2": required_y,
        "oxygen_supply_ratio": ratio,
        "f_do": f_do,
        "pasteur_deficit": pasteur,
        "hypoxic_death_deficit": death,
    }
    if np.ndim(xv_1e6_cells_mL) == 0:
        out = {
            k: (bool(v) if k == "do_controller_saturated" else float(v))
            for k, v in out.items()
        }
    return out


# ---------------------------------------------------------------------------
# Hydrodynamic stress inside the ODEs (v1.4.0, decoupled from the URS-09 alarm).
# ---------------------------------------------------------------------------
# check_safety_interlocks keeps the conservative alarm (P/V > 47.6 W/m3 OR sparge >
# 0.15 vvm). The kinetic penalty is a separate, physically scaled term:
# - Sparge (bubble rupture at the gas-liquid interface, Ark DT#1): onset 0.15 vvm
#   (modeling assumption), sigma_sparge = max(0, (sparge - 0.15)/0.15).
# - Impeller: A-Mab runs healthy cultures at up to 60 W/m3 local P/V (Table 3.22,
#   per the v1.4.0 review) and mechanical damage needs P/V orders of magnitude
#   above 47.6 W/m3 (A-Mab p.100 / Ma 2002). The onset is set one order of
#   magnitude above the alarm, 476 W/m3, still below that damage range. It lies
#   outside the schema domain (P/V <= 100 W/m3), so inside the qualified domain
#   P/V has NO kinetic effect.
SPARGE_STRESS_ONSET_VVM = 0.15
IMPELLER_DAMAGE_ONSET_W_M3 = 476.0


def compute_hydrodynamic_stress(power_density_W_m3: float, sparge_vvm: float) -> dict:
    """Continuous shear intensity used by the kinetics (0.0 inside normal operation).

    sigma_imp = max(0, (P/V - 476)/476), sigma_sparge = max(0, (sparge - 0.15)/0.15)
    and sigma_total = sigma_imp + sigma_sparge + sigma_imp * sigma_sparge. kd gains
    kd_shear * sigma_total and qp is divided by (1 + alpha_shear_qp * sigma_total).
    """
    sigma_imp = max(0.0, (float(power_density_W_m3) - IMPELLER_DAMAGE_ONSET_W_M3) / IMPELLER_DAMAGE_ONSET_W_M3)
    sigma_sparge = max(0.0, (float(sparge_vvm) - SPARGE_STRESS_ONSET_VVM) / SPARGE_STRESS_ONSET_VVM)
    return {
        "sigma_impeller": sigma_imp,
        "sigma_sparge": sigma_sparge,
        "sigma_total": sigma_imp + sigma_sparge + sigma_imp * sigma_sparge,
    }


# ---------------------------------------------------------------------------
# Kinetic parameters (one law for every feeding mode).
# ---------------------------------------------------------------------------
# Units: Xv, Xd in 1e6 cells/mL (= 1e9 cells/L); specific rates per 1e9 cells, so
# q [g/(1e9 cell*d)] * Xv [1e9 cell/L] = g/(L*d) with no extra factor.
#
# CALIBRATED (10 free parameters, scipy.optimize.least_squares "trf" against the
# Bionova Stratyx 30 W/m3 daily pre-feed data; src/model_validation.py,
# run_parameter_calibration). Values are the optimiser output; the bounds and
# AT_BOUND flags are in PARAMETER_BOUNDS and docs/03.
MU_MAX_36_5_PER_D = 0.832867   # 1/d, bounds [0.65, 0.95]
MU_MAX_34_0_PER_D = 0.322098   # 1/d, bounds [0.10, 0.35]
K_I_L = 5.01088                # g/L lactate inhibition on growth, bounds [5, 15] (near lower bound)
G_BOOST_CONC = 76.4406         # g/L glucose in the Cell Boost 7a/7b feed, bounds [55, 85]
X_MAX_1E6_ML = 42.6493         # 1e6 cells/mL logistic carrying capacity
Q_LAC_MAX = 0.285600           # g/(1e9 cell*d) maximum lactate uptake
Q_NH3 = 0.0582430              # mmol/(1e9 cell*d) ammonium production
KD_NH3 = 0.0177939             # 1/d per mM of NH3 above NH3_DEATH_ONSET_MM
QP_36_5 = 0.0150130            # g/(1e9 cell*d) specific productivity at 36.5 C
QP_34_0 = 0.00888312           # g/(1e9 cell*d) specific productivity at 34.0 C
# WHY qp(36.5 C) > qp(34.0 C) (empirical, v1.4.0 audit). Bionova Fig. 4 shows production
# slowing late in the run: titer gained per IVCD is 0.0118 (days 0-8), 0.0108 (8-10),
# 0.0084 (10-12) and 0.0028 g/(1e9 cell*d) (12-14) (digitized, no dilution correction).
# In NISTCHO the 34 C phase moderated growth and NH3 and sustained viability; it did
# not raise the instantaneous qp. With one run and one shift day, the temperature
# anchors are the only term that can absorb that late slowdown, so the temperature
# effect on qp is confounded with culture age and unmodeled nutrient depletion. A
# shift-day sweep is therefore an extrapolation: with these anchors a later shift
# always gives more titer, which no Bionova run has tested.

# FIXED MODELING ASSUMPTIONS (NOT CALIBRATED). Either not identifiable from the
# Bionova data (normoxic, glucose > 1 g/L, no shear or sparge excursions) or fixed
# at round values in the CHO-typical range to keep the calibration at 10 free
# parameters; see docs/03 (identifiability) for the data each one would need.
K_S_G = 0.5                  # g/L glucose half-saturation (growth and maintenance)
K_I_NH3 = 20.0               # mM ammonium inhibition constant on growth
NH3_DEATH_ONSET_MM = 5.0     # mM, lower end of the ~5-8 mM physiological window
Y_X_G = 3.0                  # (1e6 cells/mL) per (g/L) glucose = 3.0e9 cells/g
M_G = 0.05                   # g/(1e9 cell*d) maintenance glucose uptake
Y_L_G = 0.80                 # g lactate / g growth-associated glucose (stoich. max 1.0)
K_L = 0.30                   # g/L half-saturation of lactate uptake
KD_BASAL = 0.03              # 1/d basal death rate
K_LYSIS = 1.0                # 1/d first-order lysis of dead cells
KD_STARVE = 0.5              # 1/d extra death at full glucose exhaustion
K_STARVE_G_L = 0.1           # g/L, Hill (n = 2) onset of starvation death
KD_HYPOXIA = 0.1             # 1/d extra death at DO_real = 0
PASTEUR_FRACTION = 0.8       # max fraction of maintenance glucose fermented at DO_real = 0
KD_SHEAR = 0.03              # 1/d extra death per unit of sigma_total
ALPHA_SHEAR_QP = 1.0         # qp / (1 + ALPHA_SHEAR_QP * sigma_total)

T_ANCHORS_C = (34.0, 36.5)   # mu_max(T) and qp(T) are linear between the anchors


@dataclass(frozen=True)
class CHOKineticParameters:
    """Complete parameter set of the v1.4.0 CHO kinetic law (immutable).

    The defaults are the module constants above. ``src/model_validation.py``
    builds modified copies (``dataclasses.replace``) during calibration; the
    dashboard always uses ``CALIBRATED_KINETICS``.
    """

    mu_max_36_5: float = MU_MAX_36_5_PER_D
    mu_max_34_0: float = MU_MAX_34_0_PER_D
    k_i_lactate: float = K_I_L
    g_boost_conc: float = G_BOOST_CONC
    x_max: float = X_MAX_1E6_ML
    q_lac_max: float = Q_LAC_MAX
    q_nh3: float = Q_NH3
    kd_nh3: float = KD_NH3
    qp_36_5: float = QP_36_5
    qp_34_0: float = QP_34_0
    k_s_glucose: float = K_S_G
    k_i_nh3: float = K_I_NH3
    nh3_death_onset: float = NH3_DEATH_ONSET_MM
    y_x_glucose: float = Y_X_G
    m_glucose: float = M_G
    y_lac_glucose: float = Y_L_G
    k_lac_uptake: float = K_L
    kd_basal: float = KD_BASAL
    k_lysis: float = K_LYSIS
    kd_starvation: float = KD_STARVE
    k_starvation: float = K_STARVE_G_L
    kd_hypoxia: float = KD_HYPOXIA
    pasteur_fraction: float = PASTEUR_FRACTION
    kd_shear: float = KD_SHEAR
    alpha_shear_qp: float = ALPHA_SHEAR_QP

    def as_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self)}


CALIBRATED_KINETICS = CHOKineticParameters()

# Free parameters of run_parameter_calibration and their bounds. The first four
# bounds are the literature bounds of the v1.4.0 specification; the others are
# physical sign/magnitude limits.
CALIBRATED_PARAMETER_NAMES = (
    "mu_max_36_5", "mu_max_34_0", "k_i_lactate", "g_boost_conc", "x_max",
    "q_lac_max", "q_nh3", "kd_nh3", "qp_36_5", "qp_34_0",
)
PARAMETER_BOUNDS = {
    "mu_max_36_5": (0.65, 0.95),
    "mu_max_34_0": (0.10, 0.35),
    "k_i_lactate": (5.0, 15.0),
    "g_boost_conc": (55.0, 85.0),
    "x_max": (20.0, 60.0),
    "q_lac_max": (0.0, 1.0),
    "q_nh3": (0.0, 0.3),
    "kd_nh3": (0.0, 0.2),
    "qp_36_5": (0.0, 0.05),
    "qp_34_0": (0.0, 0.05),
    # Extended screening and the K_I,L -> m_G swap experiment only (fixed in the
    # shipped calibration). m_G bounds: CHO physiological range (v1.4.0 audit).
    "y_x_glucose": (0.5, 6.0),
    "m_glucose": (0.03, 0.25),
    "y_lac_glucose": (0.0, 1.0),
    "kd_basal": (0.0, 0.1),
    "k_lysis": (0.0, 3.0),
    "k_i_nh3": (2.0, 60.0),
}

# ---------------------------------------------------------------------------
# Fed-batch protocol constants (Bionova, Ref. 2, pp. 3-4; Ark, Ref. 3).
# ---------------------------------------------------------------------------
FEED_DAYS = (2.0, 4.0, 6.0, 8.0, 10.0, 12.0)
BOOST_FRACTION_OF_V0 = 0.042 + 0.0042     # 4.2 % Cell Boost 7a + 0.42 % 7b of V0
ARK_ADAPTIVE_FACTORS = {8.0: 1.80, 10.0: 1.82}  # closed_loop only ("up to 82%")
C_STOCK_GLUCOSE_G_L = 500.0               # concentrated glucose stock for top-ups
# Initial state: Xv0 = 0.7e6 cells/mL (Bionova inoculum), viability 99.0 %
# (Xd0 = 0.007), G0 = 6.0 g/L, L0 = 0.10 g/L, NH3_0 = 0.5 mM, P0 = 0.
INITIAL_STATE = (0.7, 0.007, 6.0, 0.10, 0.5, 0.0)
STATE_NAMES = ("Xv", "Xd", "G", "L", "NH3", "Titer")

GRID_DT_DAYS = 0.1                 # reporting grid of the time series
SOLVER_RTOL = 1e-6
SOLVER_ATOL = 1e-9
MAX_RHS_EVALS_PER_SEGMENT = 6000   # RK45 budget before switching to Radau
_EPS = 1e-9


class _SolverBudgetExceeded(RuntimeError):
    """RK45 used more RHS evaluations than MAX_RHS_EVALS_PER_SEGMENT (stiffness)."""


def _audit_event(audit_logger, parameter_name, old_value, new_value, reason) -> None:
    """Append one automatic system event to ``audit_logger`` (read-only on state)."""
    audit_logger.append_record(
        user_id=AUDIT_SYSTEM_USER,
        role=AUDIT_SYSTEM_ROLE,
        parameter_name=parameter_name,
        old_value=str(old_value),
        new_value=str(new_value),
        reason_for_change=reason,
        human_approved=True,
    )


def _interp_temperature(temp_C: float, at_34: float, at_36_5: float) -> float:
    """Linear in T between the 34.0 and 36.5 C anchors, clamped (no extrapolation)."""
    return float(np.interp(temp_C, T_ANCHORS_C, (at_34, at_36_5)))


def _build_rhs(kp: CHOKineticParameters, temp_C: float, do_setpoint_pct: float,
               kla_h_inv: float, y_o2_max: float, sigma_shear: float):
    """Right-hand side of the 6-state ODE at constant temperature (one segment).

    Every state is read through max(0, .) (soft positivity for trial RK stages) and
    every consumption rate carries a Monod factor, so it vanishes as C -> 0+.
    """
    mu_max = _interp_temperature(temp_C, kp.mu_max_34_0, kp.mu_max_36_5)
    qp = _interp_temperature(temp_C, kp.qp_34_0, kp.qp_36_5)
    mu_ref = kp.mu_max_36_5
    inv_mu_ref = 1.0 / mu_ref if mu_ref > 0.0 else 0.0
    k_s = kp.k_s_glucose
    k_il = kp.k_i_lactate
    k_in = kp.k_i_nh3
    inv_xmax = 1.0 / kp.x_max
    n_crit = kp.nh3_death_onset
    kd0 = kp.kd_basal + kp.kd_shear * sigma_shear
    kd_st = kp.kd_starvation
    k_st2 = kp.k_starvation * kp.k_starvation
    kd_n = kp.kd_nh3
    kd_hyp = kp.kd_hypoxia
    k_lys = kp.k_lysis
    inv_yxg = 1.0 / kp.y_x_glucose
    m_g = kp.m_glucose
    y_lg = kp.y_lac_glucose
    pasteur = kp.pasteur_fraction
    q_lmax = kp.q_lac_max
    k_l = kp.k_lac_uptake
    q_n = kp.q_nh3
    qp_eff = qp / (1.0 + kp.alpha_shear_qp * sigma_shear)
    # Oxygen balance constants (see compute_dissolved_oxygen_state).
    c_max = C_STAR_O2_MMOL_L * y_o2_max / Y_O2_AIR
    c_sp = C_STAR_O2_MMOL_L * do_setpoint_pct / 100.0
    o2_per_xv = 1.0e9 * Q_O2_MMOL_CELL_H / kla_h_inv   # mmol/L per (1e6 cells/mL)
    do_per_c = 100.0 / C_STAR_O2_MMOL_L
    inv_norm = (DO_HYPOXIA_NORM_PCT + K_DO_PCT) / DO_HYPOXIA_NORM_PCT

    def rhs(t, y):
        xv = y[0] if y[0] > 0.0 else 0.0
        xd = y[1] if y[1] > 0.0 else 0.0
        g = y[2] if y[2] > 0.0 else 0.0
        lac = y[3] if y[3] > 0.0 else 0.0
        nh3 = y[4] if y[4] > 0.0 else 0.0
        c_l = c_max - xv * o2_per_xv
        if c_l > c_sp:
            c_l = c_sp
        elif c_l < 0.0:
            c_l = 0.0
        do_real = c_l * do_per_c
        if do_real >= DO_HYPOXIA_NORM_PCT:
            f_do = 1.0
            h_pasteur = 0.0
            h_death = 0.0
        else:
            f_do = do_real / (do_real + K_DO_PCT) * inv_norm
            h_pasteur = (DO_HYPOXIA_NORM_PCT - do_real) / DO_HYPOXIA_NORM_PCT
            h_death = (DO_DEATH_ONSET_PCT - do_real) / DO_DEATH_ONSET_PCT if do_real < DO_DEATH_ONSET_PCT else 0.0
        f_g = g / (k_s + g)
        logistic = 1.0 - xv * inv_xmax
        if logistic < 0.0:
            logistic = 0.0
        mu = mu_max * f_g * (k_il / (k_il + lac)) * (k_in / (k_in + nh3)) * logistic * f_do
        nh3_excess = nh3 - n_crit
        if nh3_excess < 0.0:
            nh3_excess = 0.0
        kd = kd0 + kd_st * k_st2 / (k_st2 + g * g) + kd_n * nh3_excess + kd_hyp * h_death
        growth_glc = mu * inv_yxg
        maint_glc = m_g * f_g
        phi = mu * inv_mu_ref
        if phi > 1.0:
            phi = 1.0
        q_lac_prod = y_lg * growth_glc + pasteur * h_pasteur * maint_glc
        q_lac_cons = q_lmax * (1.0 - phi) * (lac / (k_l + lac)) * f_do
        return [
            (mu - kd) * xv,
            kd * xv - k_lys * xd,
            -(growth_glc + maint_glc) * xv,
            (q_lac_prod - q_lac_cons) * xv,
            q_n * xv,
            qp_eff * f_do * xv,
        ]

    return rhs


def _euler_segment(rhs, t_a, t_b, y0, t_out, dt):
    """Explicit Euler with positivity clipping (the v1.3.2 integrator, verification only)."""
    y = np.array(y0, dtype=float)
    t = t_a
    out = []
    for tk in t_out:
        while t < tk - 1e-12:
            h = min(dt, tk - t)
            y = np.maximum(0.0, y + h * np.asarray(rhs(t, y), dtype=float))
            t += h
        t = tk
        out.append(y.copy())
    return np.array(out).T


def _integrate_segment(rhs, t_a, t_b, y0, t_out, method, rtol, atol, euler_dt):
    """Integrate one event-free segment; RK45 falls back to Radau on failure/stiffness."""
    if method == "Euler":
        return _euler_segment(rhs, t_a, t_b, y0, t_out, euler_dt), {
            "method": "Euler", "nfev": 0, "fallback": False, "reason": ""}
    calls = [0]

    def counted(t, y):
        calls[0] += 1
        if calls[0] > MAX_RHS_EVALS_PER_SEGMENT:
            raise _SolverBudgetExceeded
        return rhs(t, y)

    reason = ""
    try:
        sol = solve_ivp(counted, (t_a, t_b), y0, method=method, rtol=rtol, atol=atol, t_eval=t_out)
        if sol.success:
            return sol.y, {"method": method, "nfev": int(sol.nfev), "fallback": False, "reason": ""}
        reason = str(sol.message)
    except _SolverBudgetExceeded:
        reason = f"more than {MAX_RHS_EVALS_PER_SEGMENT} RHS evaluations (stiff)"
    if method == "Radau":
        raise RuntimeError(f"Radau failed on [{t_a}, {t_b}] d: {reason}")
    sol = solve_ivp(rhs, (t_a, t_b), y0, method="Radau", rtol=rtol, atol=atol, t_eval=t_out)
    if not sol.success:
        raise RuntimeError(f"RK45 and Radau failed on [{t_a}, {t_b}] d: {sol.message}")
    return sol.y, {"method": "Radau", "nfev": int(sol.nfev), "fallback": True, "reason": reason}


def _state_dict(state, volume_L: float) -> dict:
    xv, xd, g, lac, nh3, titer = (float(v) for v in state)
    total = xv + xd
    return {
        "Xv": xv, "Xd": xd, "G": g, "L": lac, "NH3": nh3, "Titer": titer, "V": float(volume_L),
        "viability_pct": 100.0 * xv / total if total > 0.0 else 0.0,
    }


def simulate_cho_fed_batch(
    config: ProcessDescription,
    audit_logger=None,
    *,
    kinetics: CHOKineticParameters | None = None,
    method: str = "RK45",
    rtol: float = SOLVER_RTOL,
    atol: float = SOLVER_ATOL,
    euler_dt: float = GRID_DT_DAYS,
) -> dict:
    """Simulate a CHO-K1 fed-batch culture (v1.4.0 six-state mechanistic model).

    When ``audit_logger`` (an ``AuditTrailLogger``) is given, the run appends the
    automatic temperature set-point shift (URS-02) and every glucose top-up with
    V_gluc > 0 (URS-07) to the audit trail. Logging only reads the state; the
    returned results are identical with and without a logger.

    STATES: Xv, Xd (1e6 cells/mL), G (g/L), L (g/L), NH3 (mmol/L), P = titer (g/L)
    and the liquid volume V (L), which only changes at feed events.

    ONE KINETIC LAW for every mode. ``config.mode`` is read only in the feed-dosing
    block; it never enters mu, kd, qp, q_G, q_L or q_NH3. T is the set-point
    schedule (36.5 -> 34.0 C at temp_shift_day); mu_max(T) and qp(T) are linear
    between the 34.0 and 36.5 C anchors and clamped.

        mu    = mu_max(T) * G/(K_S_G+G) * K_I_L/(K_I_L+L) * K_I_NH3/(K_I_NH3+NH3)
                * max(0, 1 - Xv/X_MAX) * f_do(DO_real)
        kd    = KD_BASAL + KD_STARVE * K_st^2/(K_st^2+G^2) + KD_NH3 * max(0, NH3-NH3_crit)
                + KD_HYPOXIA * max(0, (10 - DO_real)/10) + KD_SHEAR * sigma_total
        dXv/dt = (mu - kd) * Xv
        dXd/dt = kd * Xv - K_LYSIS * Xd
        q_G    = mu/Y_X_G + M_G * G/(K_S_G+G);                   dG/dt = -q_G * Xv
        q_Lp   = Y_L_G * mu/Y_X_G + PASTEUR * h_P(DO_real) * M_G * G/(K_S_G+G)
        q_Lc   = Q_LAC_MAX * (1 - mu/mu_max(36.5)) * L/(K_L+L) * f_do(DO_real)
        dL/dt  = (q_Lp - q_Lc) * Xv
        dNH3/dt = Q_NH3 * Xv
        dP/dt  = qp(T) * f_do(DO_real) / (1 + ALPHA_SHEAR_QP * sigma_total) * Xv

    Lactate switch: production follows the growth-associated glycolytic flux
    (overflow, Y_L_G of mu/Y_X_G) and uptake is repressed in proportion to the
    fraction of maximal growth mu/mu_max(36.5). While cells grow fast lactate
    accumulates; when mu falls (density limitation, NH3, T shift) uptake is
    de-repressed and lactate is reconsumed. The switch is set by the state
    (Xv, G, L, NH3) through mu, not by the calendar or the T step.

    DISSOLVED OXYGEN: ``compute_dissolved_oxygen_state`` (quasi-steady balance with
    O2 enrichment up to ``max_o2_mole_fraction``). kLa is the measured A-Mab Table
    3.22 value of the column immediately below the vessel volume (<2 L: the 2 L
    value as proxy). f_do, the Pasteur deficit h_P = max(0, (15 - DO_real)/15)
    and the death deficit depend only on DO_real.

    HYDRODYNAMIC STRESS: ``compute_hydrodynamic_stress`` (sparge above 0.15 vvm;
    impeller only above 476 W/m3, outside the schema domain). The 47.6 W/m3
    alarm of check_safety_interlocks is independent of the kinetics.

    NUMERICS: [0, duration] is split at every feed day (< duration) and at
    temp_shift_day; each segment is integrated with solve_ivp RK45 (rtol 1e-6,
    atol 1e-9). If RK45 fails or exceeds MAX_RHS_EVALS_PER_SEGMENT the segment is
    re-integrated with Radau. ``method="Radau"`` or ``method="Euler"`` (explicit,
    step ``euler_dt``) are available for verification (check_numerical_convergence).

    FEEDS (days 2, 4, 6, 8, 10, 12 that are < duration; none at harvest):
        static:      v_basal = 0.0462 * V0; pre-feed glucose rule only if
                     config.glucose_feedback_in_static (the Bionova protocol);
        closed_loop: v_basal = 0.0462 * V0 * {1.80 day 8, 1.82 day 10, else 1}
                     plus the pre-feed glucose rule.
    Glucose rule (URS-07), armed when mode == "closed_loop" or
    glucose_feedback_in_static: if G_pre < glucose_min_threshold_g_L (or the
    post-bolus G is), a 500 g/L stock top-up brings G exactly to
    glucose_refill_target_g_L after the bolus. Both volumes are scaled together if they exceed the free
    vessel volume (``bolus_clipped_alarm``), so V(t) <= vessel_volume_L. Every
    bolus is an exact mass balance: C_new = C * V_old / V_new for Xv, Xd, L, NH3
    and P (the feed contains none of them) and
    G_new = (G * V_old + v_basal * G_BOOST_CONC + v_gluc * 500) / V_new.

    OUTPUTS: time series on a 0.1 d grid (the value at a feed day is the
    post-bolus state), ``daily_pre_feed`` (state exactly before the bolus at each
    integer day 0..duration, the timing of the Bionova sampling), DO diagnostics,
    feed events, solver diagnostics and summary metrics.

    MEASURED VALUES (v1.4.0, calibrated constants, DO 30 %, O2 enrichment on, 0.70
    fill; concentrations are identical at 0.25 L and 2.0 L):
        - static, 14 d:      titer 1.9915 g/L, viability 88.22 %, peak VCD 23.96,
                             NH3 11.68 mM, lactate peak 1.341 g/L on day 5.0;
        - closed_loop, 14 d: titer 1.9243 g/L, viability 88.98 %, peak VCD 23.68,
                             NH3 11.32 mM; titer -3.37 % (dilution by the Ark
                             boluses), harvested mass +2.29 %, viability +0.76 pp;
        - 21 d (no feed after day 12): static 2.4946 g/L / 34.41 %, closed_loop
          2.7265 g/L / 39.86 % (NH3 14.98 / 16.58 mM).
        With the default 2 -> 5 g/L rule no top-up fires: the calibrated Cell
        Boost glucose keeps pre-feed G >= 2 g/L on every feed day. These are model
        outputs, not targets.
    """
    kp = CALIBRATED_KINETICS if kinetics is None else kinetics
    if method not in ("RK45", "Radau", "Euler"):
        raise ValueError("method must be 'RK45', 'Radau' or 'Euler'.")

    duration = float(config.duration_days)
    n_grid = int(round(duration / GRID_DT_DAYS)) + 1
    time_days = [round(i * GRID_DT_DAYS, 10) for i in range(n_grid)]
    grid = np.asarray(time_days)

    vessel = float(config.vessel_volume_L)
    V0 = float(config.initial_fill_fraction) * vessel
    V = V0
    kla_eff_h = measured_kla_for_volume(vessel)
    y_o2_max = float(config.max_o2_mole_fraction) if config.o2_enrichment_enabled else Y_O2_AIR
    stress = compute_hydrodynamic_stress(config.power_density_W_m3, config.sparge_vvm)
    sigma = stress["sigma_total"]
    G_MIN = float(config.glucose_min_threshold_g_L)
    G_TARGET = float(config.glucose_refill_target_g_L)
    shift = float(config.temp_shift_day)

    feed_days = [d for d in FEED_DAYS if d < duration - _EPS]
    boundaries = sorted(set(feed_days + ([shift] if _EPS < shift < duration - _EPS else []) + [duration]))

    state = np.array(INITIAL_STATE, dtype=float)
    out = np.empty((6, n_grid))
    out[:, 0] = state
    vol = np.empty(n_grid)
    vol[0] = V0
    daily_pre_feed = {0: _state_dict(state, V0)}
    feed_events = []
    segments = []
    n_bolus_clipped = 0
    clipped_volume_L = 0.0

    # Temperature series from the set-point schedule. The URS-02 audit event is
    # logged at the first grid time with the new set-point, in chronological order
    # with the URS-07 top-ups (a top-up on the same day is logged first, as in v1.3.x).
    temp_series = [
        get_temperature_setpoint(
            t, temp_initial_C=config.temp_initial_C, temp_shift_C=config.temp_shift_C,
            shift_day=config.temp_shift_day,
        )
        for t in time_days
    ]
    shift_index = next((i for i in range(1, n_grid) if temp_series[i] != temp_series[i - 1]), None)
    shift_logged = audit_logger is None or shift_index is None

    def _log_shift():
        _audit_event(
            audit_logger,
            "temperature_setpoint_C", f"{temp_series[shift_index - 1]:.1f}", f"{temp_series[shift_index]:.1f}",
            f"URS-02 automated temperature shift at culture day {time_days[shift_index]:.1f} "
            f"(pre-approved biphasic schedule)",
        )

    t_a = 0.0
    for t_b in boundaries:
        if not shift_logged and time_days[shift_index] < t_b - _EPS:
            _log_shift()
            shift_logged = True
        temp_C = float(config.temp_initial_C) if t_a < shift - _EPS else float(config.temp_shift_C)
        rhs = _build_rhs(kp, temp_C, float(config.do_setpoint_pct), kla_eff_h, y_o2_max, sigma)
        idx = np.nonzero((grid > t_a + _EPS) & (grid <= t_b + _EPS))[0]
        t_out = list(grid[idx])
        end_on_grid = bool(t_out) and abs(t_out[-1] - t_b) < _EPS
        if not end_on_grid:
            t_out.append(t_b)
        y_seg, info = _integrate_segment(rhs, t_a, t_b, state, t_out, method, rtol, atol, euler_dt)
        y_seg = np.maximum(y_seg, 0.0)
        info.update({"t_start": t_a, "t_end": t_b, "temp_C": temp_C})
        segments.append(info)
        n_on_grid = len(idx)
        out[:, idx] = y_seg[:, :n_on_grid]
        vol[idx] = V
        state = y_seg[:, -1].copy()
        for k in idx:
            day = time_days[k]
            if abs(day - round(day)) < _EPS:
                daily_pre_feed[int(round(day))] = _state_dict(out[:, k], V)

        if t_b in feed_days:
            fd = t_b
            G_pre = float(state[2])
            V_old = V
            factor = ARK_ADAPTIVE_FACTORS.get(fd, 1.0) if config.mode == "closed_loop" else 1.0
            v_basal_req = BOOST_FRACTION_OF_V0 * V0 * factor
            G_actual = (G_pre * V_old + v_basal_req * kp.g_boost_conc) / (V_old + v_basal_req)
            v_gluc_req = 0.0
            if (config.mode == "closed_loop" or config.glucose_feedback_in_static) and (
                G_pre < G_MIN or G_actual < G_MIN
            ):
                v_gluc_req = max(
                    0.0,
                    (V_old + v_basal_req) * (G_TARGET - G_actual) / (C_STOCK_GLUCOSE_G_L - G_TARGET),
                )
            headspace = max(0.0, vessel - V_old)
            requested = v_basal_req + v_gluc_req
            scale = 1.0
            if requested > headspace:
                scale = headspace / requested if requested > 0.0 else 0.0
            v_basal = v_basal_req * scale
            v_gluc = v_gluc_req * scale
            if scale < 1.0:
                n_bolus_clipped += 1
                clipped_volume_L += requested - (v_basal + v_gluc)
            pre = dict(zip(STATE_NAMES, (float(v) for v in state)))
            V_new = V_old + v_basal + v_gluc
            if V_new > V_old:
                dilution = V_old / V_new
                state = state * dilution
                state[2] = (G_pre * V_old + v_basal * kp.g_boost_conc + v_gluc * C_STOCK_GLUCOSE_G_L) / V_new
                V = V_new
            k_fd = int(round(fd / GRID_DT_DAYS))
            out[:, k_fd] = state
            vol[k_fd] = V
            feed_events.append({
                "day": fd,
                "step_index_after": k_fd,
                "V_old_L": V_old,
                "V_new_L": V,
                "v_basal_requested_L": v_basal_req,
                "v_gluc_requested_L": v_gluc_req,
                "scale_factor": scale,
                "v_basal_L": v_basal,
                "v_gluc_L": v_gluc,
                "adaptive_factor": factor,
                "glucose_added_g": v_basal * kp.g_boost_conc + v_gluc * C_STOCK_GLUCOSE_G_L,
                "pre": pre,
                "post": dict(zip(STATE_NAMES, (float(v) for v in state))),
            })
            if v_gluc > 0.0 and audit_logger is not None:
                _audit_event(
                    audit_logger,
                    "glucose_g_L", f"{G_actual:.4f}", f"{state[2]:.4f}",
                    f"URS-07 glucose top-up at culture day {fd:.1f}: "
                    f"G_pre_feed {G_pre:.4f} g/L, V_gluc "
                    f"{v_gluc:.6f} L of {C_STOCK_GLUCOSE_G_L:.0f} g/L stock",
                )
        if not shift_logged and abs(time_days[shift_index] - t_b) <= _EPS:
            _log_shift()
            shift_logged = True
        t_a = t_b
    if not shift_logged:
        _log_shift()

    xv_s, xd_s, g_s, l_s, n_s, p_s = out
    total = xv_s + xd_s
    viability = np.where(total > 0.0, 100.0 * xv_s / np.where(total > 0.0, total, 1.0), 0.0)
    oxy = compute_dissolved_oxygen_state(
        xv_s, config.do_setpoint_pct, kla_eff_h,
        o2_enrichment_enabled=config.o2_enrichment_enabled,
        max_o2_mole_fraction=config.max_o2_mole_fraction,
    )
    pre_states = [ev["pre"] for ev in feed_events]
    peak_candidates = [(float(xv_s[i]), time_days[i]) for i in range(n_grid)] + [
        (p["Xv"], ev["day"]) for p, ev in zip(pre_states, feed_events)]
    peak_vcd, peak_vcd_day = max(peak_candidates, key=lambda c: c[0])
    lac_candidates = [(float(l_s[i]), time_days[i]) for i in range(n_grid)] + [
        (p["L"], ev["day"]) for p, ev in zip(pre_states, feed_events)]
    peak_lac, peak_lac_day = max(lac_candidates, key=lambda c: c[0])

    final_volume = float(vol[-1])
    final_titer = float(p_s[-1])
    do_real = oxy["do_real_pct"]
    return {
        "time_days": time_days,
        "vcd": xv_s.tolist(),
        "dead_cell_density": xd_s.tolist(),
        "viability_pct": viability.tolist(),
        "glucose_g_L": g_s.tolist(),
        "lactate_g_L": l_s.tolist(),
        "nh3_mmol_L": n_s.tolist(),
        "titer_g_L": p_s.tolist(),
        "temp_C": temp_series,
        "volume_L": vol.tolist(),
        "do_real_pct": do_real.tolist(),
        "do_eff_pct": do_real.tolist(),  # v1.3.x name, kept as an alias of do_real_pct
        "do_controller_saturated": [bool(s) for s in oxy["do_controller_saturated"]],
        "required_y_o2": oxy["required_y_o2"].tolist(),
        "f_do_metabolic": oxy["f_do"].tolist(),
        "oxygen_supply_ratio": oxy["oxygen_supply_ratio"].tolist(),
        "daily_pre_feed": daily_pre_feed,
        "final_titer_g_L": round(final_titer, 4),
        "final_viability_pct": round(float(viability[-1]), 2),
        "final_nh3_mmol_L": round(float(n_s[-1]), 4),
        "peak_vcd": round(float(peak_vcd), 4),
        "peak_vcd_day": float(peak_vcd_day),
        "peak_lactate_g_L": round(float(peak_lac), 4),
        "peak_lactate_day": float(peak_lac_day),
        "harvested_mass_g": round(final_titer * final_volume, 4),
        "total_feed_volume_L": round(final_volume - V0, 4),
        "initial_volume_L": V0,
        "feed_events": feed_events,
        "bolus_clipped_alarm": n_bolus_clipped > 0,
        "n_bolus_clipped": n_bolus_clipped,
        "clipped_volume_L": round(clipped_volume_L, 6),
        "min_oxygen_supply_ratio": round(float(np.min(oxy["oxygen_supply_ratio"])), 6),
        "min_do_real_pct": round(float(np.min(do_real)), 4),
        "min_do_eff_pct": round(float(np.min(do_real)), 4),
        "min_f_do_metabolic": round(float(np.min(oxy["f_do"])), 6),
        "do_controller_saturated_any": bool(np.any(oxy["do_controller_saturated"])),
        "max_required_y_o2": round(float(np.max(oxy["required_y_o2"])), 6),
        "kla_eff_h_inv": round(kla_eff_h, 4),
        "y_o2_max": y_o2_max,
        "hydrodynamic_stress": stress,
        "solver": {
            "method_requested": method,
            "rtol": rtol,
            "atol": atol,
            "segments": segments,
            "n_segments": len(segments),
            "nfev_total": int(sum(s["nfev"] for s in segments)),
            "fallback_used": any(s["fallback"] for s in segments),
        },
    }
