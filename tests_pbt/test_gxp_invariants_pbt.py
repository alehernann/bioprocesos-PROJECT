"""Property-based tests (Hypothesis) of the v1.4.0 physical and regulatory invariants.

Kept OUTSIDE tests/ on purpose, like tests_app/: tests/conftest.py writes the FDA CSA OQ log
(docs/04) for the qualified OQ tests in tests/, and this suite must not change that record.
Every property runs with ``@settings(max_examples=60, deadline=None, derandomize=True)``:
the examples are deterministic in CI and no failing example is saved to an example database.
Hypothesis still caches Unicode tables and literal constants in .hypothesis/ (git-ignored).

Seven properties, each traced to the EARS requirements of docs/01 and to the NFRs. Each one
kills at least one in-memory mutant of the code under test (scripts/mutation_check_pbt.py).
Tolerances were fixed before the suite was run and are justified where they are used (output
rounding of the function under test, a priori floating-point error bounds); none was widened
after a failure. The code under test is called through its module (``twin.<function>``) so the
mutation harness can replace it in memory without touching src/.

Edge cases of v1.4.0 found while setting up these properties (reported, not hidden):
- VTB: a constant trace is not preserved bit for bit; the convex update drifts by 1-7 ULP
  (e.g. 59.9 -> 59.900000000000006 with "20 mL (Glycol Ref)"). PBT-05 bounds the drift a priori.
- TOST + Levene: with n = 2 per group Levene is 0/0 (NaN p-value) and equivalence is never
  declared; with identical groups, equivalence needs margin > t(1-alpha, df) * se. PBT-07 uses
  n >= 3 and the TOST/confidence-interval duality.
- Part 11: the SHA-256 payload hashes str(value), so a type-only change with the same text
  (1 -> "1") is not detected. PBT-06 tampers with the recorded text.

Run with:  python -m pytest -v tests_pbt/
"""

import math

import numpy as np
import pydantic
import pytest
from hypothesis import event, given, settings, strategies as st
from scipy import stats

import src.amab_design_space as amab
import src.audit_trail_part11 as audit
import src.bioreactor_twin as twin
import src.spc_six_sigma as spc
import src.thermal_vtb_mkt as thermal
from src.models import ProcessDescription

# Like tests_app/: a DeprecationWarning is an error even without -W on the command line.
pytestmark = pytest.mark.filterwarnings("error::DeprecationWarning")

UNIT_ROUNDOFF = 2.0 ** -53  # IEEE-754 binary64 unit roundoff u


# ---------------------------------------------------------------------------------------------
# PBT-01: fed-batch positivity, vessel capacity and bolus mass conservation
# ---------------------------------------------------------------------------------------------
SPECIES_SERIES = {"Xv": "vcd", "Xd": "dead_cell_density", "G": "glucose_g_L", "L": "lactate_g_L",
                  "NH3": "nh3_mmol_L", "Titer": "titer_g_L"}
OUTPUT_SERIES = tuple(SPECIES_SERIES.values()) + ("volume_L", "viability_pct", "do_real_pct",
                                                  "f_do_metabolic", "required_y_o2")


@st.composite
def process_parameters(draw):
    """Valid ProcessDescription fields over the whole operating domain (slider bounds)."""
    duration = draw(st.integers(min_value=5, max_value=21))
    g_target = draw(st.floats(min_value=2.0, max_value=15.0))
    g_min = draw(st.floats(min_value=0.5, max_value=min(10.0, g_target), exclude_max=g_target <= 10.0))
    return dict(
        vessel_volume_L=draw(st.floats(min_value=0.25, max_value=35000.0)),
        power_density_W_m3=draw(st.floats(min_value=2.0, max_value=100.0)),
        sparge_vvm=draw(st.floats(min_value=0.0, max_value=1.0)),
        temp_initial_C=draw(st.floats(min_value=30.0, max_value=40.0)),
        temp_shift_C=draw(st.floats(min_value=30.0, max_value=40.0)),
        temp_shift_day=draw(st.floats(min_value=1.0, max_value=min(14.0, float(duration)))),
        do_setpoint_pct=draw(st.floats(min_value=5.0, max_value=95.0)),
        initial_fill_fraction=draw(st.floats(min_value=0.20, max_value=0.95)),
        mode=draw(st.sampled_from(("static", "closed_loop"))),
        o2_enrichment_enabled=draw(st.booleans()),
        glucose_feedback_in_static=draw(st.booleans()),
        max_o2_mole_fraction=draw(st.floats(min_value=0.2095, max_value=1.0)),
        glucose_min_threshold_g_L=g_min,
        glucose_refill_target_g_L=g_target,
        duration_days=duration,
    )


def _mass_conserved(after: float, before: float) -> bool:
    """Mass balance tolerance of the task specification: 1e-8 relative, 1e-8 absolute floor."""
    return abs(after - before) <= 1e-8 * max(1.0, abs(before))


@settings(max_examples=60, deadline=None, derandomize=True)
@given(params=process_parameters(), shift_excess=st.floats(min_value=1e-6, max_value=7.0))
def test_pbt_01_fedbatch_positivity_capacity_and_mass_conservation(params, shift_excess):
    """URS-07, NFR-01, NFR-04 (and the NFR-06 output bounds) for any valid run of the twin.

    NFR-04: a shift later than the run (or beyond 14 d) raises ValidationError, never a run.
    NFR-01: the same configuration gives bit-identical outputs twice. NFR-06: no NaN/Inf, the
    six concentrations >= 0, viability in [0, 100] %, 0 < V(t) <= vessel_volume_L + 1e-12 L.
    URS-07: no bolus on the harvest day, V_new = V_old + v_basal + v_gluc, and every bolus
    conserves the mass of the six species; only glucose is added (v_basal * G_BOOST_CONC +
    v_gluc * 500 g/L, recomputed here from the event volumes), checked on the event record
    and on the reported series at the post-bolus grid point.
    """
    bad_shift = min(14.0, float(params["duration_days"])) + shift_excess
    with pytest.raises(pydantic.ValidationError):
        ProcessDescription(**{**params, "temp_shift_day": bad_shift})

    config = ProcessDescription(**params)
    res = twin.simulate_cho_fed_batch(config)
    again = twin.simulate_cho_fed_batch(config)
    vessel = config.vessel_volume_L
    for key in OUTPUT_SERIES:
        assert res[key] == again[key], f"NFR-01: {key} not reproducible"
        assert np.all(np.isfinite(np.asarray(res[key], dtype=float))), key
    for key in SPECIES_SERIES.values():
        assert min(res[key]) >= 0.0, key
    assert 0.0 <= min(res["viability_pct"]) and max(res["viability_pct"]) <= 100.0
    assert min(res["volume_L"]) > 0.0 and max(res["volume_L"]) <= vessel + 1e-12

    g_boost = twin.CALIBRATED_KINETICS.g_boost_conc
    event(f"bolus clipped: {res['bolus_clipped_alarm']}")
    event(f"glucose top-up: {any(ev['v_gluc_L'] > 0.0 for ev in res['feed_events'])}")
    for ev in res["feed_events"]:
        day, k = ev["day"], ev["step_index_after"]
        v_old, v_new, v_basal, v_gluc = ev["V_old_L"], ev["V_new_L"], ev["v_basal_L"], ev["v_gluc_L"]
        assert day < config.duration_days, "URS-07: no bolus on the harvest day"
        assert 0.0 <= ev["scale_factor"] <= 1.0 and v_basal >= 0.0 and v_gluc >= 0.0
        assert abs(v_new - (v_old + v_basal + v_gluc)) <= 1e-12 * max(1.0, v_new), day
        assert v_new <= vessel + 1e-12 and res["volume_L"][k] == v_new, day
        added_glucose = v_basal * g_boost + v_gluc * twin.C_STOCK_GLUCOSE_G_L
        assert _mass_conserved(ev["glucose_added_g"], added_glucose), day
        for species, series in SPECIES_SERIES.items():
            assert ev["pre"][species] >= 0.0 and ev["post"][species] >= 0.0, (day, species)
            before = ev["pre"][species] * v_old + (added_glucose if species == "G" else 0.0)
            assert _mass_conserved(ev["post"][species] * v_new, before), (day, species)
            assert _mass_conserved(res[series][k] * v_new, before), (day, species)


# ---------------------------------------------------------------------------------------------
# PBT-02: pH split-range controller
# ---------------------------------------------------------------------------------------------
@settings(max_examples=60, deadline=None, derandomize=True)
@given(
    ph_pair=st.tuples(st.floats(min_value=0.0, max_value=14.0), st.floats(min_value=0.0, max_value=14.0)),
    setpoint=st.floats(min_value=6.0, max_value=8.0),
    deadband=st.floats(min_value=0.01, max_value=1.0),
    kp=st.floats(min_value=1.0, max_value=500.0),
)
def test_pbt_02_ph_split_range_universal_exclusivity_and_bounds(ph_pair, setpoint, deadband, kp):
    """URS-03, URS-04, URS-05 for any pH 0-14, set-point 6-8, dead-band 0.01-1 and gain 1-500.

    Never both actuators > 0 (split-range exclusivity); outputs in [0, 100] %; both exactly 0.0
    inside [setpoint - deadband, setpoint + deadband]; CO2 only above and base only below the
    band. Each branch engages once its proportional demand kp * distance reaches 0.01 % (the
    smallest value that survives the function's 2-decimal rounding), so a disabled actuator
    fails. CO2 is non-decreasing and base non-increasing in pH (monotone over the whole range).
    """
    low, high = sorted(ph_pair)
    upper, lower = setpoint + deadband, setpoint - deadband
    outputs = []
    for ph in (low, high):
        out = twin.compute_split_range_ph_actuators(ph, setpoint=setpoint, deadband=deadband, kp=kp)
        co2, base = out["co2_valve_pct"], out["base_pump_pct"]
        event("pH above band" if ph > upper else "pH below band" if ph < lower else "pH in band")
        assert not (co2 > 0.0 and base > 0.0), f"both actuators active at pH {ph}"
        assert 0.0 <= co2 <= 100.0 and 0.0 <= base <= 100.0
        if lower <= ph <= upper:
            assert co2 == 0.0 and base == 0.0, f"actuation inside the dead-band at pH {ph}"
        if co2 > 0.0:
            assert ph > upper
        if base > 0.0:
            assert ph < lower
        if kp * (ph - upper) >= 0.01:
            assert co2 > 0.0, f"URS-04: CO2 branch idle at pH {ph}"
        if kp * (lower - ph) >= 0.01:
            assert base > 0.0, f"URS-05: base branch idle at pH {ph}"
        outputs.append((co2, base))
    (co2_low, base_low), (co2_high, base_high) = outputs
    assert co2_low <= co2_high, "CO2 opening must not decrease when pH rises"
    assert base_low >= base_high, "base pumping must not increase when pH rises"


# ---------------------------------------------------------------------------------------------
# PBT-03: oxygen transfer (scale-up calculator)
# ---------------------------------------------------------------------------------------------
def _unrounded_otr(kla: float, do_pct: float, y_o2: float) -> float:
    """Documented law (compute_scale_up_engineering docstring), same operation order:
    OTR = kLa * C*_air * max(0, y_O2 / 0.2095 - DO / 100)."""
    return kla * (amab.C_STAR_O2_MMOL_L * max(0.0, y_o2 / amab.Y_O2_AIR - do_pct / 100.0))


@settings(max_examples=60, deadline=None, derandomize=True)
@given(
    vs=st.floats(min_value=0.001, max_value=0.1),
    pv=st.floats(min_value=2.0, max_value=100.0),
    vcc=st.floats(min_value=0.1, max_value=60.0),
    measured_kla=st.one_of(st.none(), st.sampled_from(sorted(set(amab.AMAB_MEASURED_KLA_H_INV.values())))),
    do_pair=st.lists(st.floats(min_value=0.0, max_value=100.0), min_size=2, max_size=2, unique=True),
    y_pair=st.lists(st.floats(min_value=0.0, max_value=1.0, exclude_min=True), min_size=2, max_size=2, unique=True),
)
def test_pbt_03_oxygen_scaleup_monotonicity_and_enrichment(vs, pv, vcc, measured_kla, do_pair, y_pair):
    """URS-06 for any Vs, P/V, VCC, kLa source, DO_1 < DO_2 and y_O2,1 < y_O2,2.

    OTR >= 0; OTR(DO_2) <= OTR(DO_1) (a higher DO set-point lowers the driving force);
    OTR(y_2) >= OTR(y_1) (O2 enrichment never lowers OTR) and C*_gas grows with y_O2; OUR does
    not depend on DO or y_O2. Strictness: when the unrounded change is >= 0.01 mmol/L/h the
    2-decimal outputs must move (an enrichment or DO term that is ignored fails).
    oxygen_sufficient is compared with OTR >= OUR on unrounded values from the documented law.
    """
    do_1, do_2 = sorted(do_pair)
    y_1, y_2 = sorted(y_pair)
    kla = amab.compute_kla_h_inv(vs, pv) if measured_kla is None else float(measured_kla)
    our = vcc * 1.0e9 * amab.Q_O2_MMOL_CELL_H
    res, otr = {}, {}
    for do in (do_1, do_2):
        for y in (y_1, y_2):
            res[do, y] = amab.compute_scale_up_engineering(
                vs, pv, vcc_1e6_cells_mL=vcc, do_percent=do, measured_kla_h_inv=measured_kla, o2_mole_fraction=y)
            otr[do, y] = _unrounded_otr(kla, do, y)
            assert res[do, y]["otr_mmol_L_h"] >= 0.0
            assert res[do, y]["oxygen_sufficient"] is (otr[do, y] >= our), (do, y)
            event(f"oxygen_sufficient: {res[do, y]['oxygen_sufficient']}")
            assert res[do, y]["our_max_mmol_L_h"] == res[do_1, y_1]["our_max_mmol_L_h"]
    for y in (y_1, y_2):
        assert res[do_2, y]["otr_mmol_L_h"] <= res[do_1, y]["otr_mmol_L_h"], ("DO", y)
        if otr[do_1, y] - otr[do_2, y] >= 0.01:
            assert res[do_2, y]["otr_mmol_L_h"] < res[do_1, y]["otr_mmol_L_h"], ("DO strict", y)
    for do in (do_1, do_2):
        assert res[do, y_2]["otr_mmol_L_h"] >= res[do, y_1]["otr_mmol_L_h"], ("y_O2", do)
        assert res[do, y_2]["c_star_gas_mmol_L"] >= res[do, y_1]["c_star_gas_mmol_L"], ("C*", do)
        if otr[do, y_2] - otr[do, y_1] >= 0.01:
            assert res[do, y_2]["otr_mmol_L_h"] > res[do, y_1]["otr_mmol_L_h"], ("y_O2 strict", do)


# ---------------------------------------------------------------------------------------------
# PBT-04: A-Mab design-space gate
# ---------------------------------------------------------------------------------------------
# Validated A-Mab ranges of the five factors (docs/01 URS-13; inclusive limits).
AMAB_BOX = {"cd_days": (15.0, 19.0), "co2_mmHg": (40.0, 160.0), "osm_mOsm": (360.0, 440.0),
            "ph_val": (6.6, 7.1), "temp_C": (34.0, 36.0)}
AMAB_ACCEPTANCE = 4.60


@st.composite
def amab_factor_vectors(draw):
    """(factors, expected_in_bounds): half all-inside, half with a random inside/outside mask."""
    mask = [True] * 5 if draw(st.booleans()) else draw(st.lists(st.booleans(), min_size=5, max_size=5))
    factors = {}
    for inside, (name, (lo, hi)) in zip(mask, AMAB_BOX.items()):
        span = hi - lo
        outside = st.one_of(st.floats(min_value=lo - span, max_value=lo, exclude_max=True),
                            st.floats(min_value=hi, max_value=hi + span, exclude_min=True))
        factors[name] = draw(st.floats(min_value=lo, max_value=hi) if inside else outside)
    return factors, all(mask)


@settings(max_examples=60, deadline=None, derandomize=True)
@given(case=amab_factor_vectors(), table_3_8_mode=st.booleans())
def test_pbt_04_amab_design_space_bounds_gate(case, table_3_8_mode):
    """URS-13 for any five-factor vector inside or outside the A-Mab box, both osmolality variants.

    in_bounds equals the box membership computed here. design_space_holds is never True outside
    the box. The function returns z1..z4 rounded to 2 decimals but decides on unrounded values,
    so with z_min the smallest rounded response: holds implies in_bounds and z_min >= 4.60;
    in_bounds and z_min >= 4.61 implies holds; z_min <= 4.59 implies not holds (z_min == 4.60 can
    go either way, because the unrounded value lies in [4.595, 4.605)).
    """
    factors, expected_in_bounds = case
    res = amab.evaluate_amab_design_space(**factors, table_3_8_mode=table_3_8_mode)
    z_min = min(res["z1_afuc_max"], res["z2_afuc_min"], res["z3_gal_max"], res["z4_gal_min"])
    assert res["in_bounds"] is expected_in_bounds, factors
    event(f"in_bounds={res['in_bounds']}, holds={res['design_space_holds']}")
    if not res["in_bounds"]:
        assert res["design_space_holds"] is False, ("held outside the A-Mab box", factors)
    if res["design_space_holds"]:
        assert res["in_bounds"] and z_min >= AMAB_ACCEPTANCE, factors
    if res["in_bounds"] and z_min >= 4.61:
        assert res["design_space_holds"] is True, factors
    if z_min <= 4.59:
        assert res["design_space_holds"] is False, factors


# ---------------------------------------------------------------------------------------------
# PBT-05: MKT (Arrhenius / Jensen), VTB contraction and Nyquist folding
# ---------------------------------------------------------------------------------------------
TEMPERATURE_C = st.floats(min_value=-20.0, max_value=60.0)
VTB_KEYS = sorted(thermal.VTB_CALIBRATION_TABLE) + sorted(thermal.VTB_VOLUME_KEY_ALIASES)


@st.composite
def nonconstant_traces(draw):
    """Temperature traces of 5-120 samples in [-20, 60] C with at least two distinct values.

    A head of 4-119 samples plus one sample offset from head[0] by 1e-6..80 C, reflected (and
    clipped at -20 C) when it leaves the range, then shuffled; no example is rejected. The extra
    sample never equals head[0]: reflection only happens when head[0] > -20 C.
    """
    head = draw(st.lists(TEMPERATURE_C, min_size=4, max_size=119))
    offset = draw(st.floats(min_value=1e-6, max_value=80.0))
    other = head[0] + offset if head[0] + offset <= 60.0 else max(-20.0, head[0] - offset)
    trace = head + [other]
    assert max(trace) > min(trace)
    return [trace[i] for i in draw(st.permutations(range(len(trace))))]


def _vtb_roundoff_bound(trace) -> float:
    """A priori bound on the rounding error of the VTB recursion after len(trace) steps.

    Each step v_k = fl(fl(alpha * x_k) + fl(fl(1 - alpha) * v_{k-1})) adds at most 3u|max| of
    rounding (u = 2**-53; the factor 1 - alpha < 1 never amplifies earlier errors), so after n
    steps the error is below 3 n u max|x|; 4 n u max|x| keeps a margin. Physical size: at most
    3.2e-12 C (120 samples at 60 C). Derived from the recursion, not fitted to observed drifts.
    """
    return 4.0 * len(trace) * UNIT_ROUNDOFF * max(abs(t) for t in trace)


@settings(max_examples=60, deadline=None, derandomize=True)
@given(
    trace=nonconstant_traces(),
    constant=TEMPERATURE_C,
    volume_key=st.sampled_from(VTB_KEYS),
    sampling_interval_min=st.one_of(st.none(), st.floats(min_value=0.1, max_value=60.0)),
    target_interval_min=st.floats(min_value=1.0, max_value=120.0),
)
def test_pbt_05_mkt_arrhenius_jensen_and_vtb_contraction(trace, constant, volume_key,
                                                         sampling_interval_min, target_interval_min):
    """URS-14 and NFR-03 for any non-constant trace of 5-120 samples in [-20, 60] C.

    MKT: exp(-dH/(R T)) is convex for T < dH/(2R) = 5000 K, so by Jensen's inequality
    min(T) <= mean(T) <= MKT <= max(T); tolerance 1e-3 C (the task specification; MKT is
    rounded to 4 decimals, 5e-5 C). VTB: the first-order filter is a convex combination, so every
    output lies in [min(air), max(air)], and a constant trace stays constant. Both hold up to the
    a priori rounding bound of the recursion (_vtb_roundoff_bound): bit-exact preservation does
    not hold in v1.4.0 (1-7 ULP drift, reported). NFR-03: the folded alias frequency lies in
    [0, f_Nyquist] of the target interval, is 0.0 without aliasing, and the aliasing flag agrees
    with f_Nyquist <= f_dominant (2-decimal outputs, 0.01 cph tolerance).
    """
    lo, hi = min(trace), max(trace)
    mean = sum(trace) / len(trace)
    mkt = thermal.calculate_mkt_celsius(trace)
    assert lo - 1e-3 <= mean <= mkt + 1e-3, (lo, mean, mkt)
    assert mkt <= hi + 1e-3, (mkt, hi)

    vtb = thermal.apply_vtb_filter(trace, volume_key=volume_key, sampling_interval_min=sampling_interval_min)
    tol = _vtb_roundoff_bound(trace)
    assert len(vtb) == len(trace) and vtb[0] == trace[0]
    assert lo - tol <= min(vtb) and max(vtb) <= hi + tol, (lo, min(vtb), max(vtb), hi, tol)
    flat = [constant] * len(trace)
    flat_out = thermal.apply_vtb_filter(flat, volume_key=volume_key, sampling_interval_min=sampling_interval_min)
    flat_tol = _vtb_roundoff_bound(flat)
    assert all(abs(v - constant) <= flat_tol for v in flat_out), (constant, flat_out[:5])

    fft = thermal.analyze_fft_nyquist(trace, target_sampling_interval_min=target_interval_min)
    nyquist, dominant, folded = fft["target_nyquist_cph"], fft["true_dominant_freq_cph"], fft["folded_alias_freq_cph"]
    assert 0.0 <= dominant <= 6.0 + 0.01, dominant  # base 5-min record: f_Nyquist,base = 6 cph
    assert 0.0 <= folded <= nyquist + 0.01, (folded, nyquist)
    event(f"aliasing_risk: {fft['aliasing_risk']}")
    if fft["aliasing_risk"]:
        assert nyquist <= dominant + 0.01, (nyquist, dominant)
    else:
        assert folded == 0.0 and nyquist >= dominant - 0.01, (folded, nyquist, dominant)


# ---------------------------------------------------------------------------------------------
# PBT-06: 21 CFR Part 11 hash chain and EU GMP Annex 22 guardrail
# ---------------------------------------------------------------------------------------------
ANY_VALUE = st.one_of(st.text(max_size=16), st.integers(min_value=-10**9, max_value=10**9),
                      st.floats(allow_nan=True, allow_infinity=True), st.booleans(), st.none())
REASON = st.text(min_size=5, max_size=40).filter(lambda s: len(s.strip()) >= 5)
AUDIT_RECORDS = st.lists(
    st.fixed_dictionaries({"user_id": ANY_VALUE, "role": ANY_VALUE, "parameter_name": ANY_VALUE,
                           "old_value": ANY_VALUE, "new_value": ANY_VALUE, "reason_for_change": REASON}),
    min_size=1, max_size=8,
)
TAMPERED_FIELDS = ("user_id", "role", "parameter_name", "old_value", "new_value",
                   "reason_for_change", "timestamp", "prev_hash", "human_approved")


def _draw_tampered(data, field: str, original):
    """Draw a replacement whose recorded text differs from the original (no rejected examples).

    Either an arbitrary value or the original text with a suffix (a near-identical edit); a
    draw with the same text as the original gets a "~" appended instead of being rejected.
    """
    base = st.text(max_size=64) if field in ("timestamp", "prev_hash", "reason_for_change") else ANY_VALUE
    appended = st.text(min_size=1, max_size=8).map(lambda suffix: f"{original}{suffix}")
    value = data.draw(st.one_of(base, appended), label=f"{field} tampered")
    return value if str(value) != str(original) else f"{original}~"


@settings(max_examples=60, deadline=None, derandomize=True)
@given(records=AUDIT_RECORDS, data=st.data())
def test_pbt_06_part11_audit_chain_any_field_tamper_detection(records, data):
    """URS-15 (Part 11 audit trail) and the Annex 22 guardrail for any chain of 1-8 records.

    Records carry arbitrary values (text, integers, floats including NaN/Inf, booleans, None)
    and a reason with >= 5 non-blank characters. The chain links genesis -> record 0 -> ... and
    verifies True; a change without human approval raises PermissionError and adds nothing.
    In every example each field in turn (user_id, role, parameter_name, old_value, new_value,
    reason_for_change, timestamp, prev_hash, and human_approved, which is flipped) is tampered
    with in a randomly drawn record: verify_chain_integrity() is always False, and True again
    once the original value is restored. "Tampering" means a different recorded text: the
    payload hashes str(value), so a type-only change with the same text (1 -> "1") is outside
    this property (v1.4.0 limitation, reported).
    """
    logger = audit.AuditTrailLogger()
    for record in records:
        logger.append_record(**record, human_approved=True)
    assert logger.verify_chain_integrity() is True
    assert logger.records[0]["prev_hash"] == "GENESIS_BLOCK_0000000000000000"
    for previous, current in zip(logger.records, logger.records[1:]):
        assert current["prev_hash"] == previous["sha256_hash"]

    with pytest.raises(PermissionError):
        logger.append_record(**records[0], human_approved=False)
    assert len(logger.records) == len(records) and logger.verify_chain_integrity() is True

    for field in TAMPERED_FIELDS:
        idx = data.draw(st.integers(min_value=0, max_value=len(records) - 1), label=f"{field} index")
        original = logger.records[idx][field]
        if field == "human_approved":
            tampered = not original
        else:
            tampered = _draw_tampered(data, field, original)
        logger.records[idx][field] = tampered
        assert logger.verify_chain_integrity() is False, (idx, field, original, tampered)
        logger.records[idx][field] = original
        assert logger.verify_chain_integrity() is True, (idx, field)
    event(f"chain length: {len(records)}")


# ---------------------------------------------------------------------------------------------
# PBT-07: SPC capability ordering and TOST equivalence
# ---------------------------------------------------------------------------------------------
@settings(max_examples=60, deadline=None, derandomize=True)
@given(
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    n_a=st.integers(min_value=3, max_value=40),
    n_b=st.integers(min_value=3, max_value=40),
    mu=st.floats(min_value=-50.0, max_value=50.0),
    sigma=st.floats(min_value=0.01, max_value=10.0),
    shift=st.floats(min_value=-3.0, max_value=3.0),
    spread_ratio=st.floats(min_value=0.2, max_value=5.0),
    lsl_offset=st.floats(min_value=-6.0, max_value=6.0),
    spec_width=st.floats(min_value=0.01, max_value=12.0),
    margin_ratio=st.floats(min_value=0.01, max_value=10.0),
)
def test_pbt_07_spc_tost_symmetry_and_capability_ordering(seed, n_a, n_b, mu, sigma, shift, spread_ratio,
                                                         lsl_offset, spec_width, margin_ratio):
    """URS-15 (SPC capability and TOST + Levene) for random normal samples, LSL < USL, margin > 0.

    Capability: Ppk = min(Ppu, Ppl) <= (Ppu + Ppl)/2 = Pp and Cpk <= Cp (within), +0.01 for the
    2-decimal outputs. TOST is symmetric: p_tost(a, b) == p_tost(b, a) and
    mean_diff(a, b) == -mean_diff(b, a), bit for bit. Identical groups (n >= 3): mean_diff 0,
    Levene compatible, and statistically_equivalent exactly when the margin exceeds
    t(0.95, 2(n-1)) * sqrt(2 s^2 / n) (TOST / 90 % confidence-interval duality, computed here
    independently with scipy.stats.t.ppf; a 1e-6 relative band around the threshold is not
    judged). "Identical groups are always equivalent" is false for small margins, and n = 2
    makes Levene 0/0 in v1.4.0 (reported), hence n >= 3.
    """
    rng = np.random.default_rng(seed)
    a = rng.normal(mu, sigma, n_a)
    b = rng.normal(mu + shift * sigma, sigma * spread_ratio, n_b)
    lsl = mu + lsl_offset * sigma
    usl = lsl + spec_width * sigma
    cap = spc.compute_process_capability(a, lsl=lsl, usl=usl)
    assert cap["ppk"] <= cap["pp"] + 0.01, (cap["ppk"], cap["pp"])
    assert cap["cpk_within"] <= cap["cp_within"] + 0.01, (cap["cpk_within"], cap["cp_within"])

    margin = margin_ratio * sigma
    ab = spc.compare_bioreactor_equivalence_tost(a, b, equiv_margin=margin)
    ba = spc.compare_bioreactor_equivalence_tost(b, a, equiv_margin=margin)
    assert ab["p_tost"] == ba["p_tost"], (ab["p_tost"], ba["p_tost"])
    assert ab["mean_diff"] == -ba["mean_diff"]

    same = spc.compare_bioreactor_equivalence_tost(a, a.copy(), equiv_margin=margin)
    assert same["mean_diff"] == 0.0 and same["p_lower"] == same["p_upper"]
    assert same["variances_compatible"] is True and same["levene_p_value"] > 0.99
    threshold = stats.t.ppf(0.95, 2.0 * (n_a - 1)) * math.sqrt(2.0 * a.var(ddof=1) / n_a)
    event(f"identical groups equivalent: {same['statistically_equivalent']}")
    if margin > threshold * (1.0 + 1e-6):
        assert same["statistically_equivalent"] is True, (margin, threshold)
    elif margin < threshold * (1.0 - 1e-6):
        assert same["statistically_equivalent"] is False, (margin, threshold)
