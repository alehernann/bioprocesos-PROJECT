"""FDA Computer Software Assurance (CSA) Operational Qualification (OQ) suite.

This suite implements the risk-based OQ test protocol defined in the FDA CSA Risk
Assessment (docs/02_FDA_CSA_Risk_Assessment_2026.md). Tests are grouped by CSA
category:

* ``test_oq_*``       -> "Scripted Testing (High Process Risk)" -- deterministic,
  fully scripted qualification of high-process-risk control, safety, design-space,
  thermal and data-integrity functions.
* ``test_exploratory_*`` -> "Unscripted / Error-Guessing (Not High Process Risk)"
  -- ad-hoc / error-guessing probes of input validation and non-critical paths.

Floating-point assertions use ``pytest.approx`` with engineering tolerances. All
expected numeric values were verified against the ACTUAL function outputs before
being written (honesty constraint: equations/tests are not altered to force a pass).

v1.4.0 change control (CHANGELOG 1.4.0, docs/03 section 10): test_oq_03, 03b, 03c,
03d, 03e, 04b and 06b were revised for the calibrated six-state model, and
test_oq_03f, 03g, 03h and 08b are new. ASME V&V 40 split: software verification
(OQ: balances, positivity, convergence, slider-domain stability) versus model
validation against Bionova NISTCHO 2026 (test_oq_03g).
"""

import itertools
import time
from dataclasses import replace

import numpy as np
import pydantic
import pytest
from scipy import stats

from src import model_validation as mv
from src.amab_design_space import (
    AMAB_MEASURED_KLA_H_INV,
    C_STAR_O2_MMOL_L,
    C_STAR_PURE_O2_MMOL_L,
    Y_O2_AIR,
    compute_scale_up_engineering,
    evaluate_amab_design_space,
    measured_kla_for_volume,
)
from src.audit_trail_part11 import AuditTrailLogger
import src.bioreactor_twin as twin
from src.bioreactor_twin import (
    CALIBRATED_KINETICS,
    G_BOOST_CONC,
    NH3_DEATH_ONSET_MM,
    check_safety_interlocks,
    compute_dissolved_oxygen_state,
    compute_hydrodynamic_stress,
    compute_split_range_ph_actuators,
    get_temperature_setpoint,
    do_hypoxia_factor,
    simulate_cho_fed_batch,
)
from src.models import ProcessDescription
from src.spc_six_sigma import (
    GORSKY_TABLE_6_1_TORQUE_N10,
    GORSKY_TABLE_6_2_TORQUE_N30,
    compare_bioreactor_equivalence_tost,
    compare_bioreactor_equivalence_ttest,
    compute_iso16269_tolerance_interval,
    compute_process_capability,
)
from src.thermal_vtb_mkt import (
    analyze_fft_nyquist,
    apply_vtb_filter,
    calculate_mkt_celsius,
)


# ---------------------------------------------------------------------------
# SCRIPTED TESTING (High Process Risk)
# ---------------------------------------------------------------------------


def test_oq_01_setpoints_and_ph_split_range_exclusivity():
    """Default set-points, pH split-range exclusivity and O2 transfer sufficiency.

    THE SYSTEM supplies set-points; regulation inside the operational band is
    delegated to the local controllers, so no closed-loop temperature or DO
    trajectory (settling band) is simulated or asserted here.
    """
    # URS-01 / URS-03 / URS-06: default set-points of ProcessDescription.
    cfg = ProcessDescription()
    assert cfg.temp_initial_C == pytest.approx(36.5, abs=1e-9)
    assert get_temperature_setpoint(0.0) == pytest.approx(36.5, abs=1e-9)
    assert cfg.ph_setpoint == pytest.approx(7.00, abs=1e-9)
    assert cfg.ph_deadband == pytest.approx(0.20, abs=1e-9)
    assert cfg.do_setpoint_pct == pytest.approx(30.0, abs=1e-9)

    # URS-03: inside the deadband (7.00 +/- 0.20) both actuators rest at 0.0.
    for ph in (6.80, 6.85, 7.00, 7.15, 7.20):
        out = compute_split_range_ph_actuators(
            ph, setpoint=cfg.ph_setpoint, deadband=cfg.ph_deadband
        )
        assert out["co2_valve_pct"] == pytest.approx(0.0, abs=1e-9)
        assert out["base_pump_pct"] == pytest.approx(0.0, abs=1e-9)

    # URS-04 / URS-05: mutual exclusivity over the whole pH 6.00-8.00 range
    # (0.01 steps): never both actuators > 0; CO2 only above, base only below band.
    upper = cfg.ph_setpoint + cfg.ph_deadband
    lower = cfg.ph_setpoint - cfg.ph_deadband
    for k in range(201):
        ph = 6.00 + 0.01 * k
        out = compute_split_range_ph_actuators(
            ph, setpoint=cfg.ph_setpoint, deadband=cfg.ph_deadband
        )
        co2, base = out["co2_valve_pct"], out["base_pump_pct"]
        assert not (co2 > 0.0 and base > 0.0), f"both actuators active at pH {ph:.2f}"
        if co2 > 0.0:
            assert ph > upper
        if base > 0.0:
            assert ph < lower

    # URS-06: mass-transfer sufficiency OTR >= OUR at the test corners Vs
    # 0.005-0.017 m/s (modeling assumption) x P/V 19-30 W/m3 (Bionova), with the OUR
    # basis of compute_scale_up_engineering (defaults: 15e6 cells/mL, qO2 1.0e-10
    # mmol/(cell*h)).
    for vs in (0.005, 0.017):
        for pv in (19.0, 30.0):
            eng = compute_scale_up_engineering(vs, pv)
            assert eng["otr_mmol_L_h"] >= eng["our_max_mmol_L_h"], (
                f"OTR {eng['otr_mmol_L_h']:.3f} < OUR {eng['our_max_mmol_L_h']:.3f}"
                f" at Vs={vs}, P/V={pv}"
            )
            assert eng["oxygen_sufficient"] is True


def test_oq_02_automated_day7_temperature_shift():
    """Biphasic temperature shift at day 7.0, recorded in an intact audit trail."""
    assert get_temperature_setpoint(6.9) == pytest.approx(36.5, abs=1e-9)
    assert get_temperature_setpoint(7.0) == pytest.approx(34.0, abs=1e-9)

    # URS-02: the automated shift is logged to the Part 11 audit trail.
    logger = AuditTrailLogger()
    simulate_cho_fed_batch(ProcessDescription(mode="closed_loop"), audit_logger=logger)
    shifts = [
        r for r in logger.records if r["parameter_name"] == "temperature_setpoint_C"
    ]
    assert len(shifts) == 1
    assert shifts[0]["old_value"] == "36.5"
    assert shifts[0]["new_value"] == "34.0"
    assert "day 7.0" in shifts[0]["reason_for_change"]
    assert logger.verify_chain_integrity() is True


def _assert_glucose_rule(res, g_min, g_target):
    """Event-by-event check of the URS-07 pre-feed rule; returns the number of top-ups."""
    fired = 0
    for ev in res["feed_events"]:
        v_old, v_basal = ev["V_old_L"], ev["v_basal_L"]
        g_pre = ev["pre"]["G"]
        g_actual = (g_pre * v_old + v_basal * G_BOOST_CONC) / (v_old + v_basal)
        needed = (g_pre < g_min or g_actual < g_min) and g_actual < g_target
        if needed:
            fired += 1
            assert ev["v_gluc_L"] > 0.0, ev["day"]
            assert ev["post"]["G"] == pytest.approx(g_target, abs=1e-9), ev["day"]
        else:
            assert ev["v_gluc_L"] == 0.0, ev["day"]
        assert ev["post"]["G"] >= g_min, ev["day"]
    return fired


def test_oq_03_closed_loop_vs_static_titer_gain():
    """URS-07 pre-feed glucose rule event by event and URS-08 emergent closed_loop vs static comparison.

    v1.4.0 change control. A top-up fires exactly when the pre-feed (or post-bolus)
    glucose is below the trigger and the bolus alone does not reach the target, and it
    lands exactly on the target. With the calibrated feed glucose (G_BOOST_CONC 76.44 g/L)
    the default runs keep G >= 2.0 g/L on every feed day, so the rule is also exercised
    with a validated higher trigger (6.0 -> 9.0 g/L). URS-08 is directional on harvested
    mass and final viability; the g/L titer difference is emergent and only reported,
    because the larger Ark feed volume dilutes the titer.
    """
    feed_days = [2.0, 4.0, 6.0, 8.0, 10.0, 12.0]
    static = simulate_cho_fed_batch(ProcessDescription(mode="static"))
    closed = simulate_cho_fed_batch(ProcessDescription(mode="closed_loop"))
    baseline = simulate_cho_fed_batch(ProcessDescription(mode="bionova_baseline"))

    # URS-07 with the default 2.0 -> 5.0 g/L rule.
    for res in (closed, baseline):
        assert [ev["day"] for ev in res["feed_events"]] == feed_days
        _assert_glucose_rule(res, 2.0, 5.0)
        glucose, time_days = res["glucose_g_L"], res["time_days"]
        for fd in feed_days:
            assert glucose[time_days.index(fd)] >= 2.0
    assert all(ev["v_gluc_L"] == 0.0 for ev in static["feed_events"])

    # URS-07 exercised with a validated higher trigger (6.0 -> 9.0 g/L).
    high = dict(glucose_min_threshold_g_L=6.0, glucose_refill_target_g_L=9.0)
    for mode in ("closed_loop", "bionova_baseline"):
        res = simulate_cho_fed_batch(ProcessDescription(mode=mode, **high))
        assert _assert_glucose_rule(res, 6.0, 9.0) >= 1, mode
        assert res["total_feed_volume_L"] > sum(ev["v_basal_L"] for ev in res["feed_events"])
    static_high = simulate_cho_fed_batch(ProcessDescription(mode="static", **high))
    assert all(ev["v_gluc_L"] == 0.0 for ev in static_high["feed_events"])

    # Bolus train: 4.62 % of V0 on every feed day; closed_loop x1.80 on day 8 and x1.82
    # on day 10 (Ark reports +80 % / +82 % versus the day-0 plan).
    v0 = 0.70 * 0.25
    for ev in static["feed_events"]:
        assert ev["v_basal_L"] == pytest.approx(0.0462 * v0, rel=1e-12)
    factors = {8.0: 1.80, 10.0: 1.82}
    for ev in closed["feed_events"]:
        assert ev["v_basal_L"] == pytest.approx(0.0462 * v0 * factors.get(ev["day"], 1.0), rel=1e-12)

    # Net lactate reconsumption after the peak in both modes.
    for res in (static, closed):
        assert res["lactate_g_L"][-1] < res["peak_lactate_g_L"]

    # URS-08: directional on harvested mass and viability (emergent, no fixed band).
    assert closed["harvested_mass_g"] > static["harvested_mass_g"]
    assert closed["final_viability_pct"] > static["final_viability_pct"]


def test_oq_03b_vessel_capacity_and_bolus_mass_balance():
    """V0 = initial_fill_fraction * vessel, V(t) <= vessel and exact six-species balance in every bolus.

    Checked at 0.25 L and 2.0 L, in the three modes, at the default fill (0.70) and at the
    Bionova fill (0.76 = 190/250 mL): C_before*V_old + added == C_after*V_new for Xv, Xd,
    G, L, NH3 and titer, against the event record and the recorded post-feed series. The
    daily_pre_feed state of a feed day is the state before its bolus.
    """
    series = {
        "Xv": "vcd", "Xd": "dead_cell_density", "G": "glucose_g_L",
        "L": "lactate_g_L", "NH3": "nh3_mmol_L", "Titer": "titer_g_L",
    }
    for fill in (0.70, 0.76):
        for vessel in (0.25, 2.0):
            for mode in ("static", "bionova_baseline", "closed_loop"):
                res = simulate_cho_fed_batch(
                    ProcessDescription(mode=mode, vessel_volume_L=vessel, initial_fill_fraction=fill)
                )
                volume = res["volume_L"]
                assert volume[0] == pytest.approx(fill * vessel, abs=1e-12)
                assert max(volume) <= vessel + 1e-12
                assert len(res["feed_events"]) == 6
                for ev in res["feed_events"]:
                    k = ev["step_index_after"]
                    v_old, v_new = ev["V_old_L"], ev["V_new_L"]
                    assert 0.0 <= ev["scale_factor"] <= 1.0
                    assert v_new == pytest.approx(v_old + ev["v_basal_L"] + ev["v_gluc_L"], abs=1e-12)
                    assert volume[k] == pytest.approx(v_new, abs=1e-12)
                    for key, name in series.items():
                        added = ev["glucose_added_g"] if key == "G" else 0.0
                        before = ev["pre"][key] * v_old + added
                        assert ev["post"][key] * v_new == pytest.approx(before, abs=1e-9), (fill, vessel, mode, key)
                        assert res[name][k] * v_new == pytest.approx(before, abs=1e-9), (fill, vessel, mode, key)
                    pre_day = res["daily_pre_feed"][int(ev["day"])]
                    assert pre_day["G"] == pytest.approx(ev["pre"]["G"], abs=1e-12)
                    assert pre_day["V"] == pytest.approx(v_old, abs=1e-12)


def test_oq_03c_lactate_reconsumption_and_nonnegativity():
    """Lactate peaks in the growth phase (days 4-6) and is reconsumed; L(t) >= 0 in every mode.

    v1.4.0 change control: the peak now comes from the state-governed switch, not from
    the day-7 temperature step (v1.3.x asserted a peak after day 5).
    """
    for mode in ("static", "bionova_baseline", "closed_loop"):
        res = simulate_cho_fed_batch(ProcessDescription(mode=mode))
        lactate = res["lactate_g_L"]
        assert min(lactate) >= 0.0, mode
        assert 4.0 <= res["peak_lactate_day"] <= 6.0, mode
        assert lactate[-1] < res["peak_lactate_g_L"], mode
        assert lactate[res["time_days"].index(8.0)] < 0.5 * res["peak_lactate_g_L"], mode


def test_oq_03d_lactate_switch_state_governed():
    """Bionova protocol: lactate peaks on day 4-5 at 1.2-1.5 g/L and falls to 0.2-0.6 g/L by day 7.

    Daily pre-feed samples (Bionova sampling). Moving the temperature shift from day 7 to
    day 10 or 14 leaves the peak day, the peak value window and the day-7 reconsumption
    unchanged: the switch is set by the state (growth slowing through Xv, L and NH3), not
    by the temperature step. v1.4.0 change control: replaces test_oq_03d_lactate_profile_v131.
    """
    base = mv.bionova_process_description()
    for shift in (7.0, 10.0, 14.0):
        cfg = ProcessDescription(**{**base.model_dump(), "temp_shift_day": shift})
        daily = simulate_cho_fed_batch(cfg)["daily_pre_feed"]
        lactate = [daily[d]["L"] for d in range(15)]
        peak_day = max(range(15), key=lactate.__getitem__)
        assert peak_day in (4, 5), shift
        assert 1.2 <= lactate[peak_day] <= 1.5, shift
        assert 0.2 <= lactate[7] <= 0.6, shift
        assert lactate[8] < 0.6, shift


def test_oq_03e_bolus_clipped_alarm():
    """Capacity clamp alarm: False at the 0.70 default fill, True at 0.95; V never exceeds the vessel.

    v1.4.0 change control: the fill is the validated ProcessDescription.initial_fill_fraction
    (v1.3.x monkeypatched a module constant).
    """
    for fill, expected in ((0.70, False), (0.95, True)):
        for vessel in (0.25, 2.0):
            for mode in ("static", "closed_loop"):
                res = simulate_cho_fed_batch(
                    ProcessDescription(mode=mode, vessel_volume_L=vessel, initial_fill_fraction=fill)
                )
                assert res["bolus_clipped_alarm"] is expected, (fill, vessel, mode)
                assert (res["n_bolus_clipped"] > 0) is expected
                assert max(res["volume_L"]) <= vessel + 1e-12


def test_oq_03f_rk45_convergence_and_nh3_decline(monkeypatch):
    """Integrator convergence, NH3 accumulation and a real viability decline over 21 days.

    Calculation verification: production RK45 (rtol 1e-6, atol 1e-9) agrees with RK45 and
    Radau at rtol 1e-9 to < 1e-4 of each series' magnitude, the two references agree to
    < 1e-6, the automatic Radau fallback reproduces RK45, and the v1.3.2 explicit Euler
    scheme (dt 0.1 d) has a larger error. NH3 never decreases between boluses, passes the
    5 mM death onset by day 14 and keeps rising to day 21, where viability has fallen by
    more than 20 points; with kd_NH3 = 0 the same runs keep a higher viability.
    """
    conv = mv.check_numerical_convergence()
    assert conv["production_vs_rk45_1e9"]["overall"] < 1e-4
    assert conv["production_vs_radau_1e9"]["overall"] < 1e-4
    assert conv["rk45_1e9_vs_radau_1e9"]["overall"] < 1e-6
    assert conv["euler_dt0p1_vs_rk45_1e9"]["overall"] > 10 * conv["production_vs_rk45_1e9"]["overall"]
    assert conv["fallback_used"] is False

    # Automatic Radau fallback, forced with a tiny RK45 budget, reproduces RK45.
    reference = simulate_cho_fed_batch(ProcessDescription())
    monkeypatch.setattr(twin, "MAX_RHS_EVALS_PER_SEGMENT", 20)
    forced = twin.simulate_cho_fed_batch(ProcessDescription())
    monkeypatch.undo()
    assert forced["solver"]["fallback_used"] is True
    assert {s["method"] for s in forced["solver"]["segments"]} == {"Radau"}
    for key in ("vcd", "glucose_g_L", "lactate_g_L", "nh3_mmol_L", "titer_g_L"):
        ref = np.asarray(reference[key])
        assert np.max(np.abs(np.asarray(forced[key]) - ref)) <= 1e-4 * np.max(np.abs(ref)), key

    no_nh3_death = replace(CALIBRATED_KINETICS, kd_nh3=0.0)
    for mode in ("static", "closed_loop"):
        r14 = simulate_cho_fed_batch(ProcessDescription(mode=mode, duration_days=14))
        r21 = simulate_cho_fed_batch(ProcessDescription(mode=mode, duration_days=21))
        nh3 = r21["nh3_mmol_L"]
        bolus_steps = {ev["step_index_after"] for ev in r21["feed_events"]}
        for i in range(1, len(nh3)):
            if i not in bolus_steps:
                assert nh3[i] >= nh3[i - 1] - 1e-12, (mode, i)
        assert r14["final_nh3_mmol_L"] > NH3_DEATH_ONSET_MM
        assert r21["final_nh3_mmol_L"] > r14["final_nh3_mmol_L"]
        assert r21["final_viability_pct"] < r14["final_viability_pct"] - 20.0, mode
        assert r21["vcd"][-1] < 0.5 * r21["peak_vcd"], mode
        for duration, run in ((14, r14), (21, r21)):
            counterfactual = simulate_cho_fed_batch(
                ProcessDescription(mode=mode, duration_days=duration), kinetics=no_nh3_death
            )
            assert counterfactual["final_viability_pct"] > run["final_viability_pct"], (mode, duration)


def test_oq_03g_bionova_validation_fit_and_oos():
    """Calibration reproducibility, in-sample fit (30 W/m3) and out-of-sample prediction (19 W/m3).

    ASME V&V 40 model validation against data/bionova_nistcho_2026.json (pre-feed daily
    sampling). The shipped constants are at least as good as a fresh calibration from the
    documented prior (10 free parameters, 60 points). Credibility criterion for the context
    of use (feeding-strategy screening): RMSE <= 2 x declared uncertainty for every
    in-sample variable and for the 19 W/m3 VCD series, and every 19 W/m3 point within
    2 x its uncertainty. K_I_L is reported as not identifiable.
    """
    ds = mv.load_bionova_reference_dataset()
    assert ds["sampling_timing"] == "pre_feed_daily"
    assert set(ds["value_type_definitions"]) == {"printed_exact", "digitized_figure_approx"}
    cfg = mv.bionova_process_description("stratyx_30_W_m3", ds)
    assert cfg.mode == "bionova_baseline"
    assert cfg.initial_fill_fraction == pytest.approx(0.76, abs=1e-12)
    assert cfg.vessel_volume_L * cfg.initial_fill_fraction == pytest.approx(0.190, abs=1e-12)

    cal = mv.run_parameter_calibration(dataset=ds)
    assert cal["success"] is True
    assert cal["n_parameters"] == 10 and cal["n_observations"] == 60
    assert mv.calibration_cost(dataset=ds) <= cal["cost"] * 1.01
    for row in cal["parameter_table"]:
        assert row["lower_bound"] <= row["value"] <= row["upper_bound"], row
    ident = mv.compute_jacobian_identifiability(cal["opt_result"], cal["param_names"])
    sv = ident["singular_values"]
    assert all(a >= b for a, b in zip(sv, sv[1:])) and sv[-1] > 0.0
    assert 1.0 < ident["condition_number"] < 1e6
    assert "k_i_lactate" in ident["not_identifiable"]
    assert len(ident["identifiable"]) >= 8
    k_il = {row["parameter"]: row for row in cal["parameter_table"]}["k_i_lactate"]
    assert k_il["value"] - k_il["lower_bound"] <= 0.05 * (k_il["upper_bound"] - k_il["lower_bound"])

    sim30 = mv.simulate_bionova_condition("stratyx_30_W_m3", dataset=ds)
    m30 = mv.compute_validation_metrics(sim30, ds, "stratyx_30_W_m3")
    assert set(m30["variables"]) == {
        "vcd_1e6_mL", "viability_pct", "glucose_g_L", "lactate_g_L", "nh3_mmol_L", "titer_g_L"}
    for key, v in m30["variables"].items():
        assert v["meets_credibility_criterion"], (key, v["rmse_over_sigma"])
        obs, mod = np.asarray(v["observed"]), np.asarray(v["model"])
        assert v["RMSE"] == pytest.approx(float(np.sqrt(np.mean((mod - obs) ** 2))), rel=1e-12)
        if v["R2"] is not None:
            r2 = 1.0 - np.sum((mod - obs) ** 2) / np.sum((obs - obs.mean()) ** 2)
            assert v["R2"] == pytest.approx(float(r2), rel=1e-12)
    assert m30["variables"]["vcd_1e6_mL"]["R2"] >= 0.95
    assert m30["variables"]["titer_g_L"]["R2"] >= 0.90
    assert abs(m30["variables"]["viability_pct"]["day14_abs_error"]) <= 2 * 2.0
    assert abs(m30["variables"]["titer_g_L"]["day14_abs_error"]) <= 2 * 0.08

    sim19 = mv.simulate_bionova_condition("stratyx_19_W_m3", dataset=ds)
    m19 = mv.compute_validation_metrics(sim19, ds, "stratyx_19_W_m3")
    assert m19["role"].startswith("out-of-sample")
    assert m19["variables"]["vcd_1e6_mL"]["meets_credibility_criterion"]
    for key, point in m19["points"].items():
        assert point["within_2sigma"], (key, point["abs_error"])


def test_oq_03h_slider_domain_physical_stability():
    """Every corner of the Streamlit slider domain integrates to a finite, physical result in < 0.25 s.

    Full factorial of the slider extremes P/V {2, 100} W/m3, sparge {0, 1} vvm,
    temp_shift_day {1, 14} d, DO {10, 90} %, V {0.25, 35000} L and duration {5, 21} d,
    for static and closed_loop with and without O2 enrichment (256 runs). A shift later
    than the run (14 > 5 d) is rejected by the schema and run with the dashboard clamp
    min(shift, duration). Checks: no NaN/Inf, concentrations >= 0, viability in [0, 100],
    V(t) <= vessel, wall time < 0.25 s per run, and mean wall time of the default 14-day
    run < 80 ms (Streamlit budget).
    """
    keys_nonneg = ("vcd", "dead_cell_density", "glucose_g_L", "lactate_g_L", "nh3_mmol_L",
                   "titer_g_L", "volume_L", "do_real_pct")
    corners = itertools.product(
        (2.0, 100.0), (0.0, 1.0), (1.0, 14.0), (10.0, 90.0), (0.25, 35000.0), (5, 21),
        ("static", "closed_loop"), (True, False),
    )
    n_runs = 0
    for pv, sparge, shift, do, vessel, duration, mode, enrich in corners:
        common = dict(power_density_W_m3=pv, sparge_vvm=sparge, do_setpoint_pct=do,
                      vessel_volume_L=vessel, duration_days=duration, mode=mode,
                      o2_enrichment_enabled=enrich)
        if shift > duration:
            with pytest.raises(pydantic.ValidationError):
                ProcessDescription(temp_shift_day=shift, **common)
            shift = min(shift, float(duration))
        cfg = ProcessDescription(temp_shift_day=shift, **common)
        t0 = time.perf_counter()
        res = simulate_cho_fed_batch(cfg)
        elapsed = time.perf_counter() - t0
        n_runs += 1
        label = (pv, sparge, shift, do, vessel, duration, mode, enrich)
        assert elapsed < 0.25, (label, elapsed)
        for key in keys_nonneg + ("viability_pct",):
            arr = np.asarray(res[key], dtype=float)
            assert np.all(np.isfinite(arr)), (label, key)
            if key in keys_nonneg:
                assert arr.min() >= 0.0, (label, key)
        via = np.asarray(res["viability_pct"])
        assert via.min() >= 0.0 and via.max() <= 100.0, label
        assert max(res["volume_L"]) <= vessel * (1.0 + 1e-12), label
        assert len(res["time_days"]) == 10 * duration + 1
    assert n_runs == 256

    t0 = time.perf_counter()
    for _ in range(20):
        simulate_cho_fed_batch(ProcessDescription())
    assert (time.perf_counter() - t0) / 20 < 0.080


def test_oq_04_safety_shear_and_cip_sip_interlocks():
    """GxP safety indicators: shear alarm, CIP block, CIP velocity and SIP sterility (nominal, boundary, failure).

    Nominal case plus the URS-11 / URS-12 boundary and failure cases: CIP velocity
    below 1.52 m/s, SIP with F0 < 15 min, SIP with a temperature below 121.1 C, and
    both SIP failures together. The function returns indicators only; it does not
    abort or release anything.
    """
    out = check_safety_interlocks(
        power_density_W_m3=50.0,
        sparge_vvm=0.20,
        batch_active=True,
        cip_valve_requested=True,
        cip_pipe_velocity_m_s=1.52,
        sip_temps_C=[121.5] * 15,
        dt_min=1.0,
    )
    assert out["high_shear_alarm"] is True
    assert out["cip_interlock_blocked"] is True
    assert out["cip_velocity_compliant"] is True
    assert out["sip_sterile_compliant"] is True

    common = dict(
        power_density_W_m3=30.0,
        sparge_vvm=0.10,
        batch_active=False,
        cip_valve_requested=False,
        dt_min=1.0,
    )

    # URS-11: CIP velocity boundary. 1.52 m/s complies; anything below does not.
    for velocity, expected in ((1.52, True), (1.51, False), (1.0, False), (0.0, False)):
        cip = check_safety_interlocks(
            cip_pipe_velocity_m_s=velocity, sip_temps_C=[121.5] * 15, **common
        )
        assert cip["cip_velocity_compliant"] is expected, velocity

    # URS-12: SIP boundary and failure cases.
    # F0 boundary: 15 min at exactly 121.1 C gives F0 = 15.0 min and complies.
    sip = check_safety_interlocks(
        cip_pipe_velocity_m_s=1.52, sip_temps_C=[121.1] * 15, **common
    )
    assert sip["f0_minutes"] == pytest.approx(15.0, abs=1e-9)
    assert sip["sip_sterile_compliant"] is True
    # F0 < 15 min with every temperature at 121.1 C: 14 min gives F0 = 14.0.
    sip = check_safety_interlocks(
        cip_pipe_velocity_m_s=1.52, sip_temps_C=[121.1] * 14, **common
    )
    assert sip["f0_minutes"] < 15.0
    assert sip["sip_sterile_compliant"] is False
    # Temperature below 121.1 C with F0 >= 15 min: 20 min at 121.0 C gives
    # F0 = 20 * 10**(-0.01) ~= 19.5 min, but the temperature criterion fails.
    sip = check_safety_interlocks(
        cip_pipe_velocity_m_s=1.52, sip_temps_C=[121.0] * 20, **common
    )
    assert sip["f0_minutes"] >= 15.0
    assert sip["sip_sterile_compliant"] is False
    # One sub-121.1 C reading inside an otherwise compliant cycle also fails.
    sip = check_safety_interlocks(
        cip_pipe_velocity_m_s=1.52, sip_temps_C=[121.5] * 14 + [121.0], **common
    )
    assert sip["f0_minutes"] >= 15.0
    assert sip["sip_sterile_compliant"] is False
    # Both failures: 10 min at 120.0 C (F0 ~= 7.8 min, temperature below 121.1 C).
    sip = check_safety_interlocks(
        cip_pipe_velocity_m_s=1.52, sip_temps_C=[120.0] * 10, **common
    )
    assert sip["f0_minutes"] < 15.0
    assert sip["sip_sterile_compliant"] is False



def test_oq_04b_shear_or_gate_and_continuous_penalty():
    """Shear alarm stays P/V > 47.6 OR sparge > 0.15; the kinetic penalty is decoupled and sparge-driven.

    v1.4.0 change control. check_safety_interlocks keeps the conservative URS-09 alarm.
    Inside the ODEs, P/V up to 100 W/m3 (the schema limit) has no kinetic effect: the
    impeller damage onset is 476 W/m3, ten times the alarm and still below the damage
    levels of A-Mab p.100 / Ma 2002 (A-Mab runs healthy at 60 W/m3 local). Sparge above
    0.15 vvm (bubble stress) lowers titer and viability, and adding P/V on top of it
    changes nothing.
    """
    common = dict(
        batch_active=False,
        cip_valve_requested=False,
        cip_pipe_velocity_m_s=1.52,
        sip_temps_C=[121.5] * 15,
    )
    for pv, sparge in ((30.0, 0.10), (47.6, 0.15)):
        out = check_safety_interlocks(power_density_W_m3=pv, sparge_vvm=sparge, **common)
        assert out["high_shear_alarm"] is False, (pv, sparge)
    for pv, sparge in ((50.0, 0.10), (65.0, 0.10), (30.0, 0.22), (65.0, 0.22)):
        out = check_safety_interlocks(power_density_W_m3=pv, sparge_vvm=sparge, **common)
        assert out["high_shear_alarm"] is True, (pv, sparge)

    # Kinetic stress intensity: zero for every P/V in the schema domain.
    for pv in (2.0, 30.0, 47.6, 50.0, 60.0, 65.0, 100.0):
        stress = compute_hydrodynamic_stress(pv, 0.10)
        assert stress["sigma_impeller"] == 0.0 and stress["sigma_total"] == 0.0, pv
    assert compute_hydrodynamic_stress(30.0, 0.22)["sigma_sparge"] == pytest.approx(0.07 / 0.15, rel=1e-12)
    assert compute_hydrodynamic_stress(952.0, 0.10)["sigma_impeller"] == pytest.approx(1.0, rel=1e-12)

    keys = ("final_titer_g_L", "final_viability_pct", "peak_vcd", "harvested_mass_g")
    for mode in ("static", "closed_loop"):
        nominal = simulate_cho_fed_batch(
            ProcessDescription(mode=mode, power_density_W_m3=30.0, sparge_vvm=0.10)
        )
        # Alarm on, kinetics unchanged: 50-60 W/m3 does not destroy qp (decoupling).
        for pv in (50.0, 60.0, 65.0, 100.0):
            res = simulate_cho_fed_batch(
                ProcessDescription(mode=mode, power_density_W_m3=pv, sparge_vvm=0.10)
            )
            for key in keys:
                assert res[key] == nominal[key], (mode, pv, key)
        sparge_only = simulate_cho_fed_batch(
            ProcessDescription(mode=mode, power_density_W_m3=30.0, sparge_vvm=0.22)
        )
        both = simulate_cho_fed_batch(
            ProcessDescription(mode=mode, power_density_W_m3=65.0, sparge_vvm=0.22)
        )
        assert sparge_only["final_titer_g_L"] < nominal["final_titer_g_L"], mode
        assert sparge_only["final_viability_pct"] < nominal["final_viability_pct"], mode
        for key in keys:
            assert both[key] == sparge_only[key], (mode, key)


def test_oq_05_ispe_amab_design_space_center_and_edges():
    """A-Mab design space: centre-point intercepts hold; extreme corner fails."""
    nominal = evaluate_amab_design_space()
    assert nominal["z1_afuc_max"] == pytest.approx(14.70, abs=0.01)
    assert nominal["z2_afuc_min"] == pytest.approx(15.29, abs=0.01)
    assert nominal["z3_gal_max"] == pytest.approx(13.15, abs=0.01)
    assert nominal["z4_gal_min"] == pytest.approx(11.08, abs=0.01)
    assert nominal["design_space_holds"] is True

    extreme = evaluate_amab_design_space(
        cd_days=19.0, co2_mmHg=160.0, osm_mOsm=440.0, ph_val=7.1, temp_C=36.0
    )
    assert extreme["design_space_holds"] is False


def test_oq_05b_amab_scale_up_kla_pilot_commercial_range():
    """URS-06: measured kLa per scale (A-Mab Table 3.22, p.105) and the correlation anchor.

    The six measured values (2 L 10, 500 L 8, 1,000 L 10, 5,000 L 10, 15,000 L 20,
    25,000 L Future 20 h^-1) all lie in 8-20 h^-1 and, passed as
    ``measured_kla_h_inv``, are used as-is by compute_scale_up_engineering. The
    correlation (A-Mab Eq. 4 form) returns 20.0 h^-1 at its 15,000 L anchor
    (Vs 0.015 m/s, P/V 26 W/m3). The twin lookup uses the column immediately
    below the volume, with the 2 L value as a proxy below 2 L (modeling assumption).
    """
    assert AMAB_MEASURED_KLA_H_INV == {
        2.0: 10.0, 500.0: 8.0, 1000.0: 10.0, 5000.0: 10.0, 15000.0: 20.0, 25000.0: 20.0,
    }
    for volume, kla in AMAB_MEASURED_KLA_H_INV.items():
        assert 8.0 <= kla <= 20.0, (volume, kla)
        eng = compute_scale_up_engineering(0.015, 26.0, measured_kla_h_inv=kla)
        assert eng["kla_h_inv"] == pytest.approx(kla, abs=1e-12), volume

    # Correlation anchor at 15,000 L.
    assert compute_scale_up_engineering(0.015, 26.0)["kla_h_inv"] == pytest.approx(20.0, abs=1e-9)

    # Column-immediately-below lookup used by the twin (no interpolation).
    for volume, expected in (
        (0.19, 10.0), (0.25, 10.0), (2.0, 10.0), (300.0, 10.0), (500.0, 8.0),
        (999.0, 8.0), (1000.0, 10.0), (2000.0, 10.0), (5000.0, 10.0),
        (14999.0, 10.0), (15000.0, 20.0), (25000.0, 20.0), (35000.0, 20.0),
    ):
        assert measured_kla_for_volume(volume) == expected, volume
    run = simulate_cho_fed_batch(ProcessDescription(vessel_volume_L=0.25))
    assert run["kla_eff_h_inv"] == pytest.approx(10.0, abs=1e-12)


def test_oq_06_mkt_and_vtb_damping():
    """MKT of an isothermal trace equals the temperature; bulk VTB damps more."""
    assert calculate_mkt_celsius([5.0] * 288) == pytest.approx(5.0, abs=0.01)
    assert calculate_mkt_celsius([2.0, 18.0]) > 10.0

    # Build a thermal-excursion trace (steady 5 C with a transient spike + noise).
    rng = np.random.default_rng(0)
    n = 200
    air = [
        5.0 + (8.0 if 50 <= k < 80 else 0.0) + float(rng.normal(0.0, 0.5))
        for k in range(n)
    ]
    bulk = apply_vtb_filter(air, volume_key="300 mL (Bulk)")
    small = apply_vtb_filter(air, volume_key="1 mL")

    # The large-volume (bulk) buffer must damp the excursion more strongly, i.e.
    # produce a lower-variance filtered series than the 1 mL buffer.
    assert np.std(bulk) < np.std(small)



def test_oq_06b_do_setpoint_driving_force():
    """URS-06: DO driving force, controller saturation without false hypoxia, O2 enrichment and real hypoxia.

    v1.4.0 change control. Scale-up: the air default is unchanged (kLa 20.0, OTR 2.94 at
    30 % DO, OTR proportional to (1 - DO/100), insufficient at high DO) and pure O2 raises
    C*_gas to C*_air/0.2095. Twin: the biology depends only on the real liquid DO
    (C_L = min(C_sp, C*_max - OUR/kLa)). At DO 85 % with air only the controller saturates
    and DO_real passes through 55-75 % with f_do = 1.0 (no false hypoxia); real hypoxia
    appears only once Xv exceeds the air-only transfer limit (17.85e6 cells/mL at kLa
    10 h^-1). With O2 enrichment the set-point holds above 20e6 cells/mL. At DO 5 % (and
    with air-limited transfer) hypoxia lowers growth and titer and raises lactate.
    """
    ref = compute_scale_up_engineering(0.015, 26.0)
    assert ref["kla_h_inv"] == pytest.approx(20.0, abs=1e-9)
    assert ref["otr_mmol_L_h"] == pytest.approx(2.94, abs=1e-9)
    assert ref == compute_scale_up_engineering(0.015, 26.0, do_percent=30.0)
    assert ref["oxygen_sufficient"] is True

    otr30 = compute_scale_up_engineering(0.015, 26.0, do_percent=30.0)["otr_mmol_L_h"]
    otr50 = compute_scale_up_engineering(0.015, 26.0, do_percent=50.0)["otr_mmol_L_h"]
    assert otr50 / otr30 == pytest.approx((1 - 0.50) / (1 - 0.30), abs=5e-3)

    do_grid = list(range(10, 101, 5))
    otrs = [
        compute_scale_up_engineering(0.015, 26.0, do_percent=float(d))["otr_mmol_L_h"]
        for d in do_grid
    ]
    assert all(b < a for a, b in zip(otrs, otrs[1:]))
    flags = [
        compute_scale_up_engineering(0.015, 26.0, do_percent=float(d))["oxygen_sufficient"]
        for d in do_grid
    ]
    assert flags[0] is True and flags[-1] is False
    first_bad = flags.index(False)
    assert not any(flags[first_bad:])

    # Inlet O2 mole fraction: air is the bit-exact default; pure O2 lifts C*_gas.
    for d in do_grid:
        assert compute_scale_up_engineering(0.015, 26.0, do_percent=float(d)) == compute_scale_up_engineering(
            0.015, 26.0, do_percent=float(d), o2_mole_fraction=Y_O2_AIR)
    pure = compute_scale_up_engineering(0.015, 26.0, do_percent=85.0, o2_mole_fraction=1.0)
    assert C_STAR_PURE_O2_MMOL_L == pytest.approx(C_STAR_O2_MMOL_L / 0.2095, rel=1e-15)
    assert pure["c_star_gas_mmol_L"] == pytest.approx(C_STAR_PURE_O2_MMOL_L, abs=5e-5)
    assert pure["otr_mmol_L_h"] == pytest.approx(round(20.0 * (C_STAR_PURE_O2_MMOL_L - 0.85 * C_STAR_O2_MMOL_L), 2), abs=0.011)
    assert pure["oxygen_sufficient"] is True

    # Hypoxia factor: exactly 1.0 from 15 % DO_real, C0-continuous and monotone below.
    assert do_hypoxia_factor(15.0) == 1.0 and do_hypoxia_factor(100.0) == 1.0
    assert abs(do_hypoxia_factor(15.0) - do_hypoxia_factor(14.99)) < 1e-3
    assert do_hypoxia_factor(10.0) == pytest.approx((10 / 11.5) / (15 / 16.5), rel=1e-12)
    assert do_hypoxia_factor(0.0) == 0.0
    grid = [0.1 * k for k in range(151)]
    values = [do_hypoxia_factor(d) for d in grid]
    assert all(b >= a for a, b in zip(values, values[1:]))

    # Quasi-steady O2 balance at Xv 5.8e6 cells/mL, kLa 10 h^-1, DO_sp 85 %.
    air = compute_dissolved_oxygen_state(5.8, 85.0, 10.0, o2_enrichment_enabled=False)
    assert air["c_l_actual_mmol_L"] == pytest.approx(0.210 - 0.058, rel=1e-12)
    assert air["do_real_pct"] == pytest.approx(100 * 0.152 / 0.210, rel=1e-12)
    assert air["do_controller_saturated"] is True and air["f_do"] == 1.0
    assert air["required_y_o2"] > Y_O2_AIR
    enriched = compute_dissolved_oxygen_state(5.8, 85.0, 10.0, o2_enrichment_enabled=True)
    assert enriched["do_real_pct"] == pytest.approx(85.0, rel=1e-12)
    assert enriched["do_controller_saturated"] is False
    assert enriched["required_y_o2"] == pytest.approx(air["required_y_o2"], rel=1e-12)

    air_limit_xv = (C_STAR_O2_MMOL_L * (1 - 0.15)) * 10.0 / 0.1  # DO_real reaches 15 % (kLa 10, qO2 0.1 pmol/cell/h)
    for mode in ("static", "closed_loop"):
        sat = simulate_cho_fed_batch(ProcessDescription(mode=mode, do_setpoint_pct=85.0, o2_enrichment_enabled=False))
        do_real = np.asarray(sat["do_real_pct"])
        f_do = np.asarray(sat["f_do_metabolic"])
        saturated = np.asarray(sat["do_controller_saturated"])
        xv = np.asarray(sat["vcd"])
        assert sat["do_controller_saturated_any"] is True
        window = (do_real >= 55.0) & (do_real <= 75.0)
        assert window.any() and saturated[window].all() and np.all(f_do[window] == 1.0), mode
        assert np.all(f_do[do_real >= 15.0] == 1.0), mode
        assert np.all(xv[do_real < 15.0] > air_limit_xv - 1e-9), mode

        e30 = simulate_cho_fed_batch(ProcessDescription(mode=mode, do_setpoint_pct=30.0))
        e85 = simulate_cho_fed_batch(ProcessDescription(mode=mode, do_setpoint_pct=85.0))
        for run, sp in ((e30, 30.0), (e85, 85.0)):
            assert run["do_controller_saturated_any"] is False
            assert np.allclose(run["do_real_pct"], sp, rtol=0, atol=1e-9)
            assert all(f == 1.0 for f in run["f_do_metabolic"])
            assert run["peak_vcd"] > 20.0
            assert Y_O2_AIR < run["max_required_y_o2"] <= 1.0
        assert e85["final_titer_g_L"] == e30["final_titer_g_L"], mode
        assert sat["final_titer_g_L"] < e30["final_titer_g_L"], mode

        # Real hypoxia: DO_sp 5 % held by the controller (DO_real < 10 %).
        hyp = simulate_cho_fed_batch(ProcessDescription(mode=mode, do_setpoint_pct=5.0))
        assert np.allclose(hyp["do_real_pct"], 5.0, rtol=0, atol=1e-9)
        assert all(f == pytest.approx(do_hypoxia_factor(5.0), rel=1e-12) for f in hyp["f_do_metabolic"])
        assert hyp["peak_lactate_g_L"] > e30["peak_lactate_g_L"], mode
        assert hyp["final_titer_g_L"] < e30["final_titer_g_L"], mode
        assert hyp["peak_vcd"] < e30["peak_vcd"], mode
        # Critical (air-limited) O2 transfer also reaches DO_real < 10 % at high density.
        air30 = simulate_cho_fed_batch(ProcessDescription(mode=mode, do_setpoint_pct=30.0, o2_enrichment_enabled=False))
        assert air30["min_do_real_pct"] < 10.0 and air30["min_f_do_metabolic"] < 1.0, mode
        assert air30["final_titer_g_L"] < e30["final_titer_g_L"], mode


def test_oq_07_fft_nyquist_sampling_validation():
    """FFT/Nyquist: a 2.9 cph fridge signal is resolved at 5 min, aliased if coarser.

    The FFT is always computed on the base 5-min air-temperature trace. A realistic
    refrigerator compressor cycling at 2.9 cycles/hour (Rusnack, Pharm. Eng. 2026)
    is well resolved by 5-min sampling (base Nyquist 6.0 cph > 2.9), but any coarser
    candidate monitor interval (15, 30, 60 min -> target Nyquist 2.0, 1.0, 0.5 cph,
    all <= 2.9 cph) must raise the aliasing-risk flag.
    """
    # Realistic fridge signal: 24 h at 5-min resolution, compressor at 2.9 cph.
    dt_base_min = 5.0
    n = int(24.0 * 60 / dt_base_min)  # 24 hours of 5-min samples
    t_min = np.arange(n) * dt_base_min
    fridge_5min = 5.0 + 2.0 * np.sin(2.0 * np.pi * 2.9 * (t_min / 60.0))

    # Target 5.0 min: Nyquist 6.0 cph > 2.9 cph -> no aliasing, signal resolved.
    resolved = analyze_fft_nyquist(
        list(fridge_5min), target_sampling_interval_min=5.0
    )
    assert resolved["true_dominant_freq_cph"] == pytest.approx(2.9, abs=0.15)
    assert resolved["target_nyquist_cph"] == pytest.approx(6.0, abs=0.01)
    assert resolved["aliasing_risk"] is False

    # Coarser candidate intervals all alias the 2.9 cph compressor signal.
    # General baseband folding |f - fs*round(f/fs)| with fs = 60/target_min, using
    # the FFT-measured peak. 24 h at 5 min (N=288) gives a bin width of
    # 1/24 = 0.0417 cph; the peak falls in bin 70 -> 2.9167 cph, so the expected
    # aliases are ~1.08 / 0.92 / 0.08 cph at 15 / 30 / 60 min.
    for target_min, expected_nyquist in ((15.0, 2.0), (30.0, 1.0), (60.0, 0.5)):
        res = analyze_fft_nyquist(
            list(fridge_5min), target_sampling_interval_min=target_min
        )
        assert res["target_nyquist_cph"] == pytest.approx(expected_nyquist, abs=0.01)
        assert res["aliasing_risk"] is True
        f_dom = res["true_dominant_freq_cph"]
        assert f_dom == pytest.approx(2.9, abs=0.05)
        fs = 60.0 / target_min
        expected = abs(f_dom - fs * round(f_dom / fs))
        assert res["folded_alias_freq_cph"] == pytest.approx(expected, abs=0.03)


def test_oq_08_gorsky_spc_tolerance_and_capability():
    """Gorsky (2020) SPC: ISO 16269 tolerance interval and ASTM E2281 capability."""
    tol = compute_iso16269_tolerance_interval(
        GORSKY_TABLE_6_1_TORQUE_N10, k_factor=3.394
    )
    assert tol["mean"] == pytest.approx(8.46, abs=0.01)
    assert tol["std"] == pytest.approx(1.95, abs=0.01)
    assert tol["lower_tolerance"] == pytest.approx(1.84, abs=0.01)
    assert tol["upper_tolerance"] == pytest.approx(15.08, abs=0.01)

    cap = compute_process_capability(GORSKY_TABLE_6_2_TORQUE_N30, lsl=5.0, usl=12.0)
    # Overall (Pp/Ppk) indices vs Gorsky Table 6.2 (n=30): Ppk 0.51.
    assert cap["ppk"] == pytest.approx(0.51, abs=0.01)
    # Backward-compatible cpk = round(ppk, 2).
    assert cap["cpk"] == pytest.approx(0.51, abs=0.01)
    # Within (Cp/Cpk) moving-range short-term capability. 0.42 is the reference
    # value in Gorsky Fig. 6.5 (p.130); 0.43 is the value this repo computes from
    # the Table 6-2 data. The assertion tolerance is +/-0.03.
    assert cap["cpk_within"] == pytest.approx(0.42, abs=0.03)
    assert cap["capable_4sigma"] is False
    # Shapiro-Wilk: the n=30 torque dataset is approximately normal (p ~ 0.24).
    assert cap["is_normal"] is True


def test_oq_08b_spc_control_stability_and_tost_equivalence():
    """I-MR Rule 1 stability before capability, and formal TOST + Levene equivalence (Gorsky p.131).

    Gorsky Table 6-2 has no point outside the within limits, is normal and therefore meets
    the capability assumptions; a drifting process that still passes Shapiro-Wilk fails
    Rule 1. TOST (two one-sided Welch tests) is recomputed independently with scipy.stats.t
    and agrees with its 90 % confidence interval: groups that a Welch t-test calls
    different can still be equivalent within a wider margin. Levene rejects equivalence when
    the spreads differ even if the means are equivalent.
    """
    cap = compute_process_capability(GORSKY_TABLE_6_2_TORQUE_N30, lsl=5.0, usl=12.0)
    data = np.asarray(GORSKY_TABLE_6_2_TORQUE_N30)
    mr_bar = np.mean(np.abs(np.diff(data)))
    ucl, lcl = data.mean() + 3 * mr_bar / 1.128, data.mean() - 3 * mr_bar / 1.128
    assert cap["n_out_of_control_points"] == int(np.sum((data > ucl) | (data < lcl))) == 0
    assert cap["in_statistical_control"] is True
    assert cap["capability_assumptions_met"] is True
    assert cap["ppk"] == pytest.approx(0.51, abs=0.01)  # existing keys unchanged

    drift = [round(5.0 + 0.25 * i, 2) for i in range(30)]
    drift_cap = compute_process_capability(drift, lsl=5.0, usl=12.0)
    assert drift_cap["is_normal"] is True
    assert drift_cap["n_out_of_control_points"] > 0
    assert drift_cap["in_statistical_control"] is False
    assert drift_cap["capability_assumptions_met"] is False

    a = [8.1, 7.9, 8.4, 8.0, 8.3, 7.8]
    b = [8.6, 8.9, 9.1, 8.7, 9.0, 8.8]
    assert compare_bioreactor_equivalence_ttest(a, b)["statistically_significant_diff"] is True
    for margin, expected in ((0.5, False), (1.0, True)):
        res = compare_bioreactor_equivalence_tost(a, b, equiv_margin=margin)
        xa, xb = np.asarray(a), np.asarray(b)
        va, vb = xa.var(ddof=1) / xa.size, xb.var(ddof=1) / xb.size
        se = np.sqrt(va + vb)
        df = (va + vb) ** 2 / (va ** 2 / (xa.size - 1) + vb ** 2 / (xb.size - 1))
        d = xa.mean() - xb.mean()
        p_lower = stats.t.sf((d + margin) / se, df)
        p_upper = stats.t.cdf((d - margin) / se, df)
        assert res["p_tost"] == pytest.approx(max(p_lower, p_upper), rel=1e-12)
        half = stats.t.ppf(0.95, df) * se
        assert res["ci_90_low"] == pytest.approx(d - half, rel=1e-12)
        assert res["ci_90_high"] == pytest.approx(d + half, rel=1e-12)
        assert res["means_equivalent"] is expected
        assert res["ci_within_margin"] is expected
        assert res["levene_p_value"] == pytest.approx(stats.levene(a, b).pvalue, rel=1e-12)
        assert res["variances_compatible"] is True
        assert res["statistically_equivalent"] is expected

    tight = [8.0, 8.1, 7.9, 8.0, 8.1, 7.9, 8.0, 8.05]
    spread = [6.5, 9.5, 7.0, 9.0, 6.8, 9.2, 8.0, 8.0]
    res = compare_bioreactor_equivalence_tost(tight, spread, equiv_margin=2.0)
    assert res["means_equivalent"] is True
    assert res["variances_compatible"] is False
    assert res["statistically_equivalent"] is False

    for bad in (dict(equiv_margin=0.0), dict(equiv_margin=1.0, alpha=0.6)):
        with pytest.raises(ValueError):
            compare_bioreactor_equivalence_tost(a, b, **bad)
    with pytest.raises(ValueError):
        compare_bioreactor_equivalence_tost([8.0], b, equiv_margin=1.0)


def test_oq_09_part11_audit_trail_and_annex22_guardrail():
    """Part 11 / Annex 22: human-in-the-loop guardrail and tamper evidence."""
    logger = AuditTrailLogger()

    # Annex 22 human-in-the-loop guardrail: no AI change without human approval.
    with pytest.raises(PermissionError):
        logger.append_record(
            user_id="twin-ai",
            role="DigitalTwin",
            parameter_name="ph_setpoint",
            old_value="7.00",
            new_value="6.90",
            reason_for_change="Autonomous optimization adjustment",
            human_approved=False,
        )

    # A valid, human-approved record forms an intact hash chain.
    logger.append_record(
        user_id="jdoe",
        role="ProcessEngineer",
        parameter_name="ph_setpoint",
        old_value="7.00",
        new_value="7.05",
        reason_for_change="Documented CPP adjustment per deviation DN-042",
        human_approved=True,
    )
    assert logger.verify_chain_integrity() is True

    # Tampering with a stored record breaks the chain (tamper evidence).
    logger.records[0]["new_value"] = "9.99"
    assert logger.verify_chain_integrity() is False


def test_oq_09b_part11_human_approved_mutation_breaks_chain():
    """Part 11: flipping the stored human_approved flag breaks the hash chain."""
    logger = AuditTrailLogger()
    logger.append_record(
        user_id="jdoe",
        role="ProcessEngineer",
        parameter_name="ph_setpoint",
        old_value="7.00",
        new_value="7.05",
        reason_for_change="Documented CPP adjustment per deviation DN-042",
        human_approved=True,
    )
    assert logger.verify_chain_integrity() is True

    logger.records[0]["human_approved"] = False
    assert logger.verify_chain_integrity() is False


# ---------------------------------------------------------------------------
# UNSCRIPTED / ERROR-GUESSING (Not High Process Risk)
# ---------------------------------------------------------------------------


def test_exploratory_10_invalid_pydantic_inputs():
    """Error-guessing: out-of-range CPPs and inconsistent set-point combinations are rejected.

    v1.4.0: also probes the cross-field validators (glucose trigger below the refill
    target, temperature shift not after the end of the run) and the new fields
    (initial_fill_fraction, max_o2_mole_fraction, mode).
    """
    with pytest.raises(pydantic.ValidationError):
        ProcessDescription(vessel_volume_L=-5.0, ph_setpoint=14.5)
    # Cross-field: trigger must be strictly below the target.
    for g_min, g_target in ((5.0, 5.0), (6.0, 5.0), (10.0, 2.0)):
        with pytest.raises(pydantic.ValidationError, match="glucose_min_threshold_g_L"):
            ProcessDescription(glucose_min_threshold_g_L=g_min, glucose_refill_target_g_L=g_target)
    assert ProcessDescription(glucose_min_threshold_g_L=4.99, glucose_refill_target_g_L=5.0)
    # Cross-field: the shift cannot be scheduled after the end of the run.
    for shift, duration in ((7.5, 7), (14.0, 5), (10.0, 9)):
        with pytest.raises(pydantic.ValidationError, match="temp_shift_day"):
            ProcessDescription(temp_shift_day=shift, duration_days=duration)
    assert ProcessDescription(temp_shift_day=5.0, duration_days=5).temp_shift_day == 5.0
    # New fields: bounds and literal values.
    for bad in (
        dict(initial_fill_fraction=0.19), dict(initial_fill_fraction=0.96),
        dict(max_o2_mole_fraction=0.20), dict(max_o2_mole_fraction=1.01),
        dict(mode="perfusion"), dict(do_setpoint_pct=4.9),
    ):
        with pytest.raises(pydantic.ValidationError):
            ProcessDescription(**bad)
    cfg = ProcessDescription()
    assert (cfg.initial_fill_fraction, cfg.o2_enrichment_enabled, cfg.max_o2_mole_fraction) == (0.70, True, 1.0)


def test_exploratory_11_audit_trail_requires_reason():
    """Error-guessing: a missing/too-short reason for change is rejected."""
    logger = AuditTrailLogger()
    with pytest.raises(ValueError):
        logger.append_record(
            user_id="jdoe",
            role="ProcessEngineer",
            parameter_name="ph_setpoint",
            old_value="7.00",
            new_value="7.05",
            reason_for_change="ok",  # shorter than 5 chars after strip
            human_approved=True,
        )


def test_exploratory_12_welch_ttest_identical_groups_not_significant():
    """Error-guessing: Welch's t-test on identical groups is not significant."""
    group = [8.1, 8.2, 8.3, 8.0, 8.4]
    result = compare_bioreactor_equivalence_ttest(group, list(group), alpha=0.05)
    assert result["statistically_significant_diff"] is False
    assert result["p_value"] == pytest.approx(1.0, abs=1e-9)
