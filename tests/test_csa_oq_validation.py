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
"""

import numpy as np
import pydantic
import pytest

from src.amab_design_space import evaluate_amab_design_space
from src.audit_trail_part11 import AuditTrailLogger
from src.bioreactor_twin import (
    check_safety_interlocks,
    compute_split_range_ph_actuators,
    get_temperature_setpoint,
    simulate_cho_fed_batch,
)
from src.models import ProcessDescription
from src.spc_six_sigma import (
    GORSKY_TABLE_6_1_TORQUE_N10,
    GORSKY_TABLE_6_2_TORQUE_N30,
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


def test_oq_01_pid_split_range_deadband():
    """Split-range pH control: deadband dead-zone and single-actuator response."""
    # Inside the deadband (setpoint 7.00 +/- 0.20) both actuators must rest at 0.0.
    for ph in (7.00, 6.85, 7.15):
        out = compute_split_range_ph_actuators(ph)
        assert out["co2_valve_pct"] == pytest.approx(0.0, abs=1e-9)
        assert out["base_pump_pct"] == pytest.approx(0.0, abs=1e-9)

    # Above the band: only the CO2 (acidifying) valve engages.
    high = compute_split_range_ph_actuators(7.35)
    assert high["co2_valve_pct"] > 0.0
    assert high["base_pump_pct"] == pytest.approx(0.0, abs=1e-9)

    # Below the band: only the base pump engages.
    low = compute_split_range_ph_actuators(6.65)
    assert low["base_pump_pct"] > 0.0
    assert low["co2_valve_pct"] == pytest.approx(0.0, abs=1e-9)


def test_oq_02_automated_day7_temperature_shift():
    """Biphasic temperature-shift schedule crosses at shift_day = 7.0."""
    assert get_temperature_setpoint(6.9) == pytest.approx(36.5, abs=1e-9)
    assert get_temperature_setpoint(7.0) == pytest.approx(34.0, abs=1e-9)


def test_oq_03_closed_loop_vs_static_titer_gain():
    """Closed-loop feeding gains >= +35% titer and holds glucose above threshold."""
    static = simulate_cho_fed_batch(ProcessDescription(mode="static"))
    closed = simulate_cho_fed_batch(ProcessDescription(mode="closed_loop"))

    gain_pct = (
        (closed["final_titer_g_L"] - static["final_titer_g_L"])
        / static["final_titer_g_L"]
        * 100.0
    )
    assert gain_pct >= 35.0

    # In closed_loop, glucose must stay above the critical minimum threshold after
    # each adaptive feed. Inspect the glucose series at every feed-day crossing.
    config = ProcessDescription(mode="closed_loop")
    threshold = config.glucose_min_threshold_g_L
    time_days = closed["time_days"]
    glucose = closed["glucose_g_L"]
    for feed_day in (2.0, 4.0, 6.0, 8.0, 10.0, 12.0):
        idx = time_days.index(feed_day)
        assert glucose[idx] >= threshold, (
            f"glucose {glucose[idx]:.3f} below threshold {threshold} "
            f"after feed day {feed_day}"
        )


def test_oq_04_safety_shear_and_cip_sip_interlocks():
    """GxP safety interlocks: shear alarm, CIP block, CIP velocity, SIP sterility."""
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


def test_oq_06_mkt_and_vtb_damping():
    """MKT of an isothermal trace equals the temperature; bulk VTB damps more."""
    assert calculate_mkt_celsius([5.0] * 288) == pytest.approx(5.0, abs=0.01)

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


def test_oq_07_fft_nyquist_sampling_validation():
    """FFT/Nyquist: adequate sampling resolves a signal; coarse sampling aliases."""
    # 5-min sampling -> Nyquist 6.0 cph; a 2.9 cph compressor signal is well resolved.
    interval_fast = 5.0
    n_fast = int(4.0 * 60 / interval_fast)  # 4 hours
    t_fast_min = np.arange(n_fast) * interval_fast
    sig_fast = 5.0 + 2.0 * np.sin(2.0 * np.pi * 2.9 * (t_fast_min / 60.0))
    fast = analyze_fft_nyquist(list(sig_fast), sampling_interval_min=interval_fast)
    assert fast["nyquist_limit_cph"] == pytest.approx(6.0, abs=0.01)
    assert fast["aliasing_risk"] is False

    # 30-min sampling -> Nyquist 1.0 cph; a ~0.95 cph component is at/above the
    # effective Nyquist band and must raise the aliasing-risk flag.
    interval_slow = 30.0
    n_slow = int(24.0 * 60 / interval_slow)  # 24 hours
    t_slow_min = np.arange(n_slow) * interval_slow
    sig_slow = 5.0 + 2.0 * np.sin(2.0 * np.pi * 0.95 * (t_slow_min / 60.0))
    slow = analyze_fft_nyquist(list(sig_slow), sampling_interval_min=interval_slow)
    assert slow["nyquist_limit_cph"] == pytest.approx(1.0, abs=0.01)
    assert slow["aliasing_risk"] is True


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
    assert cap["cpk"] == pytest.approx(0.51, abs=0.01)
    assert cap["capable_4sigma"] is False


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


# ---------------------------------------------------------------------------
# UNSCRIPTED / ERROR-GUESSING (Not High Process Risk)
# ---------------------------------------------------------------------------


def test_exploratory_10_invalid_pydantic_inputs():
    """Error-guessing: out-of-range CPPs must be rejected by the schema."""
    with pytest.raises(pydantic.ValidationError):
        ProcessDescription(vessel_volume_L=-5.0, ph_setpoint=14.5)


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
