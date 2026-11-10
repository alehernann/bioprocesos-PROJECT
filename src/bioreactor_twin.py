"""CHO-K1 fed-batch mechanistic digital twin plus control and safety logic.

This module provides:

1. A split-range pH controller (CO2 valve vs. base pump) around a deadband.
2. A biphasic temperature-shift setpoint schedule.
3. GxP safety interlocks: hydrodynamic-shear alarm (A-Mab / Ma et al. 2002 shear
   context), CIP/SIP interlocks and sterilization F0 integration. The 1.52 m/s
   (5 ft/s) CIP pipe velocity criterion follows ASME BPE-2014.
4. A mechanistic fed-batch simulation of CHO-K1 culture (viable/dead cells,
   glucose, lactate, titer) with static and closed-loop feeding strategies. The
   closed-loop adaptive feed follows the Ark Biotech & Culture Biosciences technical
   bulletin (Quint et al., 2026), which reports a +43% titer gain; this model is
   not calibrated to that value, and its emergent gain is +14.66% (see
   simulate_cho_fed_batch). The micro-scale basis follows the Stratyx(TM) /
   Bionova Scientific 2026 whitepaper.

References
----------
- CMC Biotech Working Group, *A-Mab: A Case Study in Bioprocess Development*, v2.1, CASSS/ISPE, Oct. 2009.
- Y. Quint et al., "Real-Time Closed-Loop Optimization Delivers 43% Titer Improvement...", Ark Biotech & Culture Biosciences Technical Bulletin, 2026.
- ASME BPE-2014, *Bioprocessing Equipment: An International Standard*.
"""

import math

import numpy as np

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
    """Biphasic temperature-shift schedule.

    Returns the initial (growth-phase) temperature before ``shift_day`` and the
    shifted (production-phase) temperature on or after it.
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
) -> dict:
    """Evaluate the GxP safety interlocks for the bioreactor skid.

    When ``audit_logger`` (an ``AuditTrailLogger``) is given, every interlock trip
    is appended to the audit trail: high-shear alarm, CIP blocked during an active
    batch, CIP velocity below 1.52 m/s, and SIP not sterile. Logging does not change
    the returned flags.

    Returns five boolean/float flags:

    - ``high_shear_alarm``: hydrodynamic-shear alarm (P/V > 47.6 W/m^3 and
      sparge > 0.15 vvm), per A-Mab / shear-sensitivity context.
    - ``cip_interlock_blocked``: CIP valve requested while a batch is active.
    - ``cip_velocity_compliant``: CIP pipe velocity >= 1.52 m/s (ASME BPE-2014, 5 ft/s).
    - ``f0_minutes``: accumulated sterilization lethality F0 at 121.1 C reference.
    - ``sip_sterile_compliant``: F0 >= 15 min and all SIP temperatures >= 121.1 C.
    """
    high_shear_alarm = bool(power_density_W_m3 > 47.6 and sparge_vvm > 0.15)
    cip_interlock_blocked = bool(batch_active and cip_valve_requested)
    cip_velocity_compliant = bool(cip_pipe_velocity_m_s >= 1.52)
    f0_minutes = sum(
        (10.0 ** ((T - 121.1) / 10.0)) * dt_min for T in sip_temps_C if T >= 100.0
    )
    sip_sterile_compliant = bool(
        f0_minutes >= 15.0 and min(sip_temps_C, default=0.0) >= 121.1
    )

    if audit_logger is not None:
        if high_shear_alarm:
            _audit_event(
                audit_logger,
                "interlock.high_shear_alarm", "False", "True",
                f"URS-09 interlock trip: P/V {power_density_W_m3} W/m3 > 47.6 and "
                f"sparge {sparge_vvm} vvm > 0.15",
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
    }


# Identity used for events the system records automatically. These events execute
# the pre-approved, validated control strategy (URS-02 schedule, URS-07 feed rule,
# URS-09..12 interlocks); human_approved=True records that pre-approval, which the
# AuditTrailLogger Annex 22 guardrail requires for every record.
AUDIT_SYSTEM_USER = "system:bioreactor_twin"
AUDIT_SYSTEM_ROLE = "AutomatedControl"


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


def _logistic(x: float) -> float:
    """Numerically stable logistic function 1 / (1 + exp(-x))."""
    if x >= 0.0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def simulate_cho_fed_batch(config: ProcessDescription, audit_logger=None) -> dict:
    """Simulate a CHO-K1 fed-batch culture under static or closed-loop feeding.

    When ``audit_logger`` (an ``AuditTrailLogger``) is given, the run appends the
    automatic temperature set-point shift (URS-02) and every glucose top-up with
    V_gluc > 0 (URS-07) to the audit trail. Logging only reads the state; the
    returned results are identical with and without a logger.

    State vector: viable cell density Xv (1e6 cells/mL), dead cell density Xd,
    glucose G (g/L), lactate L (g/L), and titer (g/L). Integrated with an explicit
    Euler scheme at dt = 0.1 d (141 points over 14 d).

    UNIFIED KINETIC LAW (v1.2.0)
    ----------------------------
    Growth, death and productivity follow ONE law for both feeding strategies. They
    depend only on the state (G, L, Xv), the temperature setpoint T and the shear
    flag. Differences in titer and viability between strategies emerge only from
    the feed trajectories and the resulting G(t) and L(t).

    Temperature dependence (T from the biphasic setpoint schedule): mu_max(T) and
    qp(T) are linearly interpolated between the anchors 34.0 C and 36.5 C and
    clamped to that range:
        - mu_max: 0.12 1/d at 34.0 C, 0.58 1/d at 36.5 C;
        - qp:     0.0185 at 34.0 C, 0.0115 at 36.5 C [g/(1e9 cell*d)].

    Growth:
        mu = mu_max(T) * G/(G+K_S_G) * K_I_L/(L+K_I_L) * (1 - Xv/X_MAX)
        with K_S_G = 0.5 g/L, K_I_L = 2.5 g/L, X_MAX = 26.0 (1e6 cells/mL).
        dXv/dt = (mu - kd)*Xv ; dXd/dt = kd*Xv

    Cell death:
        kd = KD_BASE + KD_STARVE*K_S_G/(K_S_G+G) + KD_LAC*max(0, L - L_TOX)
             + KD_SHEAR*[high shear]
        KD_BASE = 0.008 1/d, KD_STARVE = 0.02 1/d (reached as G -> 0),
        KD_LAC = 0.02 1/d per g/L, L_TOX = 1.0 g/L, KD_SHEAR = 0.03 1/d.
        KD_STARVE replaces the old static-only late-culture step (0.018 + 0.0095
        vs the 0.008 closed-loop basal, a difference of about 0.02 1/d). Death is
        now driven by glucose exhaustion instead of by calendar time or by mode.
        These death constants are model assumptions and still need fitting to
        experimental viability data.

    Titer:
        dTiter/dt = qp(T) * fPV * Xv * TITER_UNIT_CONV (fPV applied exactly once).

    Power/volume factor ``fPV``: 1.08 for P/V >= 30 W/m^3, 1.00 for P/V <= 19,
    linear interpolation between 19 and 30; under high shear (P/V > 47.6 and
    sparge > 0.15) fPV = 0.63 (qp penalised -37%) and viability is penalised via
    KD_SHEAR.

    GLUCOSE UPTAKE (v1.2.0):
        q_G = mu*Xv/Y_X_G + M_G*Xv*G/(G + K_G_UPTAKE)
        The growth term already carries the Monod factor G/(G+0.5) through mu; the
        maintenance term gets its own Monod factor (K_G_UPTAKE = 0.5 g/L), so the
        total uptake falls smoothly to zero as glucose is exhausted.

    LACTATE DYNAMICS (v1.2.0): three regimes driven ONLY by G, L and t, identical
    for both feeding strategies, blended with logistic weights so dL/dt is
    continuous (s(x) = 1/(1+exp(-x)), W_G = 0.1 g/L, W_T = 0.1 d):
        w_over = s((G - 5.0)/W_G)
        w_cons = s((t - 6.0)/W_T) * s((G - 2.0)/W_G) * s((5.0 - G)/W_G)
        dL = Y_L_BASE*q_G*(1 - w_cons) + Y_L_OVERFLOW*q_G*w_over
             - K_L_CONSUME*L*Xv*w_cons
    Far from the thresholds this reduces to the piecewise regimes:
        - overflow,        G > 5.0:                    (Y_L_BASE + Y_L_OVERFLOW)*q_G
        - net consumption, t >= 6.0, 2.0 <= G <= 5.0:  -K_L_CONSUME * L * Xv
        - basal, otherwise:                            Y_L_BASE * q_G

    Substrate / lactate yield constants (biomass and glycolysis bookkeeping):
        - Y_X_G    = 1.80 (1e6 cells/mL) biomass yield per g/L glucose consumed;
        - M_G      = 0.175 g/L per (1e6 cells/mL * d) maintenance glucose draw;
        - K_G_UPTAKE = 0.5 g/L Monod half-saturation of the maintenance draw;
        - Y_L_BASE = 0.08 g lactate per g glucose (baseline glycolysis);
        - Y_L_OVERFLOW = 0.40 extra g lactate per g glucose above the overflow
          threshold (Warburg-type overflow metabolism of CHO cells);
        - G_OVERFLOW_THRESHOLD = 5.0 g/L glucose above which overflow lactate applies;
        - K_L_CONSUME = 0.012 1/d per (1e6 cells/mL) net lactate-consumption rate;
        - TITER_UNIT_CONV = 1.0: qp in g/(1e9 cell*d) times Xv in 1e6 cells/mL gives
          g/(L*d); the 1e-9 and 1e9 factors cancel exactly.

    VARIABLE-VOLUME FED-BATCH BALANCE (liquid volume V as a state variable)
    -----------------------------------------------------------------------
    Liquid volume V (L) is tracked dynamically from V_0 = 0.76 * vessel_volume_L
    (a 76% initial working volume, leaving headroom for the fed-batch bolus train).
    At each feed-event crossing of days 2, 4, 6, 8, 10, 12 a feed volume is added
    and all concentrations are diluted by the ratio V_actual / V_new:

        - V_boost = (0.042 + 0.0042) * V_0 in "static" mode; in "closed_loop" the
          same base is scaled by the Ark adaptive factor (1.80 on the day-8
          crossing, 1.82 on the day-10 crossing, 1.0 otherwise), consistent with
          the glucose front-loading pattern.
        - G_BOOST_CONC = 12.0 g/L: glucose content of the base feed media.

    FEED SEQUENCE on crossing days 2, 4, 6, 8, 10, 12 (v1.2.0):
        1. The Euler step is integrated first; its result is G_pre_feed.
        2. Base bolus V_boost is added. Xv, Xd, L and Titer are diluted by
           V_actual/(V_actual + V_boost) and
           G_actual = (G_pre_feed*V_actual + V_boost*G_BOOST_CONC)/(V_actual + V_boost).
        3. closed_loop only: if G_pre_feed < glucose_min_threshold_g_L or
           G_actual < glucose_min_threshold_g_L (default 2.0), a top-up from the
           C_stock = 500 g/L stock is sized to restore G exactly to
           glucose_refill_target_g_L (default 5.0):
           V_gluc = V * (G_target - G_actual) / (C_stock - G_target),
           followed by a second dilution of Xv, Xd, L and Titer. In static mode
           V_gluc = 0.0.

    ``config.mode`` is read ONLY in the feed-dosing block (adaptive bolus factor and
    glucose top-up). Reported titers, viabilities and the closed-loop titer gain are
    the real outputs of these equations and are not forced to hit any target band.

    MEASURED VALUES (v1.2.0, defaults, 14 d; identical titer and viability at 0.25 L
    and 2.0 L because the balance is per unit volume):
        - static:      titer 1.0164 g/L, viability 81.17 %, min/max G 0.0057/6.0 g/L,
                       max/final L 1.0889/1.0783 g/L;
        - closed_loop: titer 1.1654 g/L, viability 91.56 %, min/max G 0.7241/6.0 g/L,
                       max/final L 1.0001/0.6498 g/L;
        - emergent titer gain +14.66 %; harvested mass 0.2466 vs 0.3048 g (0.25 L)
          and 1.9731 vs 2.4384 g (2.0 L).

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
    Y_L_BASE = 0.08         # g lactate per g glucose (baseline glycolysis)
    Y_L_OVERFLOW = 0.40     # extra g lactate per g glucose above overflow threshold
    G_OVERFLOW_THRESHOLD = 5.0  # g/L glucose above which overflow lactate applies
    # Net lactate-consumption window, defined only by state (G) and time (t).
    G_CONSUME_LOW = 2.0     # g/L lower glucose bound of the consumption window
    G_CONSUME_HIGH = 5.0    # g/L upper glucose bound of the consumption window
    T_CONSUME_START = 6.0   # d, earliest time for net lactate consumption
    K_L_CONSUME = 0.012     # 1/d per (1e6 cells/mL) net lactate consumption
    # Logistic transition widths for the lactate regimes (numerical smoothing).
    W_G = 0.1               # g/L
    W_T = 0.1               # d (one Euler step)
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
    KD_SHEAR = 0.03         # 1/d high-shear death penalty

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

    # Liquid-volume state: 76% initial working volume of the vessel.
    V_0 = 0.76 * config.vessel_volume_L
    V = V_0

    # Power/volume productivity factor and high-shear penalty
    pv = config.power_density_W_m3
    high_shear = (pv > 47.6) and (config.sparge_vvm > 0.15)
    if high_shear:
        fPV = 0.63
    elif pv >= 30.0:
        fPV = 1.08
    elif pv <= 19.0:
        fPV = 1.00
    else:
        fPV = 1.00 + (1.08 - 1.00) * (pv - 19.0) / (30.0 - 19.0)

    feed_days = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
    fed_done = {d: False for d in feed_days}

    vcd_series = []
    viability_series = []
    glucose_series = []
    lactate_series = []
    titer_series = []
    temp_series = []
    volume_series = []

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
        # Linear interpolation between the two calibrated anchors, clamped to the
        # anchor range (no extrapolation outside 34.0-36.5 C).
        mu_max = float(np.interp(temp_C, T_ANCHORS_C, MU_MAX_ANCHORS))
        qp = float(np.interp(temp_C, T_ANCHORS_C, QP_ANCHORS))

        # Record current state
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

        # Kinetics: one law for every mode; only the state (G, L, T, Xv, shear) acts.
        mu = mu_max * (G / (G + K_S_G)) * (K_I_L / (L + K_I_L)) * (1 - Xv / X_MAX)

        # Cell-death rate: basal + glucose starvation (inverse Monod, -> KD_STARVE
        # as G -> 0) + lactate toxicity above L_TOX + high-shear penalty.
        kd = (
            KD_BASE
            + KD_STARVE * K_S_G / (K_S_G + G)
            + KD_LAC * max(0.0, L - L_TOX)
            + (KD_SHEAR if high_shear else 0.0)
        )

        dXv = (mu - kd) * Xv
        dXd = kd * Xv

        # Substrate consumption: growth-associated (Monod already inside mu) plus
        # maintenance with its own Monod saturation, so q_G -> 0 smoothly as G -> 0.
        glucose_uptake = (mu * Xv) / Y_X_G + M_G * Xv * (G / (G + K_G_UPTAKE))
        # Numerical guard only: one Euler step cannot remove more glucose than exists.
        glucose_uptake = min(glucose_uptake, G / dt) if dt > 0 else glucose_uptake
        dG = -glucose_uptake

        # Lactate dynamics: overflow / net consumption / basal regimes blended with
        # logistic weights in G and t, so dL/dt is continuous. In the limits far
        # from the thresholds it reduces exactly to the three piecewise regimes.
        w_over = _logistic((G - G_OVERFLOW_THRESHOLD) / W_G)
        w_cons = (
            _logistic((t - T_CONSUME_START) / W_T)
            * _logistic((G - G_CONSUME_LOW) / W_G)
            * _logistic((G_CONSUME_HIGH - G) / W_G)
        )
        dL = (
            Y_L_BASE * glucose_uptake * (1.0 - w_cons)
            + Y_L_OVERFLOW * glucose_uptake * w_over
            - K_L_CONSUME * L * Xv * w_cons
        )

        # fPV is applied exactly once, identically in every mode.
        dTiter = qp * fPV * Xv * TITER_UNIT_CONV

        # Euler update
        Xv = max(0.0, Xv + dXv * dt)
        Xd = max(0.0, Xd + dXd * dt)
        G = max(0.0, G + dG * dt)
        L = max(0.0, L + dL * dt)
        Titer = max(0.0, Titer + dTiter * dt)

        # Feeding at the crossing of each feed day -- variable-volume balance.
        t_next = time_days[i + 1]
        for fd in feed_days:
            if (not fed_done[fd]) and (t < fd <= t_next + 1e-9):
                # Step 1: the Euler step above has already been integrated; this is
                # the glucose the culture actually reached before the feed.
                G_pre_feed = G
                V_actual = V

                # Step 2: base feed bolus. The Ark adaptive factor scales it in
                # closed_loop on the day-8 / day-10 crossings.
                if config.mode == "closed_loop":
                    if fd == 8.0:
                        adaptive_factor = 1.80
                    elif fd == 10.0:
                        adaptive_factor = 1.82
                    else:
                        adaptive_factor = 1.0
                else:
                    adaptive_factor = 1.0

                # Base feed bolus volume (static: unscaled; closed_loop: scaled).
                V_boost = (0.042 + 0.0042) * V_0 * adaptive_factor

                V_after_boost = V_actual + V_boost
                dilution = V_actual / V_after_boost
                Xv *= dilution
                Xd *= dilution
                L *= dilution
                Titer *= dilution
                G_actual = (
                    G_pre_feed * V_actual + V_boost * G_BOOST_CONC
                ) / V_after_boost
                V = V_after_boost
                G = G_actual

                # Step 3: closed_loop glucose top-up from the C_STOCK stock, sized by
                # mass balance to bring G exactly to G_TARGET:
                #   (G_actual*V + V_gluc*C_STOCK) / (V + V_gluc) = G_TARGET
                if config.mode == "closed_loop" and (
                    G_pre_feed < G_MIN or G_actual < G_MIN
                ):
                    V_gluc = max(
                        0.0, V * (G_TARGET - G_actual) / (C_STOCK - G_TARGET)
                    )
                    if V_gluc > 0.0:
                        V_new = V + V_gluc
                        dilution = V / V_new
                        Xv *= dilution
                        Xd *= dilution
                        L *= dilution
                        Titer *= dilution
                        G = (G_actual * V + V_gluc * C_STOCK) / V_new
                        V = V_new
                        if audit_logger is not None:
                            _audit_event(
                                audit_logger,
                                "glucose_g_L", f"{G_actual:.4f}", f"{G:.4f}",
                                f"URS-07 glucose top-up at culture day {fd:.1f}: "
                                f"G_pre_feed {G_pre_feed:.4f} g/L, V_gluc "
                                f"{V_gluc:.6f} L of {C_STOCK:.0f} g/L stock",
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
    }
