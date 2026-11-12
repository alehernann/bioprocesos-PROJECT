"""ISPE A-Mab multivariate design-space response surfaces and scale-up engineering.

The quadratic response-surface models (RSMs) for the four N-glycan critical quality
attributes (afucosylation max/min, galactosylation max/min) reproduce the A-Mab
design-space case study (CMC Biotech Working Group, *A-Mab: A Case Study in Bioprocess
Development*, v2.1, CASSS/ISPE, Oct. 2009, pp. 90-92 and 100-106). The five process
factors (culture duration, pCO2, osmolality, pH, temperature) are normalized to their
design-space centre so that the model intercepts correspond to the centre-point response.

The scale-up correlation uses the power-law form of A-Mab Eq. 4 (p.101),
kLa = k * (P/V)^a * Vs^b, where k, a and b depend on the vessel configuration. A-Mab
fitted it for the 15,000 L open-pipe sparger (Fig. 3.11, p.102). The coefficient
used here (80.14) was recalibrated in this repository so the law passes through the
A-Mab 15,000 L point (Table 3.22: Vs 0.015 m/s, P/V 26 W/m3, kLa 20 h^-1); it is not
read from Fig. 3.11. A-Mab Table 3.22 reports measured kLa of 8-20 h^-1. Applying the
law at 0.25 L or 2 L is an extrapolation outside the scales A-Mab fitted.
"""


def evaluate_amab_design_space(
    cd_days: float = 17.0,
    co2_mmHg: float = 100.0,
    osm_mOsm: float = 400.0,
    ph_val: float = 6.85,
    temp_C: float = 35.0,
    table_3_8_mode: bool = True,
) -> dict:
    """Evaluate the A-Mab N-glycan design-space response surfaces.

    Parameters are normalized to the design-space centre (A-Mab ISPE 2009,
    pp. 90-92, 100-106). At the centre point all normalized inputs are zero and the
    responses reduce to the model intercepts [14.70, 15.29, 13.15, 11.08].

    The osmolality coefficient on the Osm main effect in Inequality 1 (response z1,
    afucosylation maximum) is source-dependent in the A-Mab case study:

    * ``+1.54`` in the Fig. 3.8 coefficient table (A-Mab 2009, p. 92, for the
      aFuc < 11% specification), and
    * ``+0.51`` in the prose model on p. 90 (for the aFuc < 13% specification).

    ``table_3_8_mode`` (default ``True``) selects the Fig. 3.8 table coefficient
    (+1.54), which is the validated default used throughout this package; the
    existing numeric outputs are unchanged. It is exposed so the p.90 text variant
    (+0.51) can be contrasted without editing the model.

    Returns a dict with the four responses (``z1_afuc_max``, ``z2_afuc_min``,
    ``z3_gal_max``, ``z4_gal_min``), whether the inputs are ``in_bounds`` of the
    validated design space, and whether the design space ``holds`` (all responses
    at or above the 4.60 acceptance limit while in bounds).
    """
    # Osmolality main-effect coefficient in Inequality 1 (z1): Fig. 3.8 table
    # value +1.54 (p.92, aFuc < 11%) vs p.90 text value +0.51 (aFuc < 13%).
    osm_coeff_z1 = 1.54 if table_3_8_mode else 0.51
    CD = (cd_days - 17.0) / 2.0
    CO2 = (co2_mmHg - 100.0) / 60.0
    Osm = (osm_mOsm - 400.0) / 40.0
    pH = (ph_val - 6.85) / 0.25
    T = temp_C - 35.0

    z1 = (
        14.70
        + 0.62 * CD
        + 0.84 * CO2
        + osm_coeff_z1 * Osm
        + 2.83 * pH
        + 1.42 * T
        - 1.27 * CD * CO2
        - 1.82 * CD * Osm
        - 4.36 * CD * pH
        - 2.26 * CD * T
        - 0.31 * CO2 * Osm
        + 3.11 * CO2 * pH
        + 0.04 * CO2 * T
        - 1.44 * Osm * pH
        - 0.81 * Osm * T
        + 3.00 * pH * T
        - 2.09 * (CD ** 2)
        - 0.15 * (CO2 ** 2)
        - 1.66 * (Osm ** 2)
        + 3.26 * (pH ** 2)
        - 2.73 * (T ** 2)
    )

    z2 = (
        15.29
        + 0.35 * CD
        - 1.53 * CO2
        - 0.41 * Osm
        - 0.28 * pH
        - 1.90 * T
        - 0.57 * CD * CO2
        + 2.80 * CD * Osm
        + 0.18 * CD * pH
        + 0.81 * CD * T
        - 1.05 * CO2 * Osm
        - 1.89 * CO2 * pH
        - 0.41 * CO2 * T
        - 0.73 * Osm * pH
        - 0.22 * Osm * T
        - 2.91 * pH * T
        + 0.31 * (CD ** 2)
        - 0.51 * (CO2 ** 2)
        - 0.42 * (Osm ** 2)
        - 5.32 * (pH ** 2)
        + 1.70 * (T ** 2)
    )

    z3 = (
        13.15
        + 2.31 * CD
        + 1.81 * CO2
        + 1.86 * Osm
        + 2.82 * pH
        - 1.63 * T
        - 1.44 * CD * CO2
        - 0.26 * CD * Osm
        - 4.12 * CD * pH
        + 0.76 * CD * T
        - 0.12 * CO2 * Osm
        - 2.80 * CO2 * pH
        + 0.50 * CO2 * T
        - 0.22 * Osm * pH
        - 2.20 * Osm * T
        - 2.27 * pH * T
        - 2.49 * (CD ** 2)
        - 0.43 * (CO2 ** 2)
        - 0.32 * (Osm ** 2)
        - 0.33 * (pH ** 2)
        + 0.06 * (T ** 2)
    )

    z4 = (
        11.08
        - 3.06 * CD
        - 2.87 * CO2
        - 1.61 * Osm
        - 2.27 * pH
        + 1.21 * T
        - 0.34 * CD * CO2
        - 0.63 * CD * Osm
        + 3.65 * CD * pH
        + 1.79 * CD * T
        - 0.19 * CO2 * Osm
        + 2.61 * CO2 * pH
        + 0.11 * CO2 * T
        - 0.13 * Osm * pH
        + 2.35 * Osm * T
        + 3.16 * pH * T
        - 0.23 * (CD ** 2)
        + 0.41 * (CO2 ** 2)
        + 0.33 * (Osm ** 2)
        - 0.20 * (pH ** 2)
        - 0.16 * (T ** 2)
    )

    in_bounds = (
        (15.0 <= cd_days <= 19.0)
        and (40.0 <= co2_mmHg <= 160.0)
        and (360.0 <= osm_mOsm <= 440.0)
        and (6.6 <= ph_val <= 7.1)
        and (34.0 <= temp_C <= 36.0)
    )
    holds = bool(
        in_bounds and z1 >= 4.60 and z2 >= 4.60 and z3 >= 4.60 and z4 >= 4.60
    )

    return {
        "z1_afuc_max": round(z1, 2),
        "z2_afuc_min": round(z2, 2),
        "z3_gal_max": round(z3, 2),
        "z4_gal_min": round(z4, 2),
        "in_bounds": in_bounds,
        "design_space_holds": holds,
    }


# --- Oxygen-transfer constants shared with the bioreactor twin (v1.3.1) ---
# Leading coefficient recalibrated in this repository (SI units, no 1e4 factor) so
# that the A-Mab 15,000 L point (Table 3.22: Vs = 0.015 m/s, P/V = 26.0 W/m3) yields
# kLa ~= 20.0 h^-1. Form: A-Mab Eq. 4 (p.101); k, a, b are configuration-dependent.
KLA_COEFF = 80.14
KLA_EXP_VS = 0.481          # exponent on Vs (m/s), A-Mab Eq. 4 form
KLA_EXP_PV = 0.194          # exponent on P/V (W/m3), A-Mab Eq. 4 form
C_STAR_O2_MMOL_L = 0.210    # mmol/L O2 at air saturation; modeling assumption (not calibrated)
Q_O2_MMOL_CELL_H = 1.0e-10  # mmol O2/(cell*h) specific oxygen uptake rate
AMAB_REF_VS_M_S = 0.015     # m/s, A-Mab 15,000 L reference superficial gas velocity


def compute_kla_h_inv(superficial_gas_vel_m_s: float, power_per_vol_W_m3: float) -> float:
    """Unrounded kLa (1/h) = KLA_COEFF * Vs^0.481 * (P/V)^0.194.

    Power-law form of A-Mab Eq. 4 (p.101), anchored at the A-Mab 15,000 L point
    (Table 3.22). Use at 0.25 L or 2 L is an extrapolation.
    """
    return (
        KLA_COEFF
        * (superficial_gas_vel_m_s ** KLA_EXP_VS)
        * (power_per_vol_W_m3 ** KLA_EXP_PV)
    )


def compute_scale_up_engineering(
    superficial_gas_vel_m_s: float,
    power_per_vol_W_m3: float,
    vcc_1e6_cells_mL: float = 15.0,
    qo2_mmol_cell_h: float = Q_O2_MMOL_CELL_H,
    do_percent: float = 30.0,
) -> dict:
    """Compute oxygen-transfer scale-up engineering parameters.

    The kLa correlation uses the power-law form of A-Mab Eq. 4 (p.101), anchored at
    the A-Mab 15,000 L point (Table 3.22). The
    ``qo2_mmol_cell_h`` argument specifies the per-cell specific oxygen uptake
    rate (mmol/(cell*h)) used to compute
    ``our_max_mmol_L_h = vcc_1e6_cells_mL * 1e9 * qo2_mmol_cell_h`` (yielding
    1.50 mmol/(L*h) at the default 15e6 cells/mL and 1.0e-10 mmol/(cell*h)).

    SI-UNIT CORRECTION
    ------------------
    ``superficial_gas_vel_m_s`` is consumed directly in SI units (m/s); the
    previous implementation multiplied it by an implicit 1e4 factor (an unphysical
    cm/s-vs-m/s unit error) baked into the leading coefficient. That factor is
    removed. The power-law form ``kLa = C * Vs^0.481 * (P/V)^0.194`` (A-Mab Eq. 4,
    p.101; k, a, b configuration-dependent) is retained, with the leading
    coefficient C recalibrated in this repository so that the A-Mab 15,000 L point
    (Table 3.22: Vs = 0.015 m/s, P/V = 26.0 W/m3) returns ~20.0 h^-1. The value 80.14
    is not read from Fig. 3.11.

    TEST ENVELOPE (modeling assumption)
    -----------------------------------
    The OQ tests evaluate the law at the corners Vs = 0.005-0.017 m/s x
    P/V = 19-30 W/m3, which gives kLa 11.10-21.84 h^-1. The P/V values 19 and
    30 W/m3 come from Bionova (Ref. 2, pp.3-4); the Vs band is a modeling
    assumption. A-Mab Table 3.22 reports measured kLa of 8-20 h^-1, so the upper
    corner (21.84 h^-1) lies above the measured range. Using the law at 0.25 L or
    2 L is an extrapolation.

    Returns ``kla_h_inv`` (volumetric mass-transfer coefficient, 1/h),
    ``our_max_mmol_L_h`` (maximum oxygen uptake rate, mmol/(L*h)),
    ``otr_mmol_L_h`` (oxygen-transfer rate) and ``oxygen_sufficient`` (OTR >= OUR).

    DISSOLVED-OXYGEN DRIVING FORCE (v1.3.0)
    ---------------------------------------
    ``do_percent`` is the DO set-point in % of air saturation (default 30.0). The
    driving force is explicit: C* = 0.210 mmol/L (air saturation; modeling
    assumption, not calibrated) and
    driving_force = C* * max(0, 1 - do_percent/100), so OTR = kLa * driving_force.
    At 30 % DO this equals the former fixed term 0.21 - 0.063 = 0.147 mmol/L.
    """
    kla_h_inv = compute_kla_h_inv(superficial_gas_vel_m_s, power_per_vol_W_m3)
    our_max_mmol_L_h = vcc_1e6_cells_mL * 1.0e9 * qo2_mmol_cell_h

    # OTR = kLa * (C* - C_L) with C_L = C* * DO/100 (standard two-film driving force).
    driving_force_mmol_L = C_STAR_O2_MMOL_L * max(0.0, 1.0 - (do_percent / 100.0))
    otr_mmol_L_h = kla_h_inv * driving_force_mmol_L
    oxygen_sufficient = bool(otr_mmol_L_h >= our_max_mmol_L_h)

    return {
        "kla_h_inv": round(kla_h_inv, 2),
        "our_max_mmol_L_h": round(our_max_mmol_L_h, 2),
        "otr_mmol_L_h": round(otr_mmol_L_h, 2),
        "oxygen_sufficient": oxygen_sufficient,
    }
