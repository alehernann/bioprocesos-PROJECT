# 03 — Requirements Traceability Matrix (RTM)

| Field | Value |
|-------|-------|
| **Document ID** | RTM-BRX-001 |
| **Title** | Requirements Traceability Matrix — CHO-K1 Fed-Batch Bioreactor Control System |
| **Version** | 1.0 |
| **Traces From** | `01_URS_Bioreactor_Control_System.md` (URS-01 … URS-15) |
| **Risk Source** | `02_FDA_CSA_Risk_Assessment_2026.md` |
| **Traces To** | `src/*.py` modules and `tests/test_csa_oq_validation.py` OQ tests |

---

## 1. Purpose

This Requirements Traceability Matrix (RTM) establishes **bidirectional traceability** between
every User Requirement (URS-01 to URS-15), the **source module** in `src/` that implements it, the
**CSA process-risk level** assigned in document 02, and the **Operational Qualification (OQ) test**
in `tests/test_csa_oq_validation.py` that provides objective evidence of compliance.

The RTM is the backbone of the validation package: it proves that (a) every requirement is
implemented and tested (no **orphan requirements**), and (b) every test traces back to a
requirement (no **orphan tests**).

## 2. Source Modules (`src/`)

| Module | Responsibility |
|--------|----------------|
| `models.py` | Strongly-typed Pydantic data models and input validation. |
| `bioreactor_twin.py` | Temperature set-point schedule, pH split-range, adaptive feed / fed-batch simulation and safety interlocks (shear, CIP, SIP). |
| `amab_design_space.py` | ISPE A-Mab Design Space center-point and edge-of-failure equations; kLa / OTR / OUR scale-up engineering. |
| `thermal_vtb_mkt.py` | Mean Kinetic Temperature and Validated Thermal Buffer damping. |
| `spc_six_sigma.py` | Statistical Process Control, tolerance intervals and process capability (Cpk). |
| `audit_trail_part11.py` | 21 CFR Part 11 compliant, tamper-evident audit trail. |

## 3. OQ Test Suite (`tests/test_csa_oq_validation.py`)

| Test ID | Scope |
|---------|-------|
| `test_oq_01_setpoints_and_ph_split_range_exclusivity` | Validated set-points (T, pH, DO), pH split-range dead-band and mutual exclusivity, OTR ≥ OUR. |
| `test_oq_02_automated_day7_temperature_shift` | Automated 36.5 °C → 34.0 °C shift at day 7.0. |
| `test_oq_03_closed_loop_vs_static_titer_gain` | Adaptive glucose top-up (trigger, V_gluc > 0), lactate consumption, directional titer/viability gain vs. static. |
| `test_oq_04_safety_shear_and_cip_sip_interlocks` | Shear alarm (P/V > 47.6 W/m³ AND sparge > 0.15 vvm), CIP velocity, SIP F0 interlocks. |
| `test_oq_05_ispe_amab_design_space_center_and_edges` | Design Space center point and edges of failure. |
| `test_oq_05b_amab_scale_up_kla_pilot_commercial_range` | A-Mab scale-up kLa over the pilot/commercial range. |
| `test_oq_06_mkt_and_vtb_damping` | MKT computation and VTB thermal damping. |
| `test_oq_07_fft_nyquist_sampling_validation` | FFT / Nyquist sampling criterion validation. |
| `test_oq_08_gorsky_spc_tolerance_and_capability` | Gorsky SPC tolerance intervals and capability. |
| `test_oq_09_part11_audit_trail_and_annex22_guardrail` | Part 11 audit trail and Annex 22 AI guardrail. |
| `test_oq_09b_part11_human_approved_mutation_breaks_chain` | Part 11 tamper evidence: mutating the stored `human_approved` flag breaks the hash chain. |
| `test_exploratory_10_invalid_pydantic_inputs` | Exploratory / error-guessing on invalid inputs. |
| `test_exploratory_11_audit_trail_requires_reason` | Exploratory / error-guessing: audit-trail entry without a reason. |
| `test_exploratory_12_welch_ttest_identical_groups_not_significant` | Exploratory / error-guessing: Welch t-test on identical groups. |

## 4. Master Traceability Matrix

| URS ID | Requirement (summary) | `src/` Module | CSA Risk Level | OQ Test |
|--------|-----------------------|---------------|----------------|---------|
| **URS-01** | Validated initial temperature set-point 36.5 °C (band delegated to local controller) | `models.py`, `bioreactor_twin.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-02** | Automated day-7 shift 36.5 → 34.0 °C | `bioreactor_twin.py` | High Process Risk | `test_oq_02_automated_day7_temperature_shift` |
| **URS-03** | pH 7.00 ± 0.20 split-range dead-band | `bioreactor_twin.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-04** | pH acid branch via CO2 sparge | `bioreactor_twin.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-05** | pH base branch via 1 M Na2CO3 | `bioreactor_twin.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-06** | DO set-point 30 % and mass-transfer sufficiency OTR ≥ OUR | `models.py`, `amab_design_space.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-07** | Adaptive glucose feed < 2.0 → 5.0 g/L | `bioreactor_twin.py` | High Process Risk | `test_oq_03_closed_loop_vs_static_titer_gain` |
| **URS-08** | Closed-loop titer and viability advantage vs static (emergent gain, no fixed band) | `bioreactor_twin.py` | High Process Risk | `test_oq_03_closed_loop_vs_static_titer_gain` |
| **URS-09** | Shear interlock: `high_shear_alarm` when `power_density_W_m3` > 47.6 W/m³ AND `sparge_vvm` > 0.15 vvm | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-10** | Shear interlock scale translation | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-11** | CIP velocity interlock ≥ 1.52 m/s (ASME BPE) | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-12** | SIP F0 ≥ 15 min at ≥ 121.1 °C | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-13** | A-Mab Design Space center/edges | `amab_design_space.py` | High Process Risk | `test_oq_05_ispe_amab_design_space_center_and_edges` |
| **URS-13** | A-Mab scale-up kLa pilot/commercial range | `amab_design_space.py` | High Process Risk | `test_oq_05b_amab_scale_up_kla_pilot_commercial_range` |
| **URS-14** | MKT and VTB thermal damping | `thermal_vtb_mkt.py` | High Process Risk | `test_oq_06_mkt_and_vtb_damping` |
| **URS-15** | Part 11 Audit Trail + SPC capability | `audit_trail_part11.py`, `spc_six_sigma.py` | High Process Risk | `test_oq_09_part11_audit_trail_and_annex22_guardrail`, `test_oq_08_gorsky_spc_tolerance_and_capability` |
| **URS-15** | Part 11 Audit Trail: `human_approved` is hash-protected (tamper evidence) | `audit_trail_part11.py` | High Process Risk | `test_oq_09b_part11_human_approved_mutation_breaks_chain` |
| **URS-15** | Part 11 Audit Trail requires a reason | `audit_trail_part11.py` | Exploratory / Error-Guessing | `test_exploratory_11_audit_trail_requires_reason` |
| **URS-15** | Welch t-test on identical groups is not significant | `spc_six_sigma.py` | Exploratory / Error-Guessing | `test_exploratory_12_welch_ttest_identical_groups_not_significant` |

## 5. Reverse Traceability (Test → Requirement)

| OQ Test | Covers URS | `src/` Module(s) | CSA Risk |
|---------|-----------|------------------|----------|
| `test_oq_01_setpoints_and_ph_split_range_exclusivity` | URS-01, URS-03, URS-04, URS-05, URS-06 | `models.py`, `bioreactor_twin.py`, `amab_design_space.py` | High |
| `test_oq_02_automated_day7_temperature_shift` | URS-02 | `bioreactor_twin.py` | High |
| `test_oq_03_closed_loop_vs_static_titer_gain` | URS-07, URS-08 | `bioreactor_twin.py` | High |
| `test_oq_04_safety_shear_and_cip_sip_interlocks` | URS-09, URS-10, URS-11, URS-12 | `bioreactor_twin.py` | High |
| `test_oq_05_ispe_amab_design_space_center_and_edges` | URS-13 | `amab_design_space.py` | High |
| `test_oq_05b_amab_scale_up_kla_pilot_commercial_range` | URS-13 | `amab_design_space.py` | High |
| `test_oq_06_mkt_and_vtb_damping` | URS-14 | `thermal_vtb_mkt.py` | High |
| `test_oq_07_fft_nyquist_sampling_validation` | NFR-03 (Nyquist sampling) | `thermal_vtb_mkt.py` | High |
| `test_oq_08_gorsky_spc_tolerance_and_capability` | URS-15 (SPC/Cpk) | `spc_six_sigma.py` | High |
| `test_oq_09_part11_audit_trail_and_annex22_guardrail` | URS-15 (Audit Trail) | `audit_trail_part11.py` | High |
| `test_oq_09b_part11_human_approved_mutation_breaks_chain` | URS-15 (Audit Trail) | `audit_trail_part11.py` | High |
| `test_exploratory_10_invalid_pydantic_inputs` | NFR-02, NFR-04 (validation) | `models.py` | High (guard) / exploratory |
| `test_exploratory_11_audit_trail_requires_reason` | URS-15 (Audit Trail) | `audit_trail_part11.py` | Exploratory / Error-Guessing |
| `test_exploratory_12_welch_ttest_identical_groups_not_significant` | URS-15 (SPC) | `spc_six_sigma.py` | Exploratory / Error-Guessing |

## 6. Coverage Analysis

| Metric | Result |
|--------|--------|
| User requirements defined | 15 (URS-01 … URS-15) |
| Requirements traced to a module | 15 / 15 (100 %) |
| Requirements traced to an OQ test | 15 / 15 (100 %) |
| Orphan requirements (no test) | 0 |
| Orphan tests (no requirement) | 0 |
| High Process Risk requirements | 15 / 15 |
| OQ tests executed | 14 |
| Scripted tests (High Process Risk) | 11 (`test_oq_01` … `test_oq_09`, incl. `test_oq_05b` and `test_oq_09b`) |
| Unscripted Exploratory / Error-Guessing tests | 3 (`test_exploratory_10` … `test_exploratory_12`) |

**Note on `test_oq_07_fft_nyquist_sampling_validation`:** this test verifies the non-functional
Nyquist sampling criterion (NFR-03) that underpins faithful signal reconstruction for the control
and monitoring loops. It is retained as a High-Risk scripted test because aliasing in sampled
process signals could silently corrupt control and SPC decisions.

**Note on `test_exploratory_10_invalid_pydantic_inputs`:** this test exercises the input-validation
guard (`models.py`) with malformed/invalid inputs. While input validation itself is High Process
Risk (gatekeeper to the core), the *exploration of invalid inputs* is conducted as an
unscripted/error-guessing activity consistent with the CSA least-burdensome principle.

**Note on `test_exploratory_10`, `test_exploratory_11` and `test_exploratory_12`:** these three
tests are error-guessing / boundary-probing activities under the least-burdensome principle of the
FDA CSA guidance (Feb 2026). They complement, and do not replace, the scripted tests on
`models.py` (invalid CPP inputs), `audit_trail_part11.py` (missing or too-short reason for change)
and `spc_six_sigma.py` (Welch t-test on identical groups).

## 7. Per-Requirement Verification Detail

The table below expands each requirement with its acceptance criterion and the objective evidence
the mapped OQ test must produce. This provides the reviewer with a direct line of sight from the
requirement statement to the pass/fail evidence.

| URS ID | Acceptance Criterion | Objective Evidence Produced by OQ |
|--------|----------------------|-----------------------------------|
| URS-01 | Default initial temperature set-point is 36.5 °C (`temp_initial_C`, `get_temperature_setpoint(0.0)`). | Set-point value assertions. |
| URS-02 | Set-point auto-changes 36.5 → 34.0 °C exactly at day 7.0. | Pre/post set-point values and Audit Trail entry. |
| URS-03 | Set-point 7.00 and dead-band 0.20 in `ProcessDescription`; no actuation while pH in 6.80–7.20. | Set-point and dead-band quiescence assertions. |
| URS-04 | CO2 branch active only when pH > 7.20. | Mutual-exclusivity sweep pH 6.00–8.00 (acid branch). |
| URS-05 | Na2CO3 1 M branch active only when pH < 6.80. | Mutual-exclusivity sweep pH 6.00–8.00 (base branch). |
| URS-06 | DO set-point is 30 %; OTR ≥ OUR at the corners Vs 0.005–0.017 m/s × P/V 19–30 W/m³. | Set-point assertion and OTR ≥ OUR / `oxygen_sufficient` assertions. |
| URS-07 | Glucose falls below 2.0 g/L, stays ≤ 6.5 g/L, is ≥ 2.0 g/L after each feed, and the top-up fires (closed-loop feed volume > basal-bolus volume). | min/max glucose, post-feed recovery and feed-volume assertions; final lactate < peak lactate. Measured (v1.2.0, closed_loop): min G 0.7241 g/L, max G 6.0 g/L, peak L 1.0001 g/L, final L 0.6498 g/L. |
| URS-08 | Closed-loop final titer and final viability > static baseline (directional; gain not banded). | Comparative titer and viability assertions. Measured (v1.2.0): titer 1.1654 vs 1.0164 g/L (emergent gain +14.66 %), viability 91.56 vs 81.17 %. |
| URS-09 | `high_shear_alarm` fires only when `power_density_W_m3` > 47.6 W/m³ AND `sparge_vvm` > 0.15 vvm. | Boundary-crossing alarm assertion. |
| URS-10 | P/V limit evaluated with scale geometry 0.25 L–15,000 L. | Multi-scale consistency assertion. |
| URS-11 | CIP aborts when velocity < 1.52 m/s. | Interlock/abort assertion. |
| URS-12 | SIP releases only when F0 ≥ 15 min at ≥ 121.1 °C. | Lethality accumulation and release-gate assertion. |
| URS-13 | Center point inside, edges flagged outside Design Space. | Center/edge classification assertion. |
| URS-14 | MKT computed; VTB damping reduces excursion amplitude. | Reference-dataset MKT value assertion. |
| URS-15 | Audit entries attributable, time-stamped, tamper-evident (including the `human_approved` flag); Cpk computed. | Record-integrity, `human_approved` mutation and capability assertions. |

## 8. Risk-to-Assurance Summary

All 15 user requirements are classified **High Process Risk** per
`02_FDA_CSA_Risk_Assessment_2026.md` and are therefore verified through **Robust Scripted Testing**.
No user requirement in this system falls into the Not-High-Risk category; the Not-High-Risk
features (plotting, UI) are presentation-layer functions that do not map to a URS and are assured
by unscripted exploratory / error-guessing testing, as documented in section 5.2 of document 02.
In addition, `test_exploratory_10`, `test_exploratory_11` and `test_exploratory_12` are
error-guessing / boundary-probing activities under the least-burdensome principle of the FDA CSA
guidance (Feb 2026); they complement the scripted tests on `models.py`, `audit_trail_part11.py`
and `spc_six_sigma.py` without replacing them.

## 9. Traceability Integrity Statement

- **Forward traceability:** URS → module → risk → test is complete for URS-01 … URS-15.
- **Backward traceability:** every OQ test in `tests/test_csa_oq_validation.py` resolves to at
  least one URS requirement or a documented non-functional requirement (NFR).
- **No orphans:** there are zero orphan requirements and zero orphan tests.
- **Risk alignment:** every High-Risk requirement is paired with a scripted OQ test.

## 10. Change Control

Any modification to a URS requirement, module responsibility, risk classification, or test mapping
must be reflected in this RTM under formal change control, preserving 100 % bidirectional
traceability. A change that adds a requirement must add the corresponding module mapping, risk
classification and OQ test in the same controlled change. A change that removes or merges a test
must re-confirm that no requirement is left without evidence.

*End of document RTM-BRX-001.*
