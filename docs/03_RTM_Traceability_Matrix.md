# 03 — Requirements Traceability Matrix (RTM)

| Campo | Valor |
|-------|-------|
| **ID del documento** | RTM-BRX-001 |
| **Título** | Requirements Traceability Matrix — Sistema de control del biorreactor CHO-K1 fed-batch |
| **Versión** | 1.0 |
| **Traza desde** | `01_URS_Bioreactor_Control_System.md` (URS-01 … URS-15) |
| **Fuente del riesgo** | `02_FDA_CSA_Risk_Assessment_2026.md` |
| **Traza hacia** | Módulos `src/*.py` y pruebas OQ de `tests/test_csa_oq_validation.py` |

---

## 1. Propósito

Esta Requirements Traceability Matrix (RTM) establece la **trazabilidad bidireccional** entre cada
requisito de usuario (URS-01 a URS-15), el **módulo fuente** de `src/` que lo implementa, el **nivel
de riesgo de proceso CSA** asignado en el documento 02 y la **prueba de Operational Qualification
(OQ)** de `tests/test_csa_oq_validation.py` que aporta la evidencia objetiva de cumplimiento.

La RTM es la columna vertebral del paquete de validación: demuestra que (a) cada requisito está
implementado y probado (sin **requisitos huérfanos**) y (b) cada prueba se traza hasta un requisito
(sin **pruebas huérfanas**).

## 2. Módulos fuente (`src/`)

| Módulo | Responsabilidad |
|--------|----------------|
| `models.py` | Modelos de datos Pydantic de tipado estricto y validación de entradas. |
| `bioreactor_twin.py` | Programa de set-points de temperatura, split-range de pH, alimentación adaptativa / simulación fed-batch e interlocks de seguridad (cizalla, CIP, SIP). |
| `amab_design_space.py` | Ecuaciones del punto central y de los bordes de falla del Design Space ISPE A-Mab; ingeniería de escalamiento kLa / OTR / OUR. |
| `thermal_vtb_mkt.py` | Mean Kinetic Temperature y amortiguamiento del Validated Thermal Buffer. |
| `spc_six_sigma.py` | Statistical Process Control, intervalos de tolerancia y capacidad de proceso (Cpk). |
| `audit_trail_part11.py` | Audit trail conforme a 21 CFR Part 11, con evidencia de manipulación. |

## 3. Suite de pruebas OQ (`tests/test_csa_oq_validation.py`)

| ID de la prueba | Alcance |
|---------|-------|
| `test_oq_01_setpoints_and_ph_split_range_exclusivity` | Set-points validados (T, pH, DO), dead-band y exclusión mutua del split-range de pH, OTR ≥ OUR. |
| `test_oq_02_automated_day7_temperature_shift` | Cambio automático de 36.5 °C → 34.0 °C en el día 7.0. |
| `test_oq_03_closed_loop_vs_static_titer_gain` | Reposición adaptativa de glucosa (disparo, V_gluc > 0), consumo de lactato, ganancia direccional de título/viabilidad frente a static. |
| `test_oq_03b_vessel_capacity_and_bolus_mass_balance` | V0 = 0.70 × vessel, V(t) ≤ vessel_volume_L (0.25 y 2.0 L, ambos modos) y balance de masa exacto en cada bolo. |
| `test_oq_03c_lactate_reconsumption_and_nonnegativity` | Reconsumo de lactato en closed_loop (L final < L pico, pico después del día 5) y L(t) ≥ 0 en ambos modos. |
| `test_oq_03d_lactate_profile_v131` | Perfil de lactato v1.3.1 (DO 30 %, 0.25 y 2.0 L): L final closed_loop < static, L pico > L final + 0.30 g/L, viabilidad closed_loop > 85 % y > static, título closed_loop > static. |
| `test_oq_03e_bolus_clipped_alarm` | Alarma de recorte de bolos: `bolus_clipped_alarm` False con llenado de 70 %, True con 95 %, y V(t) ≤ vessel_volume_L siempre. |
| `test_oq_04_safety_shear_and_cip_sip_interlocks` | Alarma de cizalla (P/V > 47.6 W/m³ OR sparge > 0.15 vvm), velocidad de CIP, interlocks de F0 de SIP. |
| `test_oq_04b_shear_or_gate_and_continuous_penalty` | Compuerta OR de cizalla: solo P/V alto (65, 0.10), solo sparge alto (30, 0.22) y ambos (65, 0.22) disparan la alarma y bajan título y viabilidad frente a nominal; (30, 0.10) y (47.6, 0.15) no la disparan. |
| `test_oq_05_ispe_amab_design_space_center_and_edges` | Punto central y bordes de falla del Design Space. |
| `test_oq_05b_amab_scale_up_kla_pilot_commercial_range` | kLa de escalamiento A-Mab en el rango piloto/comercial. |
| `test_oq_06_mkt_and_vtb_damping` | Cálculo de MKT y amortiguamiento térmico del VTB. |
| `test_oq_06b_do_setpoint_driving_force` | Set-point de DO en la fuerza impulsora: a 30 % kLa 20.0 y OTR 2.94; OTR ∝ (1 − DO/100); OTR decreciente con el DO; OTR ≥ OUR deja de cumplirse a DO alto. Gemelo: a DO 30 ratio y f_do = 1.0; a DO 10 sube el lactato y bajan título y viabilidad; a DO 85 ratio mínimo < 1 y título menor. |
| `test_oq_07_fft_nyquist_sampling_validation` | Validación del criterio de muestreo FFT / Nyquist. |
| `test_oq_08_gorsky_spc_tolerance_and_capability` | Intervalos de tolerancia y capacidad SPC de Gorsky. |
| `test_oq_09_part11_audit_trail_and_annex22_guardrail` | Audit trail de Part 11 y guardrail de AI del Annex 22. |
| `test_oq_09b_part11_human_approved_mutation_breaks_chain` | Evidencia de manipulación de Part 11: mutar el indicador `human_approved` almacenado rompe la cadena de hash. |
| `test_exploratory_10_invalid_pydantic_inputs` | Exploratory / error-guessing sobre entradas inválidas. |
| `test_exploratory_11_audit_trail_requires_reason` | Exploratory / error-guessing: entrada de audit trail sin razón. |
| `test_exploratory_12_welch_ttest_identical_groups_not_significant` | Exploratory / error-guessing: prueba t de Welch con grupos idénticos. |

## 4. Matriz maestra de trazabilidad

| ID URS | Requisito (resumen) | Módulo `src/` | Nivel de riesgo CSA | Prueba OQ |
|--------|-----------------------|---------------|----------------|---------|
| **URS-01** | Set-point inicial de temperatura validado de 36.5 °C (banda delegada al controlador local) | `models.py`, `bioreactor_twin.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-02** | Cambio automático en el día 7 de 36.5 → 34.0 °C | `bioreactor_twin.py` | High Process Risk | `test_oq_02_automated_day7_temperature_shift` |
| **URS-03** | Dead-band split-range de pH 7.00 ± 0.20 | `bioreactor_twin.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-04** | Rama ácida de pH por sparge de CO2 | `bioreactor_twin.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-05** | Rama básica de pH con Na2CO3 1 M | `bioreactor_twin.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-06** | Set-point de DO de 30 % y suficiencia de transferencia de masa OTR ≥ OUR | `models.py`, `amab_design_space.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-06** | Set-point de DO configurable en la fuerza impulsora C* × (1 − DO/100), verificación OTR ≥ OUR y respuesta del gemelo a hipoxia y limitación de O2 | `models.py`, `amab_design_space.py`, `bioreactor_twin.py` | High Process Risk | `test_oq_06b_do_setpoint_driving_force` |
| **URS-07** | Alimentación adaptativa de glucosa < 2.0 → 5.0 g/L | `bioreactor_twin.py` | High Process Risk | `test_oq_03_closed_loop_vs_static_titer_gain` |
| **URS-08** | Ventaja de título y viabilidad del lazo cerrado frente a static (ganancia emergente, sin banda fija) | `bioreactor_twin.py` | High Process Risk | `test_oq_03_closed_loop_vs_static_titer_gain` |
| **URS-07** | Capacidad del recipiente y balance de masa exacto de los bolos (V0 = 0.70 × vessel, V(t) ≤ vessel) | `bioreactor_twin.py` | High Process Risk | `test_oq_03b_vessel_capacity_and_bolus_mass_balance` |
| **URS-07** | Cinética continua de lactato: reconsumo tras el pico y L(t) ≥ 0 | `bioreactor_twin.py` | High Process Risk | `test_oq_03c_lactate_reconsumption_and_nonnegativity` |
| **URS-08** | Perfil de lactato v1.3.1 y ventaja de viabilidad y título del lazo cerrado | `bioreactor_twin.py` | High Process Risk | `test_oq_03d_lactate_profile_v131` |
| **URS-07** | Alarma de recorte de bolos por capacidad del recipiente (`bolus_clipped_alarm`) | `bioreactor_twin.py` | High Process Risk | `test_oq_03e_bolus_clipped_alarm` |
| **URS-09** | Interlock de cizalla: `high_shear_alarm` cuando `power_density_W_m3` > 47.6 W/m³ OR `sparge_vvm` > 0.15 vvm | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-10** | Traslado de escala del interlock de cizalla | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-09** | Compuerta OR de cizalla y penalización continua (sigma_shear) sobre kd y qp | `bioreactor_twin.py` | High Process Risk | `test_oq_04b_shear_or_gate_and_continuous_penalty` |
| **URS-11** | Interlock de velocidad de CIP ≥ 1.52 m/s (ASME BPE) | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-12** | F0 de SIP ≥ 15 min a ≥ 121.1 °C | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-13** | Centro/bordes del A-Mab Design Space | `amab_design_space.py` | High Process Risk | `test_oq_05_ispe_amab_design_space_center_and_edges` |
| **URS-13** | kLa de escalamiento A-Mab en el rango piloto/comercial | `amab_design_space.py` | High Process Risk | `test_oq_05b_amab_scale_up_kla_pilot_commercial_range` |
| **URS-14** | MKT y amortiguamiento térmico del VTB | `thermal_vtb_mkt.py` | High Process Risk | `test_oq_06_mkt_and_vtb_damping` |
| **URS-15** | Audit Trail de Part 11 + capacidad SPC | `audit_trail_part11.py`, `spc_six_sigma.py` | High Process Risk | `test_oq_09_part11_audit_trail_and_annex22_guardrail`, `test_oq_08_gorsky_spc_tolerance_and_capability` |
| **URS-15** | Audit Trail de Part 11: `human_approved` protegido por hash (evidencia de manipulación) | `audit_trail_part11.py` | High Process Risk | `test_oq_09b_part11_human_approved_mutation_breaks_chain` |
| **URS-15** | El Audit Trail de Part 11 exige una razón | `audit_trail_part11.py` | Exploratory / Error-Guessing | `test_exploratory_11_audit_trail_requires_reason` |
| **URS-15** | La prueba t de Welch con grupos idénticos no es significativa | `spc_six_sigma.py` | Exploratory / Error-Guessing | `test_exploratory_12_welch_ttest_identical_groups_not_significant` |

## 5. Trazabilidad inversa (prueba → requisito)

| Prueba OQ | URS cubiertos | Módulo(s) `src/` | Riesgo CSA |
|---------|-----------|------------------|----------|
| `test_oq_01_setpoints_and_ph_split_range_exclusivity` | URS-01, URS-03, URS-04, URS-05, URS-06 | `models.py`, `bioreactor_twin.py`, `amab_design_space.py` | High |
| `test_oq_02_automated_day7_temperature_shift` | URS-02 | `bioreactor_twin.py` | High |
| `test_oq_03_closed_loop_vs_static_titer_gain` | URS-07, URS-08 | `bioreactor_twin.py` | High |
| `test_oq_03b_vessel_capacity_and_bolus_mass_balance` | URS-07 | `bioreactor_twin.py` | High |
| `test_oq_03c_lactate_reconsumption_and_nonnegativity` | URS-07, URS-08 | `bioreactor_twin.py` | High |
| `test_oq_03d_lactate_profile_v131` | URS-07, URS-08 | `bioreactor_twin.py` | High |
| `test_oq_03e_bolus_clipped_alarm` | URS-07 | `bioreactor_twin.py` | High |
| `test_oq_04_safety_shear_and_cip_sip_interlocks` | URS-09, URS-10, URS-11, URS-12 | `bioreactor_twin.py` | High |
| `test_oq_04b_shear_or_gate_and_continuous_penalty` | URS-09 | `bioreactor_twin.py` | High |
| `test_oq_05_ispe_amab_design_space_center_and_edges` | URS-13 | `amab_design_space.py` | High |
| `test_oq_05b_amab_scale_up_kla_pilot_commercial_range` | URS-13 | `amab_design_space.py` | High |
| `test_oq_06_mkt_and_vtb_damping` | URS-14 | `thermal_vtb_mkt.py` | High |
| `test_oq_06b_do_setpoint_driving_force` | URS-06 | `amab_design_space.py`, `models.py`, `bioreactor_twin.py` | High |
| `test_oq_07_fft_nyquist_sampling_validation` | NFR-03 (muestreo Nyquist) | `thermal_vtb_mkt.py` | High |
| `test_oq_08_gorsky_spc_tolerance_and_capability` | URS-15 (SPC/Cpk) | `spc_six_sigma.py` | High |
| `test_oq_09_part11_audit_trail_and_annex22_guardrail` | URS-15 (Audit Trail) | `audit_trail_part11.py` | High |
| `test_oq_09b_part11_human_approved_mutation_breaks_chain` | URS-15 (Audit Trail) | `audit_trail_part11.py` | High |
| `test_exploratory_10_invalid_pydantic_inputs` | NFR-02, NFR-04 (validación) | `models.py` | High (guard) / exploratory |
| `test_exploratory_11_audit_trail_requires_reason` | URS-15 (Audit Trail) | `audit_trail_part11.py` | Exploratory / Error-Guessing |
| `test_exploratory_12_welch_ttest_identical_groups_not_significant` | URS-15 (SPC) | `spc_six_sigma.py` | Exploratory / Error-Guessing |

## 6. Análisis de cobertura

| Métrica | Resultado |
|--------|--------|
| Requisitos de usuario definidos | 15 (URS-01 … URS-15) |
| Requisitos trazados a un módulo | 15 / 15 (100 %) |
| Requisitos trazados a una prueba OQ | 15 / 15 (100 %) |
| Requisitos huérfanos (sin prueba) | 0 |
| Pruebas huérfanas (sin requisito) | 0 |
| Requisitos High Process Risk | 15 / 15 |
| Pruebas OQ ejecutadas | 20 |
| Pruebas scripted (High Process Risk) | 17 (`test_oq_01` … `test_oq_09`, incl. `test_oq_03b`, `test_oq_03c`, `test_oq_03d`, `test_oq_03e`, `test_oq_04b`, `test_oq_05b`, `test_oq_06b` y `test_oq_09b`) |
| Pruebas Unscripted Exploratory / Error-Guessing | 3 (`test_exploratory_10` … `test_exploratory_12`) |

**Nota sobre `test_oq_07_fft_nyquist_sampling_validation`:** esta prueba verifica el criterio no
funcional de muestreo de Nyquist (NFR-03), en el que se apoya la reconstrucción fiel de las señales
de los lazos de control y monitoreo. Se mantiene como prueba scripted High-Risk porque el aliasing
en señales de proceso muestreadas podría corromper en silencio las decisiones de control y de SPC.

**Nota sobre `test_exploratory_10_invalid_pydantic_inputs`:** esta prueba ejercita el filtro de
validación de entradas (`models.py`) con entradas mal formadas o inválidas. Aunque la validación de
entradas es en sí High Process Risk (es la puerta de acceso al núcleo), la *exploración de entradas
inválidas* se hace como actividad unscripted/error-guessing, en línea con el principio
least-burdensome de CSA.

**Nota sobre `test_exploratory_10`, `test_exploratory_11` y `test_exploratory_12`:** estas tres
pruebas son actividades de error-guessing y sondeo de fronteras bajo el principio least-burdensome
de la guía FDA CSA (Feb 2026). Complementan, sin reemplazarlas, las pruebas scripted sobre
`models.py` (entradas de CPP inválidas), `audit_trail_part11.py` (razón de cambio ausente o
demasiado corta) y `spc_six_sigma.py` (prueba t de Welch con grupos idénticos).

## 7. Detalle de verificación por requisito

La tabla siguiente amplía cada requisito con su criterio de aceptación y la evidencia objetiva que
debe producir la prueba OQ asignada. Así el revisor ve directamente la relación entre el enunciado
del requisito y la evidencia de aprobado/fallido.

| ID URS | Criterio de aceptación | Evidencia objetiva producida por la OQ |
|--------|----------------------|-----------------------------------|
| URS-01 | El set-point inicial de temperatura por defecto es 36.5 °C (`temp_initial_C`, `get_temperature_setpoint(0.0)`). | Aserciones del valor del set-point. |
| URS-02 | El set-point cambia automáticamente de 36.5 → 34.0 °C exactamente en el día 7.0. | Valores del set-point antes/después y entrada en el Audit Trail. |
| URS-03 | Set-point 7.00 y dead-band 0.20 en `ProcessDescription`; sin actuación mientras el pH esté en 6.80–7.20. | Aserciones del set-point y de reposo dentro de la dead-band. |
| URS-04 | La rama de CO2 se activa solo cuando pH > 7.20. | Barrido de exclusión mutua en pH 6.00–8.00 (rama ácida). |
| URS-05 | La rama de Na2CO3 1 M se activa solo cuando pH < 6.80. | Barrido de exclusión mutua en pH 6.00–8.00 (rama básica). |
| URS-06 | El set-point de DO es 30 %; OTR ≥ OUR en las esquinas Vs 0.005–0.017 m/s × P/V 19–30 W/m³. | Aserción del set-point y aserciones OTR ≥ OUR / `oxygen_sufficient`; con DO configurable, OTR ∝ (1 − DO/100), decreciente y `oxygen_sufficient` False a DO alto (`test_oq_06b`). Medido (v1.3.1, 2.0 L, closed_loop): DO 10 % título 0.8089 g/L, viabilidad 77.71 %, L pico 1.5135 g/L; DO 30 % título 1.2189 g/L, viabilidad 90.55 %; DO 85 % título 1.0734 g/L, ratio OTR/OUR mínimo 0.8292. |
| URS-07 | La glucosa baja de 2.0 g/L, se mantiene ≤ 6.5 g/L, queda ≥ 2.0 g/L después de cada alimentación y la reposición se dispara (volumen alimentado en lazo cerrado > volumen de los bolos basales). | Aserciones de glucosa mín./máx., de recuperación tras cada alimentación y de volumen alimentado; lactato final < lactato pico. Medido (v1.3.1, closed_loop, DO 30 %): G mín. 0.6408 g/L, G máx. 6.0000 g/L, L pico 1.3425 g/L (día 7.0), L final 0.5842 g/L; V(t) ≤ vessel y balance de masa exacto por bolo (`test_oq_03b`); L(t) ≥ 0 (`test_oq_03c`). |
| URS-08 | Título final y viabilidad final del lazo cerrado > línea base static (direccional; la ganancia no se acota a una banda). | Aserciones comparativas de título y viabilidad. Medido (v1.3.1, DO 30 %): título 1.2189 vs 1.0537 g/L (ganancia emergente +15.68 %), viabilidad 90.55 vs 80.54 % (`test_oq_03d`); con llenado de 95 % los bolos se recortan sin superar el recipiente (`test_oq_03e`). |
| URS-09 | `high_shear_alarm` se dispara cuando `power_density_W_m3` > 47.6 W/m³ OR `sparge_vvm` > 0.15 vvm; no se dispara con ambos en o por debajo de su umbral. | Aserción de la alarma al cruzar la frontera; aserciones direccionales de título y viabilidad menores que en nominal para (65, 0.10), (30, 0.22) y (65, 0.22) (`test_oq_04b`). |
| URS-10 | El límite P/V se evalúa con la geometría de cada escala, de 0.25 L a 15,000 L. | Aserción de consistencia entre escalas. |
| URS-11 | El CIP se aborta cuando la velocidad es < 1.52 m/s. | Aserción de interlock/aborto. |
| URS-12 | El SIP libera solo cuando F0 ≥ 15 min a ≥ 121.1 °C. | Aserción de acumulación de letalidad y de la compuerta de liberación. |
| URS-13 | El punto central queda dentro y los bordes se señalan fuera del Design Space. | Aserción de clasificación de centro/bordes. |
| URS-14 | Se calcula la MKT; el amortiguamiento del VTB reduce la amplitud de la excursión. | Aserción del valor de MKT sobre el dataset de referencia. |
| URS-15 | Entradas de auditoría atribuibles, con marca de tiempo y con evidencia de manipulación (incluido el indicador `human_approved`); se calcula el Cpk. | Aserciones de integridad del registro, de mutación de `human_approved` y de capacidad. |

## 8. Resumen de riesgo y aseguramiento

Los 15 requisitos de usuario se clasifican como **High Process Risk** según
`02_FDA_CSA_Risk_Assessment_2026.md` y, por lo tanto, se verifican con **Robust Scripted Testing**.
Ningún requisito de usuario de este sistema cae en la categoría Not-High-Risk; las funcionalidades
Not-High-Risk (gráficas, UI) son funciones de la capa de presentación que no se corresponden con
ninguna URS y se aseguran con pruebas unscripted exploratorias y de error-guessing, como se documenta
en la sección 5.2 del documento 02. Además, `test_exploratory_10`, `test_exploratory_11` y
`test_exploratory_12` son actividades de error-guessing y sondeo de fronteras bajo el principio
least-burdensome de la guía FDA CSA (Feb 2026); complementan las pruebas scripted sobre `models.py`,
`audit_trail_part11.py` y `spc_six_sigma.py` sin reemplazarlas.

## 9. Declaración de integridad de la trazabilidad

- **Trazabilidad hacia adelante:** URS → módulo → riesgo → prueba está completa para URS-01 … URS-15.
- **Trazabilidad hacia atrás:** cada prueba OQ de `tests/test_csa_oq_validation.py` se resuelve en al
  menos un requisito URS o en un requisito no funcional (NFR) documentado.
- **Sin huérfanos:** no hay requisitos huérfanos ni pruebas huérfanas.
- **Alineación con el riesgo:** cada requisito High-Risk tiene asignada una prueba OQ scripted.

## 10. Control de cambios

Cualquier modificación de un requisito URS, de la responsabilidad de un módulo, de la clasificación
de riesgo o de la asignación de pruebas debe reflejarse en esta RTM bajo control de cambios formal,
preservando el 100 % de trazabilidad bidireccional. Un cambio que añada un requisito debe añadir en
el mismo cambio controlado la asignación de módulo, la clasificación de riesgo y la prueba OQ
correspondientes. Un cambio que elimine o fusione una prueba debe reconfirmar que ningún requisito
queda sin evidencia.

*Fin del documento RTM-BRX-001.*
