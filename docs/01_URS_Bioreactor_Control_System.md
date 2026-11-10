# 01 — User Requirements Specification (URS)
## Bioreactor Control System — CHO-K1 Fed-Batch Digital Twin

| Field | Value |
|-------|-------|
| **Document ID** | URS-BRX-001 |
| **Title** | User Requirements Specification for the CHO-K1 Fed-Batch Bioreactor Control System |
| **Version** | 2.1 |
| **Status** | Approved for Implementation |
| **Regulatory Framework** | GAMP 5 (2nd ed.), ICH Q8(R2)/Q9(R1)/Q10/Q11, FDA CSA (Feb 2026), 21 CFR Part 11, EudraLex Annex 11 |
| **Product** | Monoclonal antibody (A-Mab reference case) expressed in CHO-K1 |
| **Process Type** | Fed-batch, controlled single-use / stainless-steel train |
| **Scale Range** | 0.25 L (Stratyx™ / Ambr®) micro-scale to 15,000 L commercial |

---

### 1. Purpose and Scope

This User Requirements Specification (URS) defines the user, functional, performance,
safety, data-integrity and regulatory requirements for the **Bioreactor Control System**
(hereafter "THE SYSTEM") that governs a **CHO-K1 fed-batch** process for the production of a
monoclonal antibody. THE SYSTEM is implemented as a validated **digital twin** that mirrors the
physical control strategy from bench scale through commercial manufacturing.

The scope spans the full scale continuum: **0.25 L Stratyx™/Ambr® micro-bioreactors** used for
process development and Design-of-Experiments (DoE) characterization, intermediate pilot
vessels, and the **15,000 L commercial** production bioreactor. THE SYSTEM is designed to be
**scale-independent** in its control logic and **scale-aware** in its engineering limits
(hydrodynamic shear, mass transfer, mixing time).

This document is written to be **testable**. Every requirement uses the **EARS** notation
(Easy Approach to Requirements Syntax) in the canonical form:

> **WHEN** [triggering condition], **THE SYSTEM SHALL** [observable system action].

Each requirement is classified according to **GAMP 5** software categories and process-risk
impact, and is traceable through the Requirements Traceability Matrix (RTM, document 03) to a
source module in `src/` and an Operational Qualification (OQ) test in
`tests/test_csa_oq_validation.py`.

### 2. Definitions, Acronyms and Abbreviations

| Term | Definition |
|------|------------|
| **CHO-K1** | Chinese Hamster Ovary K1 cell line, the production host. |
| **Fed-batch** | Cultivation mode where nutrients are fed during the run without medium removal. |
| **PID** | Proportional-Integral-Derivative closed-loop controller. |
| **DO / OD** | Dissolved Oxygen (English DO; Spanish "Oxígeno Disuelto", OD). |
| **P/V** | Volumetric power input (W/m³), a proxy for hydrodynamic shear. |
| **CIP** | Clean-In-Place. |
| **SIP** | Sterilize-In-Place. |
| **F0** | Accumulated lethality (equivalent minutes at 121.1 °C, z = 10 °C). |
| **MKT** | Mean Kinetic Temperature. |
| **GAMP** | Good Automated Manufacturing Practice. |
| **EARS** | Easy Approach to Requirements Syntax. |
| **Split-range** | Control scheme where one controller output drives two final elements. |
| **Dead-band** | Control region where no actuator action is taken. |
| **PAT** | Process Analytical Technology. |
| **CQA** | Critical Quality Attribute. |
| **CPP** | Critical Process Parameter. |

### 3. GAMP 5 Software Categorization

| GAMP Category | Description | Applicability to THE SYSTEM |
|---------------|-------------|------------------------------|
| **Category 1** | Infrastructure software (OS, runtime). | Python runtime, OS — supplier-assessed. |
| **Category 3** | Non-configured COTS. | NumPy, SciPy, Pandas numerical libraries. |
| **Category 4** | Configured products. | Streamlit/Plotly visualization layer (configured UI). |
| **Category 5** | Custom / bespoke software. | Control logic, Design Space, interlocks, Audit Trail — the GxP-critical core. |

Category 5 custom code carries the highest validation rigor and is subject to **Robust
Scripted Testing** per the FDA CSA 2026 guidance (see document 02).

### 4. Regulatory and Standards Basis

- **GAMP 5, 2nd ed. (ISPE, 2022)** — risk-based validation lifecycle.
- **FDA Computer Software Assurance (CSA), Feb 3, 2026** — critical-thinking, risk-based assurance.
- **ICH Q8(R2) / Q9(R1) / Q10 / Q11 / Q12** — QbD, quality risk management, lifecycle.
- **21 CFR Part 11 / EudraLex Annex 11 / Draft Annex 22 (AI)** — electronic records and signatures.
- **ASME BPE-2014** — bioprocessing equipment hygienic design (CIP velocity).
- **ISPE A-Mab Case Study (2009)** — Design Space reference process.

---

## 5. User Requirements (URS-01 to URS-15)

### 5.1 Temperature Set-Point

#### URS-01 — Validated initial temperature set-point
**WHEN** the bioreactor is in the growth phase (culture day < 7.0),
**THE SYSTEM SHALL** issue the validated initial temperature set-point of **36.5 °C**
(`ProcessDescription.temp_initial_C`) to the local temperature controller. Regulation of the
measured temperature within its operational band is delegated to that local controller; THE
SYSTEM does not simulate or qualify a temperature PID loop.
- *GAMP Category:* 5 — *Process Risk:* High — *Modules:* `models.py`, `bioreactor_twin.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`

#### URS-02 — Automated day-7 temperature shift
**WHEN** the culture time reaches **day 7.0**,
**THE SYSTEM SHALL** automatically and without operator intervention change the temperature
set-point from **36.5 °C to 34.0 °C** (temperature-shift / mild hypothermia for productivity),
logging the event to the Audit Trail and completing the ramp within the validated transition window.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_02_automated_day7_temperature_shift`

### 5.2 pH Control Loop (Split-Range with Dead-Band)

#### URS-03 — pH set-point and tolerance
**WHEN** the culture is active,
**THE SYSTEM SHALL** maintain broth pH at **7.00 ± 0.20** (dead-band 6.80–7.20) using a
split-range control strategy, so that no corrective addition occurs while pH remains inside the
dead-band.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`

#### URS-04 — pH acid branch (CO2 sparge)
**WHEN** the measured pH exceeds the upper dead-band limit (**pH > 7.20**),
**THE SYSTEM SHALL** actuate the **CO2** sparge branch of the split-range controller to lower pH,
and **SHALL NOT** actuate the base branch simultaneously.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`

#### URS-05 — pH base branch (Na2CO3 1 M)
**WHEN** the measured pH falls below the lower dead-band limit (**pH < 6.80**),
**THE SYSTEM SHALL** actuate the base-addition branch delivering **1 M Na2CO3** to raise pH, and
**SHALL NOT** actuate the CO2 branch simultaneously, preserving split-range mutual exclusivity.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`

### 5.3 Dissolved Oxygen Set-Point and Mass-Transfer Sufficiency

#### URS-06 — DO set-point and oxygen-transfer sufficiency
**WHEN** the culture is active,
**THE SYSTEM SHALL** issue a dissolved-oxygen (OD) set-point of **30 %** of air saturation
(`ProcessDescription.do_setpoint_pct`) to the local DO controller, and **SHALL** verify that the
oxygen-transfer rate is sufficient for the culture demand (**OTR ≥ OUR**) over the A-Mab
pilot/commercial operating window. OTR is computed as kLa × (0.21 − 0.063) mmol/L, the driving
force between air saturation and 30 % DO. Regulation of the measured DO is delegated to the local
controller; THE SYSTEM does not simulate or qualify a DO PID loop.
- *GAMP Category:* 5 — *Process Risk:* High — *Modules:* `models.py`, `amab_design_space.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`

### 5.4 Adaptive Glucose Feeding

#### URS-07 — Adaptive glucose feed trigger
**WHEN** the measured residual glucose concentration drops **below 2.0 g/L**,
**THE SYSTEM SHALL** trigger an adaptive bolus/continuous feed that restores glucose toward a
target of **5.0 g/L**, avoiding overshoot that would cause lactate accumulation or osmolality excursion.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_03_closed_loop_vs_static_titer_gain`

#### URS-08 — Closed-loop titer advantage
**WHEN** the adaptive feed strategy is enabled versus a static (open-loop) feed baseline,
**THE SYSTEM SHALL** demonstrate a reproducible increase in final antibody titer and final
viability. The size of the gain is the emergent output of the model equations and is reported, not
constrained to a fixed band.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_03_closed_loop_vs_static_titer_gain`

### 5.5 Hydrodynamic Shear Safety Interlock

#### URS-09 — Hydrodynamic shear interlock (P/V)
**WHEN** `power_density_W_m3` > **47.6 W/m³** **AND** `sparge_vvm` > **0.15 vvm** (both conditions
must hold; P/V above 47.6 W/m³ with sparge ≤ 0.15 vvm does not trip the alarm),
**THE SYSTEM SHALL** raise the hydrodynamic-shear alarm (`high_shear_alarm = True`) and, when an
Audit Trail logger is supplied, record the trip in the Part 11 Audit Trail, applying the same limit at
every scale. THE SYSTEM does not cap agitation or sparge itself; the corrective action is left to the
operator or the local controller.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_04_safety_shear_and_cip_sip_interlocks`

#### URS-10 — Shear interlock scale translation
**WHEN** the process is scaled between 0.25 L and 15,000 L,
**THE SYSTEM SHALL** evaluate the P/V shear limit using scale-appropriate geometry (impeller
diameter, power number, working volume) so that the **47.6 W/m³** criterion remains physically valid.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_04_safety_shear_and_cip_sip_interlocks`

### 5.6 CIP / SIP Interlocks

#### URS-11 — CIP flow-velocity interlock (ASME BPE)
**WHEN** a Clean-In-Place (CIP) cycle is executing,
**THE SYSTEM SHALL** verify that the cleaning-fluid velocity is **≥ 1.52 m/s** (per ASME BPE-2014
turbulent-flow hygienic requirement) and **SHALL** interlock/abort the cycle if velocity falls below
this threshold, logging the deviation.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_04_safety_shear_and_cip_sip_interlocks`

#### URS-12 — SIP lethality interlock (F0)
**WHEN** a Sterilize-In-Place (SIP) cycle is executing,
**THE SYSTEM SHALL** compute accumulated lethality **F0** and **SHALL** release the vessel to
production only when **F0 ≥ 15 min** at a temperature **≥ 121.1 °C**, otherwise holding the batch
in a non-released state and logging the failure.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `bioreactor_twin.py` — *OQ:* `test_oq_04_safety_shear_and_cip_sip_interlocks`

### 5.7 Design Space, Thermal and Data-Integrity Requirements

#### URS-13 — ISPE A-Mab Design Space enforcement
**WHEN** the operator proposes a set-point combination of critical process parameters,
**THE SYSTEM SHALL** evaluate whether the combination lies inside the validated **A-Mab Design
Space** (center point and edges-of-failure) and **SHALL** flag any point outside the multivariate
acceptable region.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `amab_design_space.py` — *OQ:* `test_oq_05_ispe_amab_design_space_center_and_edges`

#### URS-14 — Mean Kinetic Temperature and cold-chain damping
**WHEN** time-series temperature data from storage or transport is supplied,
**THE SYSTEM SHALL** compute the **Mean Kinetic Temperature (MKT)** and model the thermal damping
of a Validated Thermal Buffer (VTB), reporting excursions beyond labeled storage conditions.
- *GAMP Category:* 5 — *Process Risk:* High — *Module:* `thermal_vtb_mkt.py` — *OQ:* `test_oq_06_mkt_and_vtb_damping`

#### URS-15 — Part 11 Audit Trail and SPC capability
**WHEN** any GxP-relevant record is created, modified or an interlock fires,
**THE SYSTEM SHALL** capture a **21 CFR Part 11** compliant, time-stamped, attributable,
tamper-evident Audit Trail entry, and **SHALL** support Statistical Process Control (SPC) and
process-capability (Cpk) analysis of the recorded data, honoring the Draft Annex 22 AI guardrail.
- *GAMP Category:* 5 — *Process Risk:* High — *Modules:* `audit_trail_part11.py`, `spc_six_sigma.py` — *OQ:* `test_oq_09_part11_audit_trail_and_annex22_guardrail`, `test_oq_08_gorsky_spc_tolerance_and_capability`

---

## 6. Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-01 | All numerical computations shall be deterministic and reproducible given identical seeds and inputs. |
| NFR-02 | Input parameters shall be validated via strongly-typed Pydantic models rejecting out-of-range or malformed values. |
| NFR-03 | The signal-processing subsystem shall respect the Nyquist criterion for sampling (see `test_oq_07`). |
| NFR-04 | The system shall degrade safely: on invalid input it raises a validated error rather than producing silent incorrect output. |
| NFR-05 | All alarms and interlocks shall be logged with ISO-8601 UTC time-stamps. |

## 7. Traceability

Every requirement URS-01 through URS-15 is forward-traced to a `src/` module, a CSA risk level,
and an OQ test case in the Requirements Traceability Matrix (document
`03_RTM_Traceability_Matrix.md`). The risk classification rationale is defined in
`02_FDA_CSA_Risk_Assessment_2026.md`.

## 8. Acceptance

This URS is accepted when all 15 user requirements are demonstrably satisfied by passing OQ
evidence and when the RTM shows 100 % bidirectional traceability with no orphan requirements and
no orphan tests.

*End of document URS-BRX-001.*
