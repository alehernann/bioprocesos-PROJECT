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
4. A mechanistic fed-batch simulation of CHO-K1 culture (viable/dead cells,
   glucose, lactate, titer) with static and closed-loop feeding strategies. The
   closed-loop adaptive feed follows the Ark Biotech & Culture Biosciences technical
   bulletin (Quint et al., 2026), which reports a +43% titer gain (literature
   value); this model is not calibrated to that value, and its emergent gain is
   reported in simulate_cho_fed_batch (MEASURED VALUES). The micro-scale basis follows the Stratyx(TM) /
   Bionova Scientific 2026 whitepaper.

References
----------
- CMC Biotech Working Group, *A-Mab: A Case Study in Bioprocess Development*, v2.1, CASSS/ISPE, Oct. 2009.
- Y. Quint et al., "Real-Time Closed-Loop Optimization Delivers 43% Titer Improvement...", Ark Biotech & Culture Biosciences Technical Bulletin, 2026.
- ASME BPE-2014, *Bioprocessing Equipment: An International Standard*.
"""

import numpy as np

from src.amab_design_space import (
    AMAB_REF_VS_M_S,
    C_STAR_O2_MMOL_L,
    Q_O2_MMOL_CELL_H,
    compute_kla_h_inv,
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


# Initial working volume as a fraction of vessel_volume_L (30 % headroom for the
# feed train). Module-level so validation can probe the capacity clamp.
INITIAL_FILL_FRACTION = 0.70

# Identity used for events the system records automatically. These events execute
# the pre-approved control strategy (URS-02 schedule, URS-07 feed rule, URS-09..12
# indicators); human_approved=True records that pre-approval, which the
# AuditTrailLogger Annex 22 guardrail requires for every record.
AUDIT_SYSTEM_USER = "system:bioreactor_twin"
AUDIT_SYSTEM_ROLE = "AutomatedControl"


# DO hypoxia response (v1.3.1 C0 fix). Monod in the effective DO normalised at
# 20 % DO, so the factor is exactly 1.0 at and above 20 % and continuous below it.
# The 20 % band is a modeling assumption (not calibrated); A-Mab ran production at
# 30-70 % DO (Table 3.14) and used 20-70 % only in the N-1 seed (Table 3.7).
# K_DO_PCT is NOT CALIBRATED.
K_DO_PCT = 2.0               # % air saturation, Monod half-saturation for O2
DO_HYPOXIA_NORM_PCT = 20.0   # % DO at which do_hypoxia_factor reaches 1.0


def do_hypoxia_factor(do_eff_pct: float) -> float:
    """min(1, (DO/(DO + K_DO_PCT)) / (20/(20 + K_DO_PCT))): 1.0 for DO >= 20 %, C0-continuous."""
    return min(
        1.0,
        (do_eff_pct / (do_eff_pct + K_DO_PCT))
        / (DO_HYPOXIA_NORM_PCT / (DO_HYPOXIA_NORM_PCT + K_DO_PCT)),
    )


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


def simulate_cho_fed_batch(config: ProcessDescription, audit_logger=None) -> dict:
    """Simulate a CHO-K1 fed-batch culture under static or closed-loop feeding.

    When ``audit_logger`` (an ``AuditTrailLogger``) is given, the run appends the
    automatic temperature set-point shift (URS-02) and every glucose top-up with
    V_gluc > 0 (URS-07) to the audit trail. Logging only reads the state; the
    returned results are identical with and without a logger.

    State vector: viable cell density Xv (1e6 cells/mL), dead cell density Xd,
    glucose G (g/L), lactate L (g/L), and titer (g/L). Integrated with an explicit
    Euler scheme at dt = 0.1 d (duration_days / dt + 1 points; 141 at the default
    14 d). The pH set-point and deadband have no kinetic effect.

    UNIFIED KINETIC LAW (v1.2.0)
    ----------------------------
    Growth, death and productivity follow ONE law for both feeding strategies. They
    depend only on the state (G, L, Xv), the temperature setpoint T, the continuous
    shear intensity sigma_shear and the DO coupling (f_do, DO_eff, supply ratio).
    Differences in titer and viability between strategies emerge only from
    the feed trajectories and the resulting G(t) and L(t).

    Temperature dependence (T from the biphasic setpoint schedule): mu_max(T) and
    qp(T) are linearly interpolated between the anchors 34.0 C and 36.5 C and
    clamped to that range (anchor values are modeling assumptions, not calibrated):
        - mu_max: 0.12 1/d at 34.0 C, 0.58 1/d at 36.5 C;
        - qp:     0.0185 at 34.0 C, 0.0115 at 36.5 C [g/(1e9 cell*d)].

    Growth:
        mu = mu_max(T) * G/(G+K_S_G) * K_I_L/(L+K_I_L) * (1 - Xv/X_MAX)
        with K_S_G = 0.5 g/L, K_I_L = 2.5 g/L, X_MAX = 26.0 (1e6 cells/mL).
        dXv/dt = (mu - kd)*Xv ; dXd/dt = kd*Xv

    Cell death:
        kd = KD_BASE + KD_STARVE*K_S_G/(K_S_G+G) + KD_LAC*max(0, L - L_TOX)
             + KD_SHEAR*sigma_shear
        KD_BASE = 0.008 1/d, KD_STARVE = 0.02 1/d (reached as G -> 0),
        KD_LAC = 0.02 1/d per g/L, L_TOX = 1.0 g/L, KD_SHEAR = 0.03 1/d.
        KD_STARVE replaces the old static-only late-culture step (0.018 + 0.0095
        vs the 0.008 closed-loop basal, a difference of about 0.02 1/d). Death is
        now driven by glucose exhaustion instead of by calendar time or by mode.
        These death constants are model assumptions and still need fitting to
        experimental viability data.

    Hydrodynamic shear (v1.3.0, continuous in P/V and sparge):
        sigma_imp    = max(0, (P/V - 47.6) / 47.6)
        sigma_sparge = max(0, (sparge - 0.15) / 0.15)
        sigma_shear  = sigma_imp + sigma_sparge + sigma_imp * sigma_sparge
        sigma_shear is exactly 0.0 at or below both thresholds (nominal P/V 30,
        sparge 0.10) and grows when either source exceeds its threshold. It adds
        KD_SHEAR * sigma_shear to kd and divides qp by (1 + ALPHA_SHEAR_QP *
        sigma_shear). It replaces the former step penalty (kd + 0.03 and fPV = 0.63
        only when P/V > 47.6 AND sparge > 0.15).

    Dissolved oxygen (v1.3.1): kLa_eff = compute_kla_h_inv(AMAB_REF_VS_M_S, P/V)
        (law anchored at the A-Mab 15,000 L point; at 0.25 L or 2 L it is an
        extrapolation; C* = 0.210 mmol/L is a modeling assumption);
        OTR_cap = kLa_eff * C* * max(0, 1 - DO/100)        [mmol/(L*h)]
        OUR     = Xv * 1e9 * Q_O2_MMOL_CELL_H              [mmol/(L*h)]
        ratio   = min(1, OTR_cap / OUR); DO_eff = DO * ratio
        Always applied, C0-continuous (no branch):
        f_do = min(1, (DO_eff/(DO_eff+2))/(20/22)) * ratio (exactly 1 at DO_eff >= 20
        with ratio = 1); Y_L/G *= 1 + 0.8 * max(0, (20 - DO_eff)/20); kd +=
        KD_HYPOXIA * (max(0, (15 - DO_eff)/15) + max(0, (0.85 - ratio)/0.85)),
        exactly 0 at both thresholds. f_do multiplies mu and qp. The DO set-point is ProcessDescription.do_setpoint_pct.

    Titer:
        dTiter/dt = qp(T) * f_do * f_shear_qp * fPV * Xv * TITER_UNIT_CONV,
        f_shear_qp = 1 / (1 + ALPHA_SHEAR_QP * sigma_shear) (fPV applied once).

    Power/volume factor ``fPV``: 1.08 for P/V >= 30 W/m^3, 1.00 for P/V <= 19,
    linear interpolation between 19 and 30. Shear damage is no longer folded into
    fPV; it acts only through sigma_shear.

    GLUCOSE UPTAKE (specific, g/(1e9 cell*d)):
        q_G(G, T) = mu(G, T, ...)/Y_X_G + M_G*G/(G + K_G_UPTAKE)
        The growth term carries the Monod factor G/(G+0.5) and mu_max(T) through mu;
        the maintenance term has its own Monod factor (K_G_UPTAKE = 0.5 g/L), so the
        uptake falls smoothly to zero as glucose is exhausted. Volumetric uptake is
        q_G * Xv.

    LACTATE DYNAMICS (v1.3.1, mechanistic and continuous; no G window, no time
    switch, identical for both feeding strategies; T is the instantaneous T(t)):
        q_L,prod(G, T)    = Y_L_G(T) * q_G(G, T)
        Y_L_G(T)          = linear in T between 0.03 g/g at 34.0 C and 0.18 g/g at
                            36.5 C, clamped to that range
        q_L,cons(G, L, T) = q_L,cons,max(T) * L/(L + K_L) * K_I_G/(K_I_G + G)
                            * (f_basal + (1 - f_basal) * G/(G + K_anap))
        q_L,cons,max(T)   = linear in T between 0.045 at 34.0 C and 0.008 at 36.5 C
                            [g/(1e9 cell*d)]
        dL/dt             = (q_L,prod - q_L,cons) * Xv
    K_L = 0.35 g/L, K_I_G = 4.5 g/L, f_basal = 0.05, K_anap = 0.60 g/L. The
    Crabtree factor represses uptake when glucose is abundant; the anaplerotic
    factor keeps uptake low when glucose is exhausted (5 % basal at G = 0); the
    Monod factor L/(L + K_L) drives q_L,cons to 0 as L -> 0, so
    L stays >= 0 by formulation (max(0, .) is only a numerical safety net). Every
    feed bolus dilutes lactate exactly: L_new = L * V_old / V_new.

    Substrate / lactate yield constants (biomass and glycolysis bookkeeping):
        - Y_X_G    = 1.80 (1e6 cells/mL) biomass yield per g/L glucose consumed;
        - M_G      = 0.175 g/L per (1e6 cells/mL * d) maintenance glucose draw;
        - K_G_UPTAKE = 0.5 g/L Monod half-saturation of the maintenance draw;
        - Y_L_G anchors: 0.18 g/g at 36.5 C, 0.03 g/g at 34.0 C;
        - q_L,cons,max anchors: 0.008 at 36.5 C, 0.045 at 34.0 C g/(1e9 cell*d);
          K_L = 0.35 g/L, K_I_G = 4.5 g/L, f_basal = 0.05, K_anap = 0.60 g/L
          (all uncalibrated, see constants);
        - TITER_UNIT_CONV = 1.0: qp in g/(1e9 cell*d) times Xv in 1e6 cells/mL gives
          g/(L*d); the 1e-9 and 1e9 factors cancel exactly.

    VARIABLE-VOLUME FED-BATCH BALANCE (liquid volume V as a state variable)
    -----------------------------------------------------------------------
    Liquid volume V (L) is tracked dynamically from V_0 = INITIAL_FILL_FRACTION *
    vessel_volume_L = 0.70 * vessel_volume_L (v1.3.0), leaving 30 % headroom for
    the fed-batch bolus train. At every feed event the requested base bolus and
    glucose top-up are scaled together by
    scale_factor = min(1, (vessel_volume_L - V) / (v_basal + v_gluc)), so
    V(t) <= vessel_volume_L always. Each event is recorded in ``feed_events``; if
    any bolus is cut, ``bolus_clipped_alarm`` is True (with ``n_bolus_clipped`` and
    ``clipped_volume_L``).
    At each feed-event crossing of days 2, 4, 6, 8, 10, 12 a feed volume is added
    and all concentrations are diluted by the ratio V_actual / V_new:

        - V_boost = (0.042 + 0.0042) * V_0 in "static" mode; in "closed_loop" the
          same base is scaled by the Ark adaptive factor (1.80 on the day-8
          crossing, 1.82 on the day-10 crossing, 1.0 otherwise). Ark reports feed
          +80 % / +82 % versus the day-0 plan ("by day eight ... up to 82%").
        - G_BOOST_CONC = 12.0 g/L: glucose content of the base feed media.

    FEED SEQUENCE on crossing days 2, 4, 6, 8, 10, 12 (v1.2.0):
        1. The Euler step is integrated first; its result is G_pre_feed.
        2. Base bolus V_boost is requested; the post-bolus glucose would be
           G_actual = (G_pre_feed*V_actual + V_boost*G_BOOST_CONC)/(V_actual + V_boost).
        3. closed_loop only: if G_pre_feed < glucose_min_threshold_g_L or
           G_actual < glucose_min_threshold_g_L (default 2.0; because
           G_BOOST_CONC = 12 g/L is above the threshold, G_actual < threshold
           implies G_pre_feed < threshold, so the rule is the pre-feed check of
           URS-07), a top-up from the
           C_stock = 500 g/L stock is sized to restore G exactly to
           glucose_refill_target_g_L (default 5.0):
           V_gluc = (V + V_boost) * (G_target - G_actual) / (C_stock - G_target).
           In static mode V_gluc = 0.0.
        4. Capacity clamp: both volumes are scaled together if they exceed the
           headspace vessel_volume_L - V.
        5. One exact dilution with the injected volumes:
           C_new = C * V_old / V_new for Xv, Xd, L and Titer, and
           G_new = (G_pre_feed*V_old + v_basal*G_BOOST_CONC + v_gluc*C_stock)/V_new.
           Without the clamp this equals steps 2 and 3 applied in sequence.

    ``config.mode`` is read ONLY in the feed-dosing block (adaptive bolus factor and
    glucose top-up). Reported titers, viabilities and the closed-loop titer gain are
    the real outputs of these equations and are not forced to hit any target band.

    MEASURED VALUES (v1.3.1, defaults, DO 30 %, 14 d; titer, viability and lactate
    are per unit volume and identical at 0.25 L and 2.0 L):
        - static:      titer 1.0537 g/L, viability 80.54 %, L peak 1.2151 g/L
                       (day 7.0), L final 0.8793 g/L, peak VCD 6.8310;
        - closed_loop: titer 1.2189 g/L, viability 90.55 %, L peak 1.3425 g/L
                       (day 7.0), L final 0.5842 g/L, peak VCD 8.1709;
        - emergent titer gain +15.68 %, harvested-mass gain +24.80 %.
        These are outputs of uncalibrated lactate, DO and shear parameters, not
        predictions.

    Returns the time series (``time_days``, ``vcd``, ``viability_pct``,
    ``glucose_g_L``, ``lactate_g_L``, ``titer_g_L``, ``temp_C``, ``volume_L``) and
    the summary metrics ``final_titer_g_L``, ``final_viability_pct``, ``peak_vcd``,
    ``harvested_mass_g`` (= final_titer_g_L * final_volume_L) and
    ``total_feed_volume_L`` (= final_volume_L - V_0).
    """
    # --- Documented substrate / lactate yield constants (v1.2.0) ---
    Y_X_G = 1.80            # (1e6 cells/mL) biomass yield per g/L glucose consumed
    M_G = 0.175             # g/L per (1e6 cells/mL * d) maintenance glucose draw
    # Monod half-saturation for the maintenance glucose draw. Same value as the
    # glucose Ks already used in the growth term mu, so both uptake terms saturate
    # consistently and vanish smoothly as G -> 0.
    K_G_UPTAKE = 0.5        # g/L
    # --- Mechanistic lactate kinetics (v1.3.1) ---
    # Units: specific rates are g/(1e9 cell*d). Xv is in 1e6 cells/mL = 1e9 cells/L,
    # so q [g/(1e9 cell*d)] * Xv [1e9 cell/L] = g/(L*d) with no extra factor
    # (same convention as qp and TITER_UNIT_CONV).
    # Lactate yield on glucose Y_L/G(T), interpolated continuously with the
    # instantaneous T(t) between the two temperature anchors. NOT CALIBRATED.
    Y_LG_SHIFT = 0.03       # g/g at 34.0 C (production phase)
    # 0.18 instead of the nominal 0.22: with 0.22 the lactate peak is 1.45-1.58 g/L,
    # above the 1.0-1.35 g/L day-6/7 band; 0.18 is the largest value tried
    # (0.22, 0.20, 0.18, ...) that puts both modes' peaks inside it.
    Y_LG_GROWTH = 0.18      # g/g at 36.5 C (growth phase)
    Y_L_G_ANCHORS = (Y_LG_SHIFT, Y_LG_GROWTH)  # ordered like T_ANCHORS_C (34.0, 36.5)
    # Maximum specific lactate consumption q_L,cons,max(T), continuous in T: low in
    # the growth phase, active after the shift. 0.008 / 0.045 g/(1e9 cell*d)
    # (= 0.089 / 0.50 pmol/cell/d with MW 90.08 g/mol). NOT CALIBRATED.
    Q_L_CONS_MAX_GROWTH = 0.008   # at 36.5 C
    Q_L_CONS_MAX_SHIFT = 0.045    # at 34.0 C
    Q_L_CONS_MAX_ANCHORS = (Q_L_CONS_MAX_SHIFT, Q_L_CONS_MAX_GROWTH)
    K_L = 0.35              # g/L Monod half-saturation of lactate uptake (NOT CALIBRATED)
    # Crabtree repression of lactate uptake by glucose, K_I_G/(K_I_G + G). NOT CALIBRATED.
    K_I_G = 4.5             # g/L
    # Anaplerotic modulation f_basal + (1 - f_basal) * G/(G + K_ANAP): lactate is
    # oxidised mainly when some glucose-derived carbon feeds the TCA cycle; a 5 %
    # basal uptake remains at G = 0. NOT CALIBRATED.
    F_BASAL = 0.05          # dimensionless
    K_ANAP = 0.60           # g/L
    # --- Dissolved-oxygen coupling (v1.3.1) ---
    # Growth and productivity are throttled by do_hypoxia_factor(DO_eff) times the
    # supply ratio; lactate yield rises below 20 % (Pasteur effect) and severe
    # hypoxia adds death. All NOT CALIBRATED.
    DO_LOW_PCT = DO_HYPOXIA_NORM_PCT  # % below which the Pasteur yield rise starts
    DO_HYPOXIA_PCT = 15.0   # % severe-hypoxia onset (effective DO)
    RATIO_HYPOXIA = 0.85    # supply ratio below which severe hypoxia starts
    Y_LG_HYPOXIA_GAIN = 0.8  # max relative rise of Y_L/G as DO_eff -> 0
    KD_HYPOXIA = 0.05       # 1/d extra death at full hypoxic deficit (NOT CALIBRATED)
    TITER_UNIT_CONV = 1.0   # g/(1e9 cell*d) * (1e6 cells/mL) -> g/(L*d); factors cancel

    # --- Unified kinetic law (v1.2.0): identical for every feeding mode ---
    # Temperature anchors: values previously used for the growth (36.5 C) and
    # production (34.0 C) phases, now read as functions of T.
    T_ANCHORS_C = (34.0, 36.5)
    MU_MAX_ANCHORS = (0.12, 0.58)       # 1/d
    QP_ANCHORS = (0.0185, 0.0115)       # g/(1e9 cell*d); higher qp at lower T
    K_S_G = 0.5             # g/L glucose half-saturation (growth and starvation)
    K_I_L = 2.5             # g/L lactate inhibition constant on growth
    X_MAX = 26.0            # 1e6 cells/mL logistic carrying capacity
    KD_BASE = 0.008         # 1/d basal death rate
    KD_STARVE = 0.02        # 1/d extra death at full glucose starvation (G -> 0)
    KD_LAC = 0.02           # 1/d per g/L lactate above L_TOX
    L_TOX = 1.0             # g/L lactate toxicity onset
    KD_SHEAR = 0.03         # 1/d extra death per unit of sigma_shear
    # Shear penalty on qp: qp / (1 + ALPHA_SHEAR_QP * sigma_shear). NOT CALIBRATED:
    # 1.0 is a neutral first-order assumption (qp halves at sigma_shear = 1). It
    # must be fitted to productivity-vs-shear data and must not be tuned to hit a
    # target titer.
    ALPHA_SHEAR_QP = 1.0

    # --- Variable-volume fed-batch balance constants ---
    C_STOCK = 500.0         # g/L concentrated glucose stock (closed_loop top-up)
    G_TARGET = float(config.glucose_refill_target_g_L)  # g/L glucose target for the closed_loop top-up
    G_MIN = float(config.glucose_min_threshold_g_L)     # g/L top-up trigger
    G_BOOST_CONC = 12.0     # g/L glucose in the base feed media

    dt = 0.1
    duration = float(config.duration_days)
    n_steps = int(round(duration / dt)) + 1
    time_days = [round(i * dt, 10) for i in range(n_steps)]

    # Initial state
    Xv = 0.7    # 1e6 cells/mL
    Xd = 0.02
    G = 6.0     # g/L
    L = 0.1     # g/L
    Titer = 0.0

    # Liquid-volume state: initial working volume = INITIAL_FILL_FRACTION of the
    # vessel; V(t) is clamped to vessel_volume_L at every feed event.
    V_0 = INITIAL_FILL_FRACTION * config.vessel_volume_L
    V = V_0

    # Power/volume productivity factor and high-shear penalty
    pv = config.power_density_W_m3
    # Oxygen supply: kLa from the same power law as compute_scale_up_engineering
    # (A-Mab Eq. 4 form, anchored at the A-Mab 15,000 L point), at P/V of this run and
    # the A-Mab reference Vs (the twin carries no vessel geometry, so Vs is held
    # constant; A-Mab p.98 notes P/V and Vs need not be constant when scaling). At
    # 0.25 L or 2 L this is an extrapolation. The DO set-point is
    # ProcessDescription.do_setpoint_pct.
    do_pct = float(config.do_setpoint_pct)
    kla_eff_h = compute_kla_h_inv(AMAB_REF_VS_M_S, pv)
    otr_cap_mmol_L_h = kla_eff_h * C_STAR_O2_MMOL_L * max(0.0, 1.0 - do_pct / 100.0)
    # Continuous shear intensity from impeller power and sparge (0.0 below both).
    sigma_imp = max(0.0, (pv - 47.6) / 47.6)
    sigma_sparge = max(0.0, (config.sparge_vvm - 0.15) / 0.15)
    sigma_shear = sigma_imp + sigma_sparge + (sigma_imp * sigma_sparge)
    f_shear_qp = 1.0 / (1.0 + ALPHA_SHEAR_QP * sigma_shear)

    if pv >= 30.0:
        fPV = 1.08
    elif pv <= 19.0:
        fPV = 1.00
    else:
        fPV = 1.00 + (1.08 - 1.00) * (pv - 19.0) / (30.0 - 19.0)

    feed_days = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
    fed_done = {d: False for d in feed_days}
    feed_events = []  # per-bolus volume and mass-balance record
    n_bolus_clipped = 0
    clipped_volume_L = 0.0

    vcd_series = []
    viability_series = []
    glucose_series = []
    lactate_series = []
    titer_series = []
    temp_series = []
    volume_series = []
    o2_ratio_series = []
    do_eff_series = []
    f_do_series = []

    peak_vcd = Xv

    for i in range(n_steps):
        t = time_days[i]

        temp_C = get_temperature_setpoint(
            t,
            temp_initial_C=config.temp_initial_C,
            temp_shift_C=config.temp_shift_C,
            shift_day=config.temp_shift_day,
        )
        if audit_logger is not None and i > 0 and temp_C != prev_temp_C:
            _audit_event(
                audit_logger,
                "temperature_setpoint_C", f"{prev_temp_C:.1f}", f"{temp_C:.1f}",
                f"URS-02 automated temperature shift at culture day {t:.1f} "
                f"(pre-approved biphasic schedule)",
            )
        prev_temp_C = temp_C

        # Temperature-dependent kinetic parameters (same law for every mode).
        # Linear interpolation between the two anchors (modeling assumptions, not
        # calibrated), clamped to the anchor range (no extrapolation outside
        # 34.0-36.5 C).
        mu_max = float(np.interp(temp_C, T_ANCHORS_C, MU_MAX_ANCHORS))
        qp = float(np.interp(temp_C, T_ANCHORS_C, QP_ANCHORS))

        # Oxygen balance (mmol/(L*h) on both sides): OTR = kLa [1/h] * C* [mmol/L];
        # OUR = Xv [1e6 cell/mL] * 1e9 [cell/L per 1e6 cell/mL] * qO2 [mmol/(cell*h)].
        our_demand_mmol_L_h = (Xv * 1.0e9) * Q_O2_MMOL_CELL_H
        oxygen_supply_ratio = min(1.0, otr_cap_mmol_L_h / max(1e-9, our_demand_mmol_L_h))
        do_eff_pct = do_pct * oxygen_supply_ratio
        # C0-continuous DO response, always applied (no branch): each term is
        # exactly 1 (or 0 for the death ramp) at and above its threshold.
        f_do_metabolic = do_hypoxia_factor(do_eff_pct) * oxygen_supply_ratio
        y_lg_do_factor = 1.0 + Y_LG_HYPOXIA_GAIN * max(0.0, (DO_LOW_PCT - do_eff_pct) / DO_LOW_PCT)
        hypoxic_deficit = (
            max(0.0, (DO_HYPOXIA_PCT - do_eff_pct) / DO_HYPOXIA_PCT)
            + max(0.0, (RATIO_HYPOXIA - oxygen_supply_ratio) / RATIO_HYPOXIA)
        )

        # Record current state
        o2_ratio_series.append(oxygen_supply_ratio)
        do_eff_series.append(do_eff_pct)
        f_do_series.append(f_do_metabolic)
        total_cells = Xv + Xd
        viability_pct = 100.0 * Xv / total_cells if total_cells > 0 else 0.0
        vcd_series.append(Xv)
        viability_series.append(viability_pct)
        glucose_series.append(G)
        lactate_series.append(L)
        titer_series.append(Titer)
        temp_series.append(temp_C)
        volume_series.append(V)
        if Xv > peak_vcd:
            peak_vcd = Xv

        if i == n_steps - 1:
            break

        # Kinetics: one law for every mode; only the state (G, L, T, Xv), shear and
        # the DO coupling act.
        mu = (
            mu_max * (G / (G + K_S_G)) * (K_I_L / (L + K_I_L)) * (1 - Xv / X_MAX)
            * f_do_metabolic
        )

        # Cell-death rate: basal + glucose starvation (inverse Monod, -> KD_STARVE
        # as G -> 0) + lactate toxicity above L_TOX + continuous shear term.
        kd = (
            KD_BASE
            + KD_STARVE * K_S_G / (K_S_G + G)
            + KD_LAC * max(0.0, L - L_TOX)
            + KD_SHEAR * sigma_shear
            + KD_HYPOXIA * hypoxic_deficit
        )

        dXv = (mu - kd) * Xv
        dXd = kd * Xv

        # Specific glucose uptake q_G(G, T): growth-associated (Monod and mu_max(T)
        # already inside mu) plus maintenance with its own Monod saturation.
        q_G = mu / Y_X_G + M_G * (G / (G + K_G_UPTAKE))
        glucose_uptake = q_G * Xv
        # Numerical guard only: one Euler step cannot remove more glucose than exists.
        glucose_uptake = min(glucose_uptake, G / dt) if dt > 0 else glucose_uptake
        dG = -glucose_uptake

        # Mechanistic lactate balance (no G window, no time switch):
        # production follows glucose uptake with a T-dependent yield; consumption
        # is Monod in L, repressed by glucose (Crabtree) plus a basal anaplerotic term.
        y_l_g = float(np.interp(temp_C, T_ANCHORS_C, Y_L_G_ANCHORS)) * y_lg_do_factor
        lactate_prod = y_l_g * glucose_uptake                     # g/(L*d)
        q_l_cons_max = float(np.interp(temp_C, T_ANCHORS_C, Q_L_CONS_MAX_ANCHORS))
        q_L_cons = (
            q_l_cons_max
            * (L / (L + K_L))
            * (K_I_G / (K_I_G + G))
            * (F_BASAL + (1.0 - F_BASAL) * G / (G + K_ANAP))
        )
        dL = lactate_prod - q_L_cons * Xv

        # fPV and the shear factor are applied exactly once, identically in every mode.
        dTiter = qp * f_do_metabolic * f_shear_qp * fPV * Xv * TITER_UNIT_CONV

        # Euler update
        Xv = max(0.0, Xv + dXv * dt)
        Xd = max(0.0, Xd + dXd * dt)
        G = max(0.0, G + dG * dt)
        L = max(0.0, L + dL * dt)  # safety net; Monod in L keeps L >= 0
        Titer = max(0.0, Titer + dTiter * dt)

        # Feeding at the crossing of each feed day -- variable-volume balance.
        t_next = time_days[i + 1]
        for fd in feed_days:
            if (not fed_done[fd]) and (t < fd <= t_next + 1e-9):
                # Step 1: the Euler step above has already been integrated; this is
                # the glucose the culture actually reached before the feed.
                G_pre_feed = G
                V_actual = V

                # Step 2: requested base feed bolus. The Ark adaptive factor scales it
                # in closed_loop on the day-8 / day-10 crossings (+80 % / +82 % vs
                # the day-0 plan, Ark).
                if config.mode == "closed_loop":
                    if fd == 8.0:
                        adaptive_factor = 1.80
                    elif fd == 10.0:
                        adaptive_factor = 1.82
                    else:
                        adaptive_factor = 1.0
                else:
                    adaptive_factor = 1.0
                v_basal_req_L = (0.042 + 0.0042) * V_0 * adaptive_factor

                # Step 3: requested closed_loop glucose top-up from the C_STOCK stock,
                # sized (before the capacity clamp) to bring G exactly to G_TARGET
                # after the base bolus:
                #   G_actual = (G_pre_feed*V + v_basal*G_BOOST_CONC) / (V + v_basal)
                #   (G_actual*(V + v_basal) + v_gluc*C_STOCK) / (V + v_basal + v_gluc) = G_TARGET
                G_actual = (
                    G_pre_feed * V_actual + v_basal_req_L * G_BOOST_CONC
                ) / (V_actual + v_basal_req_L)
                v_gluc_req_L = 0.0
                if config.mode == "closed_loop" and (
                    G_pre_feed < G_MIN or G_actual < G_MIN
                ):
                    v_gluc_req_L = max(
                        0.0,
                        (V_actual + v_basal_req_L) * (G_TARGET - G_actual)
                        / (C_STOCK - G_TARGET),
                    )

                # Step 4: vessel-capacity clamp. Both volumes are scaled together so
                # V(t) never exceeds vessel_volume_L.
                available_headspace_L = max(0.0, config.vessel_volume_L - V_actual)
                total_requested_bolo_L = v_basal_req_L + v_gluc_req_L
                scale_factor = 1.0
                if total_requested_bolo_L > available_headspace_L:
                    scale_factor = (
                        available_headspace_L / total_requested_bolo_L
                        if total_requested_bolo_L > 0 else 0.0
                    )
                v_basal_L = v_basal_req_L * scale_factor
                v_gluc_L = v_gluc_req_L * scale_factor
                if scale_factor < 1.0:
                    n_bolus_clipped += 1
                    clipped_volume_L += total_requested_bolo_L - (v_basal_L + v_gluc_L)

                # Step 5: exact mass balance over the volume actually injected.
                # Every concentration is diluted as C * V_old / V_new; glucose adds
                # the mass contained in the injected basal medium and stock.
                V_new = V_actual + v_basal_L + v_gluc_L
                if V_new > V_actual:
                    dilution = V_actual / V_new
                    pre = {"Xv": Xv, "Xd": Xd, "G": G_pre_feed, "L": L, "Titer": Titer}
                    Xv *= dilution
                    Xd *= dilution
                    L *= dilution
                    Titer *= dilution
                    G = (
                        G_pre_feed * V_actual
                        + v_basal_L * G_BOOST_CONC
                        + v_gluc_L * C_STOCK
                    ) / V_new
                    V = V_new
                else:
                    pre = {"Xv": Xv, "Xd": Xd, "G": G_pre_feed, "L": L, "Titer": Titer}

                feed_events.append(
                    {
                        "day": fd,
                        "step_index_after": i + 1,
                        "V_old_L": V_actual,
                        "V_new_L": V,
                        "v_basal_requested_L": v_basal_req_L,
                        "v_gluc_requested_L": v_gluc_req_L,
                        "scale_factor": scale_factor,
                        "v_basal_L": v_basal_L,
                        "v_gluc_L": v_gluc_L,
                        "glucose_added_g": v_basal_L * G_BOOST_CONC + v_gluc_L * C_STOCK,
                        "pre": pre,
                    }
                )

                if v_gluc_L > 0.0 and audit_logger is not None:
                    _audit_event(
                        audit_logger,
                        "glucose_g_L", f"{G_actual:.4f}", f"{G:.4f}",
                        f"URS-07 glucose top-up at culture day {fd:.1f}: "
                        f"G_pre_feed {G_pre_feed:.4f} g/L, V_gluc "
                        f"{v_gluc_L:.6f} L of {C_STOCK:.0f} g/L stock",
                    )

                fed_done[fd] = True

    final_titer = titer_series[-1]
    final_viability = viability_series[-1]
    final_volume = volume_series[-1]
    harvested_mass_g = float(final_titer) * float(final_volume)
    total_feed_volume_L = float(final_volume) - V_0

    return {
        "time_days": time_days,
        "vcd": vcd_series,
        "viability_pct": viability_series,
        "glucose_g_L": glucose_series,
        "lactate_g_L": lactate_series,
        "titer_g_L": titer_series,
        "temp_C": temp_series,
        "volume_L": volume_series,
        "final_titer_g_L": round(float(final_titer), 4),
        "final_viability_pct": round(float(final_viability), 2),
        "peak_vcd": round(float(peak_vcd), 4),
        "harvested_mass_g": round(harvested_mass_g, 4),
        "total_feed_volume_L": round(total_feed_volume_L, 4),
        "feed_events": feed_events,
        "bolus_clipped_alarm": n_bolus_clipped > 0,
        "n_bolus_clipped": n_bolus_clipped,
        "clipped_volume_L": round(clipped_volume_L, 6),
        "oxygen_supply_ratio": o2_ratio_series,
        "do_eff_pct": do_eff_series,
        "f_do_metabolic": f_do_series,
        "min_oxygen_supply_ratio": round(min(o2_ratio_series), 6),
        "min_do_eff_pct": round(min(do_eff_series), 4),
        "min_f_do_metabolic": round(min(f_do_series), 6),
        "kla_eff_h_inv": round(kla_eff_h, 4),
    }
