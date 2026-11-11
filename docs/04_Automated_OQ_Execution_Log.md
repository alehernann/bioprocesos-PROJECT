# Automated OQ Execution Log

FDA Computer Software Assurance (CSA) Operational Qualification (OQ) automated execution record.

> This document is GENERATED automatically by `tests/conftest.py` on every `pytest` run. Do not edit it by hand.

## Execution Environment

- **Execution timestamp (UTC):** 2026-11-11 19:27:27 UTC
- **Python version:** 3.11.15
- **Platform:** Linux-6.1.189-236.400.amzn2023.x86_64-x86_64-with-glibc2.34
- **Qualified package versions:**
    - numpy: 2.4.6
    - scipy: 1.17.1
    - pandas: 3.1.1
    - pydantic: 2.14.3
    - plotly: 7.1.0
    - streamlit: 1.67.0
    - pytest: 9.2.0

## Execution Summary

- **Total tests executed:** 20
- **Passed:** 20
- **Failed:** 0
- **Errored:** 0
- **Skipped:** 0
- **Pytest exit status:** 0

## Test Results

| ID | CSA Category | Result | Duration (s) |
| --- | --- | --- | --- |
| tests/test_csa_oq_validation.py::test_oq_01_setpoints_and_ph_split_range_exclusivity | Scripted Testing (High Process Risk) | PASSED | 0.0008 |
| tests/test_csa_oq_validation.py::test_oq_02_automated_day7_temperature_shift | Scripted Testing (High Process Risk) | PASSED | 0.0018 |
| tests/test_csa_oq_validation.py::test_oq_03_closed_loop_vs_static_titer_gain | Scripted Testing (High Process Risk) | PASSED | 0.0030 |
| tests/test_csa_oq_validation.py::test_oq_03b_vessel_capacity_and_bolus_mass_balance | Scripted Testing (High Process Risk) | PASSED | 0.0063 |
| tests/test_csa_oq_validation.py::test_oq_03c_lactate_reconsumption_and_nonnegativity | Scripted Testing (High Process Risk) | PASSED | 0.0040 |
| tests/test_csa_oq_validation.py::test_oq_03d_lactate_profile_v131 | Scripted Testing (High Process Risk) | PASSED | 0.0055 |
| tests/test_csa_oq_validation.py::test_oq_03e_bolus_clipped_alarm | Scripted Testing (High Process Risk) | PASSED | 0.0105 |
| tests/test_csa_oq_validation.py::test_oq_04_safety_shear_and_cip_sip_interlocks | Scripted Testing (High Process Risk) | PASSED | 0.0001 |
| tests/test_csa_oq_validation.py::test_oq_04b_shear_or_gate_and_continuous_penalty | Scripted Testing (High Process Risk) | PASSED | 0.0110 |
| tests/test_csa_oq_validation.py::test_oq_05_ispe_amab_design_space_center_and_edges | Scripted Testing (High Process Risk) | PASSED | 0.0002 |
| tests/test_csa_oq_validation.py::test_oq_05b_amab_scale_up_kla_pilot_commercial_range | Scripted Testing (High Process Risk) | PASSED | 0.0001 |
| tests/test_csa_oq_validation.py::test_oq_06_mkt_and_vtb_damping | Scripted Testing (High Process Risk) | PASSED | 0.0005 |
| tests/test_csa_oq_validation.py::test_oq_06b_do_setpoint_driving_force | Scripted Testing (High Process Risk) | PASSED | 0.0090 |
| tests/test_csa_oq_validation.py::test_oq_07_fft_nyquist_sampling_validation | Scripted Testing (High Process Risk) | PASSED | 0.0005 |
| tests/test_csa_oq_validation.py::test_oq_08_gorsky_spc_tolerance_and_capability | Scripted Testing (High Process Risk) | PASSED | 0.0007 |
| tests/test_csa_oq_validation.py::test_oq_09_part11_audit_trail_and_annex22_guardrail | Scripted Testing (High Process Risk) | PASSED | 0.0001 |
| tests/test_csa_oq_validation.py::test_oq_09b_part11_human_approved_mutation_breaks_chain | Scripted Testing (High Process Risk) | PASSED | 0.0001 |
| tests/test_csa_oq_validation.py::test_exploratory_10_invalid_pydantic_inputs | Unscripted / Error-Guessing (Not High Process Risk) | PASSED | 0.0001 |
| tests/test_csa_oq_validation.py::test_exploratory_11_audit_trail_requires_reason | Unscripted / Error-Guessing (Not High Process Risk) | PASSED | 0.0001 |
| tests/test_csa_oq_validation.py::test_exploratory_12_welch_ttest_identical_groups_not_significant | Unscripted / Error-Guessing (Not High Process Risk) | PASSED | 0.0011 |

## Acceptability Statement (FDA CSA Section V.A.6)

In accordance with the FDA guidance *Computer Software Assurance for Production and Quality System Software*, Section V.A.6, this automated OQ execution constitutes objective evidence that the software performs as intended for its risk-based use. The scripted high-process-risk tests (`test_oq_*`) and the unscripted / error-guessing tests (`test_exploratory_*`) above, together with their recorded results and durations, document the assurance activities performed.

Based on the results recorded in this log, the OQ execution results are declared **ACCEPTABLE** per FDA CSA Section V.A.6: the testing provides objective evidence that the results are acceptable for the intended, risk-assessed use of the system.
