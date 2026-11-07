"""CHO-K1 fed-batch mechanistic digital twin plus control and safety logic.

This module provides:

1. A split-range pH controller (CO2 valve vs. base pump) around a deadband.
2. A biphasic temperature-shift setpoint schedule.
3. GxP safety interlocks: hydrodynamic-shear alarm (A-Mab / Ma et al. 2002 shear
   context), CIP/SIP interlocks and sterilization F0 integration. The 1.52 m/s
   (5 ft/s) CIP pipe velocity criterion follows ASME BPE-2014.
4. A mechanistic fed-batch simulation of CHO-K1 culture (viable/dead cells,
   glucose, lactate, titer) with static and closed-loop feeding strategies. The
   closed-loop adaptive feed and +43% titer gain reference follows the Ark Biotech
   & Culture Biosciences technical bulletin (Quint et al., 2026); the micro-scale
   basis follows the Stratyx(TM) / Bionova Scientific 2026 whitepaper.

References
----------
- CMC Biotech Working Group, *A-Mab: A Case Study in Bioprocess Development*, v2.1, CASSS/ISPE, Oct. 2009.
- Y. Quint et al., "Real-Time Closed-Loop Optimization Delivers 43% Titer Improvement...", Ark Biotech & Culture Biosciences Technical Bulletin, 2026.
- ASME BPE-2014, *Bioprocessing Equipment: An International Standard*.
"""

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
) -> dict:
    """Evaluate the GxP safety interlocks for the bioreactor skid.

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

    return {
        "high_shear_alarm": high_shear_alarm,
        "cip_interlock_blocked": cip_interlock_blocked,
        "cip_velocity_compliant": cip_velocity_compliant,
        "f0_minutes": f0_minutes,
        "sip_sterile_compliant": sip_sterile_compliant,
    }


def simulate_cho_fed_batch(config: ProcessDescription) -> dict:
    """Simulate a CHO-K1 fed-batch culture under static or closed-loop feeding.

    State vector: viable cell density Xv (1e6 cells/mL), dead cell density Xd,
    glucose G (g/L), lactate L (g/L), and titer (g/L). Integrated with an explicit
    Euler scheme at dt = 0.1 d (141 points over 14 d).

    Kinetics (biphasic, temperature-shift at ``temp_shift_day``):
        - growth phase (36.5 C): mu_max = 0.58 1/d, qp_base = 0.012 g/(1e9 cell*d);
        - production phase (34.0 C): mu_max = 0.12 1/d, qp_base = 0.021.
        mu = mu_max * (G/(G+0.5)) * (2.5/(L+2.5)) * (1 - Xv/26.0)
        kd = 0.015 + 0.02*max(0, L-1.2) + (0.04 if G < 0.5 else 0.0)
        dXv/dt = (mu - kd)*Xv ; dXd/dt = kd*Xv
        dTiter/dt = qp * fPV * Xv * TITER_UNIT_CONV

    Power/volume factor ``fPV``: 1.08 for P/V >= 30 W/m^3, 1.00 for P/V <= 19,
    linear interpolation between 19 and 30; under high shear (P/V > 47.6 and
    sparge > 0.15) fPV = 0.63 (qp penalised -37%) and viability is penalised via an
    extra death term.

    Substrate / lactate calibration yields (documented; calibrated toward the
    closed-loop vs. static reference of ~2.71 vs ~1.896 g/L, i.e. ~+43%, per the Ark
    Biotech / Culture Biosciences bulletin, Quint et al. 2026). ONLY the substrate
    and lactate yields below were tuned; the kinetic equations (mu, kd, qp, the
    qp*1.43 window, feeding rules) are left exactly as specified.
        - Y_X_G    = 3.2 (1e6 cells/mL) biomass yield per g/L glucose consumed;
        - M_G      = 0.008 g/L per (1e6 cells/mL * d) maintenance glucose draw;
        - Y_L_BASE = 0.08 g lactate per g glucose consumed (baseline glycolysis);
        - Y_L_OVERFLOW = 0.40 extra g lactate per g glucose when glucose is above the
          overflow threshold (Warburg-type overflow metabolism of CHO cells); this
          glucose-dependent overflow is the mechanism by which controlled closed-loop
          feeding (which keeps glucose from overshooting) outperforms static boluses;
        - G_OVERFLOW_THRESHOLD = 5.0 g/L glucose above which overflow lactate applies;
        - K_L_UP   = 0.02 1/d lactate re-uptake in production phase when glucose is low.
        - TITER_UNIT_CONV = 1.0: qp is given in g/(1e9 cell*d) and Xv in 1e6 cells/mL.
          Per-cell qp (qp/1e9 g/cell/d) times Xv expressed in cells/L
          (Xv * 1e6 cells/mL * 1e3 mL/L = Xv * 1e9 cells/L) gives qp * Xv g/(L*d);
          the 1e-9 and 1e9 factors cancel exactly, so the conversion factor is 1.0.

    Feeding on crossing days 2, 4, 6, 8, 10, 12:
        - "static": +2.2 g/L glucose-equivalent bolus each feed day.
        - "closed_loop": a +80% feed multiplier applies qp*1.43 between days 6 and 10
          (Ark bulletin), and an adaptive rule tops glucose back up to
          ``glucose_refill_target_g_L`` whenever G < ``glucose_min_threshold_g_L``.

    OBTAINED CALIBRATION NOTE (nominal defaults, 14 d): with the yields above the
    model gives static final_titer_g_L ~= 1.85 g/L and closed_loop ~= 2.29 g/L,
    a closed-loop advantage of ~+24%. The static value matches the ~1.896 g/L
    reference closely. The full ~+43% gain (closed_loop ~2.71 g/L) is NOT reachable
    while keeping static ~1.9 g/L under the fixed kinetic equations given (the
    qp*1.43 boost spans only days 6-10 and the specified mu/kd limit biomass), so
    per the instruction it was NOT forced: only the substrate/lactate yields were
    calibrated. The closed-loop strategy still clearly and consistently outperforms
    static, which is the qualitative result the Ark bulletin describes.

    Returns the time series (``time_days``, ``vcd``, ``viability_pct``,
    ``glucose_g_L``, ``lactate_g_L``, ``titer_g_L``, ``temp_C``) and the summary
    metrics ``final_titer_g_L``, ``final_viability_pct`` and ``peak_vcd``.
    """
    # --- Documented substrate / lactate calibration yields (ONLY these were tuned) ---
    Y_X_G = 3.2             # (1e6 cells/mL) biomass yield per g/L glucose consumed
    M_G = 0.008             # g/L per (1e6 cells/mL * d) maintenance glucose draw
    Y_L_BASE = 0.08         # g lactate per g glucose (baseline glycolysis)
    Y_L_OVERFLOW = 0.40     # extra g lactate per g glucose above overflow threshold
    G_OVERFLOW_THRESHOLD = 5.0  # g/L glucose above which overflow lactate applies
    K_L_UP = 0.02           # 1/d lactate re-uptake (production phase, low glucose)
    TITER_UNIT_CONV = 1.0   # g/(1e9 cell*d) * (1e6 cells/mL) -> g/(L*d); factors cancel

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

    peak_vcd = Xv

    for i in range(n_steps):
        t = time_days[i]

        temp_C = get_temperature_setpoint(
            t,
            temp_initial_C=config.temp_initial_C,
            temp_shift_C=config.temp_shift_C,
            shift_day=config.temp_shift_day,
        )

        if t < config.temp_shift_day:
            mu_max = 0.58
            qp_base = 0.012
        else:
            mu_max = 0.12
            qp_base = 0.021

        # Closed-loop adaptive-feed productivity boost between days 6 and 10.
        qp = qp_base
        if config.mode == "closed_loop" and 6.0 <= t <= 10.0:
            qp = qp_base * 1.43

        # Record current state
        total_cells = Xv + Xd
        viability_pct = 100.0 * Xv / total_cells if total_cells > 0 else 0.0
        vcd_series.append(Xv)
        viability_series.append(viability_pct)
        glucose_series.append(G)
        lactate_series.append(L)
        titer_series.append(Titer)
        temp_series.append(temp_C)
        if Xv > peak_vcd:
            peak_vcd = Xv

        if i == n_steps - 1:
            break

        # Kinetics
        mu = mu_max * (G / (G + 0.5)) * (2.5 / (L + 2.5)) * (1 - Xv / 26.0)
        kd = 0.015 + 0.02 * max(0.0, L - 1.2) + (0.04 if G < 0.5 else 0.0)
        if high_shear:
            kd += 0.03  # additional viability penalty under high hydrodynamic shear

        dXv = (mu - kd) * Xv
        dXd = kd * Xv

        # Substrate consumption: growth-associated + maintenance
        glucose_uptake = (mu * Xv) / Y_X_G + M_G * Xv
        glucose_uptake = min(glucose_uptake, G / dt) if dt > 0 else glucose_uptake
        dG = -glucose_uptake

        # Lactate: baseline glycolysis plus Warburg-type overflow when glucose is
        # high, minus re-uptake when glucose is scarce in the production phase.
        y_lactate = Y_L_BASE + (Y_L_OVERFLOW if G > G_OVERFLOW_THRESHOLD else 0.0)
        lactate_prod = y_lactate * glucose_uptake
        lactate_uptake = (
            K_L_UP * L * Xv if (t >= config.temp_shift_day and G < 1.5) else 0.0
        )
        dL = lactate_prod - lactate_uptake

        dTiter = qp * fPV * Xv * TITER_UNIT_CONV

        # Euler update
        Xv = max(0.0, Xv + dXv * dt)
        Xd = max(0.0, Xd + dXd * dt)
        G = max(0.0, G + dG * dt)
        L = max(0.0, L + dL * dt)
        Titer = max(0.0, Titer + dTiter * dt)

        # Feeding at the crossing of each feed day
        t_next = time_days[i + 1]
        for fd in feed_days:
            if (not fed_done[fd]) and (t < fd <= t_next + 1e-9):
                if config.mode == "static":
                    G += 2.2
                else:  # closed_loop adaptive glucose top-up
                    if G < config.glucose_min_threshold_g_L:
                        delta_G = config.glucose_refill_target_g_L - G
                        G += delta_G
                fed_done[fd] = True

    final_titer = titer_series[-1]
    final_viability = viability_series[-1]

    return {
        "time_days": time_days,
        "vcd": vcd_series,
        "viability_pct": viability_series,
        "glucose_g_L": glucose_series,
        "lactate_g_L": lactate_series,
        "titer_g_L": titer_series,
        "temp_C": temp_series,
        "final_titer_g_L": round(float(final_titer), 4),
        "final_viability_pct": round(float(final_viability), 2),
        "peak_vcd": round(float(peak_vcd), 4),
    }
