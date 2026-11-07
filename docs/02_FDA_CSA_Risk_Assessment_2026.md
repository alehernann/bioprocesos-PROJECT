# 02 — FDA Computer Software Assurance (CSA) Risk Assessment — 2026

| Field | Value |
|-------|-------|
| **Document ID** | CSA-RA-2026-001 |
| **Title** | Risk Assessment under FDA CSA for Production and Quality System Software |
| **Version** | 1.0 |
| **Primary Guidance** | FDA *Computer Software Assurance for Production and Quality System Software*, CDRH/CBER/CDER, Feb 3, 2026 |
| **Supporting Standards** | ISO 13485:2016, 21 CFR Part 820 (QSR), GAMP 5 (2nd ed.), 21 CFR Part 11, EudraLex Annex 11, Draft Annex 22 (AI) |
| **System Under Assessment** | CHO-K1 Fed-Batch Bioreactor Control System (digital twin) |

---

## 1. Purpose

This Risk Assessment applies the **FDA Computer Software Assurance (CSA)** paradigm to the
bioreactor control system. CSA shifts the emphasis from exhaustive, documentation-heavy
*Computer System Validation (CSV)* toward **critical thinking** and **risk-based assurance**:
effort is concentrated where software failure would most directly affect **product quality**,
**patient safety**, or **data integrity**.

The core CSA question for each software feature is:

> *"If this software feature failed or behaved incorrectly, could it directly compromise
> product quality, process safety, or the integrity of a quality record?"*

- If **yes**, the feature is **High Process Risk** and receives **Robust Scripted Testing**
  (pre-approved, step-by-step scripts with expected results and objective evidence).
- If **no**, the feature is **Not High Process Risk** and may be assured with the least-burdensome
  appropriate method: **Unscripted Exploratory Testing**, **Ad-hoc Testing**, or
  **Error-Guessing Testing**, with record-of-activity rather than fully pre-scripted evidence.

## 2. Regulatory Basis and Interpretation

### 2.1 FDA CSA (2026)
CSA promotes a **least-burdensome** assurance approach proportional to risk. It explicitly
endorses **unscripted testing** (exploratory, ad-hoc, error-guessing) for lower-risk features and
reserves **scripted testing** (limited and robust) for higher-risk features. The assurance
activity and its evidence must be **commensurate with the risk**.

### 2.2 ISO 13485:2016
Clause 4.1.6 requires validation of software used in the quality management system using a
**risk-based** approach proportionate to the risk associated with its use. This aligns directly
with the CSA intended-use and risk-determination steps.

### 2.3 21 CFR Part 820 (Quality System Regulation)
§ 820.70(i) requires that software used to automate production or the quality system be validated
for its intended use according to an established protocol. CSA is the FDA's modern interpretation
of how to satisfy § 820.70(i) efficiently.

## 3. CSA Risk Determination Methodology

The assessment proceeds through the four CSA steps:

1. **Identify the intended use** of each software feature.
2. **Determine the risk** the feature poses to process/product (High vs. Not-High Process Risk).
3. **Determine the appropriate assurance activity** (scripted vs. unscripted).
4. **Establish the appropriate record** (objective evidence proportional to risk).

### 3.1 Risk Factors Considered
- **Direct product-quality impact** — does the feature control a CPP or evaluate a CQA?
- **Safety impact** — does the feature act as a safety interlock?
- **Data-integrity impact** — does the feature create/modify a Part 11 record?
- **Detectability** — would a failure be obvious or silent?
- **Downstream propagation** — does an error cascade into release decisions?

## 4. Risk Classification Matrix

| # | Software Feature / Function | Module | Intended Use | Failure Impact | **Process Risk** | **CSA Assurance Method** |
|---|-----------------------------|--------|--------------|----------------|------------------|--------------------------|
| 1 | **Closed-loop control** (Temp, pH, OD, glucose PID) | `bioreactor_twin.py` | Directly manipulates CPPs that define the batch. | Out-of-spec batch, CQA failure. | **High Process Risk** | **Robust Scripted Testing** |
| 2 | **Safety interlocks** (shear P/V, CIP velocity, SIP F0) | `bioreactor_twin.py` | Prevents cell damage, ensures cleaning/sterilization efficacy. | Contamination, non-sterile release, equipment/product loss. | **High Process Risk** | **Robust Scripted Testing** |
| 3 | **MKT calculation** (cold-chain thermal) | `thermal_vtb_mkt.py` | Determines whether storage/transport excursions compromise product. | Undetected potency/stability loss, wrong disposition. | **High Process Risk** | **Robust Scripted Testing** |
| 4 | **Design Space equations** (A-Mab center/edges) | `amab_design_space.py` | Defines the multivariate acceptable operating region (ICH Q8). | Operation outside validated space, regulatory non-compliance. | **High Process Risk** | **Robust Scripted Testing** |
| 5 | **Audit Trail** (21 CFR Part 11) | `audit_trail_part11.py` | Creates attributable, tamper-evident GxP records. | Data-integrity breach, loss of record trustworthiness. | **High Process Risk** | **Robust Scripted Testing** |
| 6 | **SPC / Six Sigma capability** (Cpk, tolerance intervals) | `spc_six_sigma.py` | Statistical release/monitoring decisions on process data. | Incorrect capability conclusion feeding disposition. | **High Process Risk** | **Robust Scripted Testing** |
| 7 | **Input validation** (Pydantic typed models) | `models.py` | Guards the High-Risk core from malformed input. | Propagates bad data into control/record logic. | **High Process Risk** | **Robust Scripted Testing** |
| 8 | **Charting / plotting** (Plotly figures) | visualization layer | Visual rendering of already-computed, validated data. | Cosmetic/display only; underlying data unaffected. | **Not High Process Risk** | **Unscripted Exploratory / Error-Guessing Testing** |
| 9 | **UI layout / navigation** (Streamlit widgets) | visualization layer | Operator ergonomics and presentation. | Inconvenience; no direct quality/safety/data impact. | **Not High Process Risk** | **Unscripted Exploratory / Error-Guessing Testing** |

## 5. Rationale for Each Classification

### 5.1 High Process Risk — Robust Scripted Testing

**Closed-loop control.** The PID loops for temperature (URS-01/02), pH split-range with dead-band
(URS-03/04/05), dissolved oxygen (URS-06) and adaptive glucose feeding (URS-07/08) directly set the
values of Critical Process Parameters. An error here changes the physical state of the batch and can
cause a Critical Quality Attribute to fall out of specification. These features demand pre-approved,
step-by-step scripts (`test_oq_01`, `test_oq_02`, `test_oq_03`) with defined expected results and
retained objective evidence.

**Safety interlocks.** The hydrodynamic-shear interlock (P/V > 47.6 W/m³, URS-09/10), the CIP
velocity interlock (≥ 1.52 m/s per ASME BPE, URS-11) and the SIP lethality interlock
(F0 ≥ 15 min at ≥ 121.1 °C, URS-12) are the last line of defense against cell damage, inadequate
cleaning and non-sterile product. Failure is catastrophic and often silent until it manifests as
contamination. Robust scripted testing (`test_oq_04`) with boundary and failure-mode cases is mandatory.

**MKT calculation.** Mean Kinetic Temperature (URS-14) governs disposition decisions for
temperature-sensitive product. A miscalculation could release degraded material or needlessly
discard good material; both are high-impact. Scripted testing against reference datasets
(`test_oq_06`) is required.

**Design Space equations.** The A-Mab Design Space (URS-13) encodes the ICH Q8 multivariate
acceptable region. Erroneous center-point or edge-of-failure logic could permit operation outside
the validated space. Scripted verification of center and edges (`test_oq_05`) is required.

**Audit Trail.** The 21 CFR Part 11 Audit Trail (URS-15) underpins the trustworthiness of every
GxP record. Any defect is a data-integrity defect. Scripted testing of attributability,
time-stamping and tamper evidence, with the Annex 22 AI guardrail
(`test_oq_09`), is required.

**SPC / Six Sigma.** Process-capability and tolerance-interval computation (Gorsky methodology)
feed statistical release and monitoring decisions. Incorrect Cpk or tolerance intervals corrupt
quality decisions, so scripted testing (`test_oq_08`) is required.

**Input validation.** The Pydantic typed models (`models.py`) are the gatekeeper that prevents
malformed data from reaching the High-Risk core. Although defensive, a validation gap would
propagate bad data everywhere, so it is treated as High Process Risk. Note that exploring *invalid*
inputs is complementary and covered by the unscripted `test_exploratory_10_invalid_pydantic_inputs`.

### 5.2 Not High Process Risk — Unscripted Exploratory / Error-Guessing Testing

**Charting / plotting.** Plotly figures render data that has *already* been computed and validated
by the High-Risk modules. A rendering defect is cosmetic: it does not change the underlying batch
data, control actions, or records. The appropriate, least-burdensome assurance is unscripted
exploratory testing and error-guessing (does the chart render? are axes labeled? does it handle an
empty series gracefully?) with a record of the activity rather than a full pre-approved script.

**UI layout / navigation.** Streamlit widgets and page layout affect operator ergonomics, not
product quality, safety, or data integrity. Exploratory and error-guessing testing (click-through,
boundary interactions, resize behavior) is sufficient and proportionate.

## 6. Assurance Effort Allocation (CSA Principle)

```
          HIGH assurance effort
                 ▲
                 │   ┌─────────────────────────────────────┐
   Robust        │   │ Control loops, interlocks, MKT,      │
   Scripted      │   │ Design Space, Audit Trail, SPC,      │
   Testing       │   │ input validation (Category 5 core)   │
                 │   └─────────────────────────────────────┘
                 │
   Unscripted    │        ┌───────────────────────────┐
   Exploratory / │        │ Plotting, UI / navigation  │
   Error-Guessing│        │ (presentation layer)       │
                 │        └───────────────────────────┘
                 ▼
          LOW assurance effort
```

The majority of validation effort is deliberately concentrated on the High Process Risk,
custom-code (GAMP Category 5) core, consistent with the CSA least-burdensome principle.

## 7. Linkage to Testing and Traceability

- High Process Risk features map to the scripted OQ tests `test_oq_01` through `test_oq_09` in
  `tests/test_csa_oq_validation.py`.
- The Not-High-Risk and the invalid-input exploration map to
  `test_exploratory_10_invalid_pydantic_inputs`.
- Full forward/backward traceability is maintained in `03_RTM_Traceability_Matrix.md`.

## 8. Conclusion

Applying FDA CSA (2026), ISO 13485 and 21 CFR Part 820, the control loops, safety interlocks, MKT
calculation, Design Space equations, SPC capability, Audit Trail and input validation are
classified **High Process Risk** and verified by **Robust Scripted Testing**. Plotting and UI are
classified **Not High Process Risk** and assured by **Unscripted Exploratory / Error-Guessing
Testing**. This allocation focuses assurance where failure would most affect product quality,
safety and data integrity.

*End of document CSA-RA-2026-001.*
