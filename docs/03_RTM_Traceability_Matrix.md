# 03 — Requirements Traceability Matrix (RTM)

| Campo | Valor |
|-------|-------|
| **ID del documento** | RTM-BRX-001 |
| **Título** | Requirements Traceability Matrix — Sistema de control del biorreactor CHO-K1 fed-batch |
| **Versión** | 1.4.0 |
| **Traza desde** | `01_URS_Bioreactor_Control_System.md` (URS-01 … URS-16, NFR-01 … NFR-07) |
| **Fuente del riesgo** | `02_FDA_CSA_Risk_Assessment_2026.md` |
| **Traza hacia** | Módulos `src/*.py`, `data/bionova_nistcho_2026.json` y pruebas OQ de `tests/test_csa_oq_validation.py` |

---

## 1. Propósito

Esta Requirements Traceability Matrix (RTM) establece la **trazabilidad bidireccional** entre cada
requisito de usuario (URS-01 a URS-16), el **módulo fuente** de `src/` que lo implementa, el **nivel
de riesgo de proceso CSA** asignado en el documento 02 y la **prueba de Operational Qualification
(OQ)** de `tests/test_csa_oq_validation.py` que aporta la evidencia objetiva de cumplimiento.

La RTM es la columna vertebral del paquete de validación: demuestra que (a) cada requisito está
implementado y probado (sin **requisitos huérfanos**) y (b) cada prueba se traza hasta un requisito
(sin **pruebas huérfanas**).

## 2. Módulos fuente (`src/`) y datos de referencia

| Módulo | Responsabilidad |
|--------|----------------|
| `models.py` | Modelos de datos Pydantic de tipado estricto, validación de entradas y validadores cruzados (`model_validator`). |
| `bioreactor_twin.py` | Programa de set-points de temperatura, split-range de pH, gemelo mecanístico de 6 estados (Xv, Xd, G, L, NH3, título) más volumen, integrado con RK45/Radau, alimentación (`mode` binario static / closed_loop; regla de glucosa en static con `glucose_feedback_in_static`), balance de O2 con enriquecimiento e interlocks de seguridad (cizalla, CIP, SIP). Constantes cinéticas calibradas y documentadas. |
| `model_validation.py` | Carga del dataset Bionova, calibración (`least_squares` TRF), identificabilidad por Jacobiano, experimento de cambio guiado por identificabilidad (`compare_k_i_l_m_g_swap`), métricas de validación dentro y fuera de muestra y verificación de convergencia numérica (ASME V&V 40). |
| `amab_design_space.py` | Ecuaciones del punto central y de los bordes de falla del Design Space ISPE A-Mab; ingeniería de escalamiento kLa / OTR / OUR con fracción molar de O2 del gas. |
| `thermal_vtb_mkt.py` | Mean Kinetic Temperature y amortiguamiento del virtual thermal buffer (VTB, Rusnack). |
| `spc_six_sigma.py` | Statistical Process Control, intervalos de tolerancia, capacidad de proceso (Cpk), estabilidad I-MR y equivalencia TOST + Levene. |
| `audit_trail_part11.py` | Audit trail conforme a 21 CFR Part 11, con evidencia de manipulación. |
| `data/bionova_nistcho_2026.json` | Dataset de referencia de Bionova (Ref. 2): protocolo y valores del día 14 impresos (`printed_exact`), series digitalizadas de figuras con incertidumbre (`digitized_figure_approx`), muestreo `pre_feed_daily`; 30 W/m³ para calibración y 19 W/m³ para validación fuera de muestra. |

## 3. Suite de pruebas OQ (`tests/test_csa_oq_validation.py`)

| ID de la prueba | Alcance |
|---------|-------|
| `test_oq_01_setpoints_and_ph_split_range_exclusivity` | Set-points validados (T, pH, DO), dead-band y exclusión mutua del split-range de pH, OTR ≥ OUR. |
| `test_oq_02_automated_day7_temperature_shift` | Cambio automático de 36.5 °C → 34.0 °C en el día 7.0, registrado una vez en el Audit Trail. |
| `test_oq_03_closed_loop_vs_static_titer_gain` | Regla de glucosa pre-feed evento por evento en closed_loop y en static con `glucose_feedback_in_static` (reposición exacta al objetivo solo cuando hace falta; regla por defecto 2 → 5 g/L y disparo validado 6 → 9 g/L; la bandera no cambia los bolos), tren de bolos (4.62 % de V0; ×1.80 y ×1.82 de Ark), reconsumo de lactato y comparación emergente closed_loop vs static (masa cosechada y viabilidad mayores; g/L reportado). |
| `test_oq_03b_vessel_capacity_and_bolus_mass_balance` | V0 = `initial_fill_fraction` × vessel (0.70 y 0.76), V(t) ≤ vessel (0.25 y 2.0 L; static, static con regla de glucosa y closed_loop) y balance de masa exacto de Xv, Xd, G, L, NH3 y título en cada bolo; `daily_pre_feed` = estado previo al bolo; sin bolo el día de cosecha (14 d: 6 bolos; 12 d: 5). |
| `test_oq_03c_lactate_reconsumption_and_nonnegativity` | Pico de lactato entre los días 4 y 6, reconsumo (L día 8 < 50 % del pico, L final < pico) y L(t) ≥ 0 en los tres modos. |
| `test_oq_03d_lactate_switch_state_governed` | Protocolo Bionova: pico pre-feed el día 4 o 5 en 1.2–1.5 g/L, L día 7 en 0.2–0.6 g/L y L día 8 < 0.6 g/L, también con el cambio térmico movido a los días 10 y 14 (switch gobernado por el estado). |
| `test_oq_03e_bolus_clipped_alarm` | Alarma de recorte de bolos: `bolus_clipped_alarm` False con llenado de 0.70, True con 0.95, y V(t) ≤ vessel_volume_L siempre. |
| `test_oq_03f_rk45_convergence_and_nh3_decline` | Convergencia RK45 (1e-6) frente a RK45/Radau (1e-9), cambio automático a Radau, error del Euler de v1.3.2; NH3 no decreciente entre bolos, > 5 mM el día 14 y mayor el día 21; caída de viabilidad > 20 puntos a 21 d y contrafactual sin muerte por NH3. |
| `test_oq_03g_bionova_validation_fit_and_oos` | Dataset y protocolo Bionova (`mode="static"`, `glucose_feedback_in_static=True`, llenado 0.76, 0.25 L, 30/19 W/m³); reproducibilidad de la calibración (10 parámetros, 60 puntos); identificabilidad (valores singulares, cond(J), K_I_L no identificable); métricas R², RMSE y criterio RMSE ≤ 2σ dentro y fuera de muestra; experimento K_I,L fijo → m_G libre y su regla de adopción. |
| `test_oq_03h_slider_domain_physical_stability` | 256 esquinas del dominio de los sliders (DO 5–90 %): sin NaN/Inf, concentraciones ≥ 0, viabilidad en [0, 100] %, V(t) ≤ vessel, < 0.25 s por corrida; cambio térmico posterior al fin rechazado por el esquema; corrida por defecto < 80 ms de media; sensibilidad direccional (sparge 0.25 vs 0.10 vvm, 21 vs 14 d, cambio en día 4 vs 10). |
| `test_oq_04_safety_shear_and_cip_sip_interlocks` | Caso nominal: alarma de cizalla (P/V > 47.6 W/m³ OR sparge > 0.15 vvm), bloqueo de CIP, velocidad de CIP = 1.52 m/s y SIP conforme. Frontera y falla: velocidad de CIP 1.52 m/s cumple y 1.51 / 1.0 / 0.0 m/s no; SIP con F0 = 15.0 min a 121.1 °C cumple; F0 < 15 min, T < 121.1 °C (también una sola lectura) y ambas fallas no cumplen. |
| `test_oq_04b_shear_or_gate_and_continuous_penalty` | Compuerta OR de la alarma; desacople: P/V de 50 a 100 W/m³ dispara la alarma sin cambiar título, viabilidad, VCD pico ni masa; sparge 0.22 vvm los reduce; P/V sobre sparge no agrega nada; intensidad de estrés nula para todo P/V del esquema. |
| `test_oq_05_ispe_amab_design_space_center_and_edges` | Punto central y bordes de falla del Design Space. |
| `test_oq_05b_amab_scale_up_kla_pilot_commercial_range` | kLa medido por escala de A-Mab Tabla 3.22 (2 L 10, 500 L 8, 1,000 L 10, 5,000 L 10, 15,000 L 20, 25,000 L Future 20 h⁻¹), todos en 8–20 h⁻¹ y usados tal cual por `compute_scale_up_engineering(measured_kla_h_inv=...)`; ancla de la correlación 20.0 h⁻¹ en 15,000 L; búsqueda de la columna inmediatamente inferior (proxy de 2 L por debajo de 2 L) y kLa 10 h⁻¹ del gemelo a 0.25 L. |
| `test_oq_06_mkt_and_vtb_damping` | Cálculo de MKT y amortiguamiento térmico del VTB. |
| `test_oq_06b_do_setpoint_driving_force` | Fuerza impulsora con aire sin cambios (kLa 20.0, OTR 2.94, OTR ∝ (1 − DO/100), insuficiente a DO alto) y con O2 puro; factor de hipoxia (1.0 desde 15 %, continuo, monótono); balance cuasi estacionario de O2; DO 85 % solo aire: controlador saturado, DO real 55–75 % con f_do = 1.0, hipoxia solo sobre el límite de 17.85e6 cél/mL; con enriquecimiento DO real = set-point y VCD > 20e6; DO 5 % y transferencia limitada por aire: hipoxia real. |
| `test_oq_07_fft_nyquist_sampling_validation` | Validación del criterio de muestreo FFT / Nyquist. |
| `test_oq_08_gorsky_spc_tolerance_and_capability` | Intervalos de tolerancia y capacidad SPC de Gorsky. |
| `test_oq_08b_spc_control_stability_and_tost_equivalence` | Regla 1 de Shewhart (I-MR) antes de la capacidad (Gorsky en control; proceso con deriva normal pero fuera de control); TOST recalculado de forma independiente y dualidad con el IC 90 %; Levene rechaza equivalencia con dispersiones distintas; validación de entradas. |
| `test_oq_09_part11_audit_trail_and_annex22_guardrail` | Audit trail de Part 11 y guardrail de AI del Annex 22. |
| `test_oq_09b_part11_human_approved_mutation_breaks_chain` | Evidencia de manipulación de Part 11: mutar el indicador `human_approved` almacenado rompe la cadena de hash. |
| `test_exploratory_10_invalid_pydantic_inputs` | Unscripted / error-guessing (Not High Process Risk) sobre entradas inválidas, validadores cruzados (glucosa, cambio térmico), campos nuevos y contrato binario de `mode` (`bionova_baseline` rechazado). |
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
| **URS-06** | Set-point de DO de 30 % y suficiencia de transferencia de masa OTR ≥ OUR | `models.py`, `amab_design_space.py`, `bioreactor_twin.py` | High Process Risk | `test_oq_01_setpoints_and_ph_split_range_exclusivity` |
| **URS-06** | Fuerza impulsora con fracción molar de O2 del gas, DO real del líquido, saturación del controlador sin hipoxia falsa, enriquecimiento con O2 e hipoxia real | `models.py`, `amab_design_space.py`, `bioreactor_twin.py` | High Process Risk | `test_oq_06b_do_setpoint_driving_force` |
| **URS-06** | kLa medido por escala (A-Mab Tabla 3.22) en la calculadora y en el gemelo; proxy de 2 L por debajo de 2 L | `amab_design_space.py`, `bioreactor_twin.py` | High Process Risk | `test_oq_05b_amab_scale_up_kla_pilot_commercial_range` |
| **URS-07** | Reposición de glucosa pre-feed exacta al objetivo (2 → 5 g/L por defecto) en `closed_loop` y en `static` con `glucose_feedback_in_static` | `models.py`, `bioreactor_twin.py` | High Process Risk | `test_oq_03_closed_loop_vs_static_titer_gain` |
| **URS-08** | Comparación emergente closed_loop vs static: mayor masa cosechada y viabilidad; g/L reportado | `bioreactor_twin.py` | High Process Risk | `test_oq_03_closed_loop_vs_static_titer_gain` |
| **URS-07** | Capacidad del recipiente y balance de masa exacto de 6 especies por bolo (V0 = fill × vessel, V(t) ≤ vessel) | `bioreactor_twin.py` | High Process Risk | `test_oq_03b_vessel_capacity_and_bolus_mass_balance` |
| **URS-07** | Cinética continua de lactato: reconsumo tras el pico y L(t) ≥ 0 | `bioreactor_twin.py` | High Process Risk | `test_oq_03c_lactate_reconsumption_and_nonnegativity` |
| **URS-16** | Switch de lactato gobernado por el estado (pico día 4–5, reconsumo día 7–8, independiente del cambio térmico) | `bioreactor_twin.py`, `model_validation.py` | High Process Risk | `test_oq_03d_lactate_switch_state_governed` |
| **URS-07** | Alarma de recorte de bolos por capacidad del recipiente (`bolus_clipped_alarm`) | `bioreactor_twin.py` | High Process Risk | `test_oq_03e_bolus_clipped_alarm` |
| **URS-16** | Convergencia numérica, acumulación de NH3 y caída real de viabilidad a 21 d | `bioreactor_twin.py`, `model_validation.py` | High Process Risk | `test_oq_03f_rk45_convergence_and_nh3_decline` |
| **URS-16** | Calibración reproducible, identificabilidad y validación dentro y fuera de muestra contra Bionova | `model_validation.py`, `bioreactor_twin.py` | High Process Risk | `test_oq_03g_bionova_validation_fit_and_oos` |
| **NFR-06 / NFR-07** | Estabilidad física y desempeño en todo el dominio de los sliders | `bioreactor_twin.py`, `models.py` | High Process Risk | `test_oq_03h_slider_domain_physical_stability` |
| **URS-02** | Efecto direccional del día de cambio térmico en la cinética calibrada (cambio en día 4 frente a 10: VCD pico menor) | `bioreactor_twin.py` | High Process Risk | `test_oq_03h_slider_domain_physical_stability` |
| **URS-09** | Interlock de cizalla: `high_shear_alarm` cuando `power_density_W_m3` > 47.6 W/m³ OR `sparge_vvm` > 0.15 vvm | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-10** | Mismo umbral de cizalla en todas las escalas: 47.6 W/m³ (P/V máximo demostrado aceptable a 2 L, A-Mab Tabla 3.22, criterio conservador, no umbral de daño) y 0.15 vvm (supuesto de modelado) | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-09** | Compuerta OR de la alarma y desacople alarma–cinética (penalización por burbujeo; impulsor solo sobre 476 W/m³) | `bioreactor_twin.py` | High Process Risk | `test_oq_04b_shear_or_gate_and_continuous_penalty` |
| **URS-11** | Indicador de velocidad de CIP ≥ 1.52 m/s (ASME BPE), registrado en el Audit Trail si hay logger | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-12** | Indicador de F0 de SIP ≥ 15 min a ≥ 121.1 °C, registrado en el Audit Trail si hay logger | `bioreactor_twin.py` | High Process Risk | `test_oq_04_safety_shear_and_cip_sip_interlocks` |
| **URS-13** | Centro/bordes del A-Mab Design Space | `amab_design_space.py` | High Process Risk | `test_oq_05_ispe_amab_design_space_center_and_edges` |
| **URS-14** | MKT y amortiguamiento térmico del virtual thermal buffer (VTB) | `thermal_vtb_mkt.py` | High Process Risk | `test_oq_06_mkt_and_vtb_damping` |
| **URS-15** | Audit Trail de Part 11 + capacidad SPC | `audit_trail_part11.py`, `spc_six_sigma.py` | High Process Risk | `test_oq_09_part11_audit_trail_and_annex22_guardrail`, `test_oq_08_gorsky_spc_tolerance_and_capability` |
| **URS-15** | Estabilidad I-MR antes de la capacidad y equivalencia formal TOST + Levene | `spc_six_sigma.py` | High Process Risk | `test_oq_08b_spc_control_stability_and_tost_equivalence` |
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
| `test_oq_03d_lactate_switch_state_governed` | URS-16 | `bioreactor_twin.py`, `model_validation.py` | High |
| `test_oq_03e_bolus_clipped_alarm` | URS-07 | `bioreactor_twin.py` | High |
| `test_oq_03f_rk45_convergence_and_nh3_decline` | URS-16, NFR-06 | `bioreactor_twin.py`, `model_validation.py` | High |
| `test_oq_03g_bionova_validation_fit_and_oos` | URS-16 | `model_validation.py`, `bioreactor_twin.py` | High |
| `test_oq_03h_slider_domain_physical_stability` | NFR-06, NFR-07, NFR-02, URS-02 (sensibilidad) | `bioreactor_twin.py`, `models.py` | High |
| `test_oq_04_safety_shear_and_cip_sip_interlocks` | URS-09, URS-10, URS-11, URS-12 | `bioreactor_twin.py` | High |
| `test_oq_04b_shear_or_gate_and_continuous_penalty` | URS-09 | `bioreactor_twin.py` | High |
| `test_oq_05_ispe_amab_design_space_center_and_edges` | URS-13 | `amab_design_space.py` | High |
| `test_oq_05b_amab_scale_up_kla_pilot_commercial_range` | URS-06 | `amab_design_space.py` | High |
| `test_oq_06_mkt_and_vtb_damping` | URS-14 | `thermal_vtb_mkt.py` | High |
| `test_oq_06b_do_setpoint_driving_force` | URS-06 | `amab_design_space.py`, `models.py`, `bioreactor_twin.py` | High |
| `test_oq_07_fft_nyquist_sampling_validation` | NFR-03 (muestreo Nyquist) | `thermal_vtb_mkt.py` | High |
| `test_oq_08_gorsky_spc_tolerance_and_capability` | URS-15 (SPC/Cpk) | `spc_six_sigma.py` | High |
| `test_oq_08b_spc_control_stability_and_tost_equivalence` | URS-15 (SPC: estabilidad y equivalencia) | `spc_six_sigma.py` | High |
| `test_oq_09_part11_audit_trail_and_annex22_guardrail` | URS-15 (Audit Trail) | `audit_trail_part11.py` | High |
| `test_oq_09b_part11_human_approved_mutation_breaks_chain` | URS-15 (Audit Trail) | `audit_trail_part11.py` | High |
| `test_exploratory_10_invalid_pydantic_inputs` | NFR-02, NFR-04 (validación) | `models.py` | Exploratory / Error-Guessing |
| `test_exploratory_11_audit_trail_requires_reason` | URS-15 (Audit Trail) | `audit_trail_part11.py` | Exploratory / Error-Guessing |
| `test_exploratory_12_welch_ttest_identical_groups_not_significant` | URS-15 (SPC) | `spc_six_sigma.py` | Exploratory / Error-Guessing |

## 6. Análisis de cobertura

| Métrica | Resultado |
|--------|--------|
| Requisitos de usuario definidos | 16 (URS-01 … URS-16) |
| Requisitos trazados a un módulo | 16 / 16 (100 %) |
| Requisitos trazados a una prueba OQ | 16 / 16 (100 %) |
| Requisitos huérfanos (sin prueba) | 0 |
| Pruebas huérfanas (sin requisito) | 0 |
| Requisitos High Process Risk | 16 / 16 |
| Pruebas OQ ejecutadas | 24 |
| Pruebas scripted (High Process Risk) | 21 (`test_oq_01` … `test_oq_09`, incl. `test_oq_03b` … `test_oq_03h`, `test_oq_04b`, `test_oq_05b`, `test_oq_06b`, `test_oq_08b` y `test_oq_09b`) |
| Pruebas Unscripted Exploratory / Error-Guessing | 3 (`test_exploratory_10` … `test_exploratory_12`) |
| Pruebas de humo del tablero (`tests_app/`, fuera de la OQ) | 17 |

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
del requisito y la evidencia de aprobado/fallido. Los valores medidos son de v1.4.0 (constantes
calibradas, DO 30 %, enriquecimiento con O2 activo, llenado 0.70, 2.0 L salvo que se indique).

| ID URS | Criterio de aceptación | Evidencia objetiva producida por la OQ |
|--------|----------------------|-----------------------------------|
| URS-01 | El set-point inicial de temperatura por defecto es 36.5 °C (`temp_initial_C`, `get_temperature_setpoint(0.0)`). | Aserciones del valor del set-point. |
| URS-02 | El set-point cambia automáticamente de 36.5 → 34.0 °C como escalón (sin rampa) exactamente en el día 7.0; adelantar el cambio baja la VCD pico. | Valores del set-point antes/después y entrada en el Audit Trail (`test_oq_02`); VCD pico con cambio en el día 4 (20.09e6) menor que en el día 10 (30.45e6) (`test_oq_03h`). Barrido completo en la sección 11. |
| URS-03 | Set-point 7.00 y dead-band 0.20 en `ProcessDescription`; sin actuación mientras el pH esté en 6.80–7.20. | Aserciones del set-point y de reposo dentro de la dead-band. |
| URS-04 | La rama de CO2 se activa solo cuando pH > 7.20. | Barrido de exclusión mutua en pH 6.00–8.00 (rama ácida). |
| URS-05 | La rama de Na2CO3 1 M se activa solo cuando pH < 6.80. | Barrido de exclusión mutua en pH 6.00–8.00 (rama básica). |
| URS-06 | Set-point de DO de 30 %; OTR ≥ OUR en las esquinas de prueba de la correlación con aire; con aire la salida es idéntica bit a bit a v1.3.2. En el gemelo la biología depende solo del DO real: f_do = 1.0 siempre que DO real ≥ 15 %. | `test_oq_06b`. Medido: DO 85 % solo aire, controlador saturado desde el día 2.5, DO real 55–75 % en los días 3.4–4.6 con f_do = 1.0, primera hipoxia real el día 6.6 con Xv 17.99e6 (límite físico 17.85e6); título 1.6408 g/L. Con enriquecimiento: DO real = set-point a 30 y 85 %, y_O2 requerido máximo 0.298 / 0.414, título 1.9243 g/L en ambos. DO 5 %: f_do 0.846, pico de lactato 1.526 g/L (1.341 a 30 %), título 0.9301 g/L, VCD pico 14.10e6. |
| URS-07 | La reposición se dispara solo si G pre-feed (o post-bolo) < disparo y el bolo no alcanza el objetivo, y deja G exactamente en el objetivo; G ≥ disparo después de cada bolo; `static` sin `glucose_feedback_in_static` nunca repone. | `test_oq_03`, `test_oq_03b`, `test_oq_03c`, `test_oq_03e`. Medido con la calibración vigente: con 2 → 5 g/L no hay reposiciones (G pre-feed mínima en día de alimentación 2.007 g/L en Bionova); con 6 → 9 g/L sí. Con el escenario B (no adoptado) la mínima es 1.757 g/L y repone el día 12. Balance de masa exacto de las 6 especies (|error| ≤ 1e-9). |
| URS-08 | closed_loop tiene mayor masa cosechada y mayor viabilidad final que static; la diferencia en g/L se reporta. | `test_oq_03`. Medido 14 d: título 1.9243 frente a 1.9915 g/L (−3.37 %), masa 3.6424 frente a 3.5609 g (+2.29 %), viabilidad 88.98 frente a 88.22 %. 21 d: 2.7265 frente a 2.4946 g/L (+9.30 %), masa +15.70 %, viabilidad 39.86 frente a 34.41 %. |
| URS-09 | `high_shear_alarm` se dispara cuando `power_density_W_m3` > 47.6 W/m³ OR `sparge_vvm` > 0.15 vvm; la cinética no responde a P/V ≤ 100 W/m³; sparge > 0.15 vvm baja título y viabilidad. | `test_oq_04b`. Medido (closed_loop): P/V 60 y 100 W/m³ dan el mismo título que 30 W/m³ (1.9243 g/L); sparge 0.22 vvm da 1.2354 g/L y 88.73 %. |
| URS-10 | El mismo umbral (47.6 W/m³ OR 0.15 vvm) se aplica a toda escala de 0.25 L a 15,000 L; la función no recibe la escala. | Aserción de la alarma con el umbral único (`test_oq_04`, `test_oq_04b`). |
| URS-11 | `cip_velocity_compliant` es True solo con velocidad ≥ 1.52 m/s (no hay aborto). | Aserciones del indicador: True en 1.52 m/s; False en 1.51, 1.0 y 0.0 m/s (`test_oq_04`). |
| URS-12 | `sip_sterile_compliant` es True solo con F0 ≥ 15 min y todas las T ≥ 121.1 °C (no hay compuerta de liberación). | Aserciones del indicador (`test_oq_04`): True con F0 = 15.0 min exactos a 121.1 °C; False con F0 < 15 min a 121.1 °C, con T < 121.1 °C y F0 ≥ 15 min (incluida una sola lectura baja) y con ambas fallas. |
| URS-13 | El punto central queda dentro y los bordes se señalan fuera del Design Space. | Aserción de clasificación de centro/bordes. |
| URS-14 | Se calcula la MKT; el amortiguamiento del virtual thermal buffer (VTB) reduce la amplitud de la excursión (sin reporte de excursiones). | Aserción del valor de MKT sobre el dataset de referencia. |
| URS-15 | Entradas de auditoría atribuibles, con marca de tiempo y con evidencia de manipulación (incluido el indicador `human_approved`); se calcula el Cpk; la capacidad solo se declara interpretable en control estadístico y con normalidad; TOST + Levene para equivalencia. | Aserciones de integridad del registro, de mutación de `human_approved`, de capacidad (`test_oq_08`) y de estabilidad y equivalencia (`test_oq_08b`): Gorsky n = 30 sin puntos fuera de control; TOST con margen 1.0 equivalente (p 0.0426) y con 0.5 no (p 0.9729) sobre los mismos datos que la prueba t declara distintos. |
| URS-16 | Constantes calibradas reproducibles (costo ≤ 1.01 × el de una calibración nueva); RMSE ≤ 2σ dentro de muestra en las seis variables y en VCD fuera de muestra; puntos fuera de muestra dentro de 2σ; switch de lactato gobernado por el estado; convergencia numérica; caída real de viabilidad a 21 d. | `test_oq_03d`, `test_oq_03f`, `test_oq_03g`. Valores en la sección 11. |

## 8. Resumen de riesgo y aseguramiento

Los 16 requisitos de usuario se clasifican como **High Process Risk** según
`02_FDA_CSA_Risk_Assessment_2026.md` y, por lo tanto, se verifican con **Robust Scripted Testing**.
Ningún requisito de usuario de este sistema cae en la categoría Not-High-Risk; las funcionalidades
Not-High-Risk (gráficas, UI) son funciones de la capa de presentación que no se corresponden con
ninguna URS y se aseguran con pruebas unscripted exploratorias y de error-guessing, como se documenta
en la sección 5.2 del documento 02 (y con las 17 pruebas de humo de `tests_app/`). Además,
`test_exploratory_10`, `test_exploratory_11` y `test_exploratory_12` son actividades de
error-guessing y sondeo de fronteras bajo el principio least-burdensome de la guía FDA CSA
(Feb 2026); complementan las pruebas scripted sobre `models.py`, `audit_trail_part11.py` y
`spc_six_sigma.py` sin reemplazarlas.

## 9. Declaración de integridad de la trazabilidad

- **Trazabilidad hacia adelante:** URS → módulo → riesgo → prueba está completa para URS-01 … URS-16.
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

**Registro de cambios de pruebas v1.4.0** (modelo calibrado de 6 estados; ninguna prueba se debilitó
para forzar un aprobado; cada cambio sigue a una ecuación nueva o a un hallazgo medido):

| Prueba | Cambio | Motivo |
|--------|--------|--------|
| `test_oq_03` | La regla de glucosa se verifica evento por evento y con un disparo validado 6 → 9 g/L; se retiró el tope de 6.5 g/L; URS-08 pasa a masa cosechada y viabilidad. | El bolo de Cell Boost aporta ~3 g/L de glucosa (Bionova midió 8.1 g/L); con la glucosa calibrada la regla 2 → 5 g/L no se dispara; el título en g/L baja por dilución (hallazgo reportado). |
| `test_oq_03b` | Seis especies (añade Xd y NH3), llenados 0.70 y 0.76, tres modos, `daily_pre_feed`. | Estados nuevos y protocolo Bionova. |
| `test_oq_03c` | Pico de lactato en los días 4–6 (antes: después del día 5). | Switch gobernado por el estado; Bionova mide el pico el día 5. |
| `test_oq_03d` | Reemplaza `test_oq_03d_lactate_profile_v131` por `test_oq_03d_lactate_switch_state_governed`. | El perfil v1.3.1 dependía de constantes no calibradas y del escalón térmico. |
| `test_oq_03e` | El llenado se pasa por `ProcessDescription.initial_fill_fraction`. | Campo nuevo validado (Tarea 2). |
| `test_oq_04b` | P/V alto dispara la alarma sin cambiar la cinética; solo el sparge penaliza. | Desacople alarma–cinética (A-Mab p.100 / Ma 2002). |
| `test_oq_06b` | Saturación del controlador sin hipoxia falsa, enriquecimiento con O2 e hipoxia real por DO real. | Se eliminó DO_eff = DO × ratio (doble penalización). |
| `test_oq_03f`, `03g`, `03h`, `08b` | Nuevas. | Convergencia y NH3, validación Bionova, dominio de sliders, estabilidad I-MR y TOST + Levene. |
| `test_exploratory_10` | Validadores cruzados y campos nuevos. | Tarea 2. |

**Ajustes de auditoría del Draft PR #5** (misma versión 1.4.0, antes del merge):

| Prueba | Cambio | Motivo |
|--------|--------|--------|
| `test_oq_03`, `03b`, `03c`, `03g` | El protocolo Bionova se escribe `mode="static"` con `glucose_feedback_in_static=True`; `03b` verifica además que no hay bolo el día de cosecha (14 d: 6 bolos; 12 d: 5). | `mode` vuelve a ser binario (Ajuste 1). |
| `test_oq_03g` | Ejecuta `compare_k_i_l_m_g_swap` y verifica su resultado documentado: B mejora cond(J), m_G identificable, μmax(34) en cota, regla de glucosa el día 12, lactato peor, `adopt_scenario_b` False. | Ajuste 2. |
| `test_oq_03h` | Esquinas de DO en 5 y 90 % (el slider empieza en el límite del esquema) y sensibilidad direccional (sparge, duración, día de cambio). | Ajuste 3. |
| `test_exploratory_10` | Rechaza `mode="bionova_baseline"` y verifica el contrato binario y el valor por defecto de la bandera. | Ajuste 1. |

## 11. Evidencia de calibración, identificabilidad y validación (v1.4.0)

Calibración: `run_parameter_calibration()` (`least_squares`, método TRF, Jacobiano de 3 puntos con
paso relativo 1e-3) sobre 60 puntos pre-feed de Stratyx 30 W/m³ (día 0 excluido), con residuos
divididos por la incertidumbre declarada. Desde el prior documentado converge en 17 evaluaciones a
un costo de 34.41 (SSR ponderada 68.81). Las constantes de `src/bioreactor_twin.py` son esa salida.

| Parámetro | Valor | Cotas | Estado | RSE (%) | Identificable |
|-----------|-------|-------|--------|---------|---------------|
| μmax(36.5 °C) (1/d) | 0.832867 | [0.65, 0.95] | interior | 10.9 | Sí |
| μmax(34.0 °C) (1/d) | 0.322098 | [0.10, 0.35] | interior | 18.7 | Sí |
| K_I,L (g/L) | 5.01088 | [5, 15] | NEAR_BOUND (inferior) | 65.5 | No: requiere pulsos de lactato de 2–6 g/L |
| G_BOOST_CONC (g/L) | 76.4406 | [55, 85] | interior | 3.8 | Sí |
| X_max (1e6 cél/mL) | 42.6493 | [20, 60] | interior | 10.5 | Sí |
| q_L,max (g/(1e9 cél·d)) | 0.285600 | [0, 1] | interior | 21.2 | Sí |
| q_NH3 (mmol/(1e9 cél·d)) | 0.0582430 | [0, 0.3] | interior | 6.3 | Sí |
| k_d,NH3 (1/(d·mM)) | 0.0177939 | [0, 0.2] | interior | 22.6 | Sí |
| qp(36.5 °C) (g/(1e9 cél·d)) | 0.0150130 | [0, 0.05] | interior | 13.9 | Sí |
| qp(34.0 °C) (g/(1e9 cél·d)) | 0.00888312 | [0, 0.05] | interior | 10.5 | Sí |

Ningún parámetro quedó AT_BOUND (sobre la cota); K_I,L quedó a 0.1 % del rango de su cota inferior.
Valores singulares del Jacobiano escalado J·diag(θ): 649.14, 77.58, 33.81, 27.57, 19.44, 17.41, 12.18,
7.16, 5.19, 1.63; cond(J) = 398.8. Pares con |r| > 0.90: μmax(36.5)–K_I,L (−0.979),
μmax(36.5)–q_L,max (−0.957), K_I,L–q_L,max (0.945), K_I,L–X_max (0.941), X_max–q_L,max (0.941),
μmax(36.5)–X_max (−0.940): el crecimiento máximo, la inhibición por lactato, la capacidad logística
y el consumo de lactato se compensan entre sí en este único experimento.

Cribado ampliado (16 parámetros libres, `run_parameter_calibration(free_parameters=...)`): SSR 63.11
(frente a 68.81 con 10), con μmax(34.0) y K_I,L AT_BOUND, K_I,NH3 AT_BOUND en 60 mM, y RSE > 50 % en
K_I,NH3 (523 %), m_G (74 %), k_d,basal (70 %), k_lisis (58 %) y k_d,NH3 (51 %). Los no identificables
(m_G, k_d,basal, k_lisis, K_I,NH3) se fijan en valores redondeados del rango típico CHO (0.05, 0.03,
1.0 y 20 mM; el cribado daba 0.041, 0.063, 2.25 y la cota de 60 mM, que los datos no distinguen).
Y_X/G = 3.0 y Y_L/G = 0.80 (RSE 27 % y 29 % en el cribado, valores 3.06 y 0.85) se fijan para mantener
10 parámetros libres. Ninguno de estos seis es un valor calibrado.

Validación (estado pre-feed del gemelo frente a Bionova; criterio RMSE ≤ 2σ):

| Condición | Variable | n | R² | RMSE | NRMSE (%) | RMSE/σ | Error día 14 | Cumple |
|-----------|----------|---|----|------|-----------|--------|--------------|--------|
| 30 W/m³ (dentro de muestra) | VCD (1e6 cél/mL) | 14 | 0.981 | 1.153 | 4.8 | 0.77 | +0.882 (+4.5 %) | Sí |
| 30 W/m³ | Viabilidad (%) | 7 | 0.623 | 1.418 | 19.0 | 0.71 | −2.329 (−2.6 %) | Sí |
| 30 W/m³ | Glucosa (g/L) | 14 | 0.891 | 0.681 | 9.9 | 1.36 | −0.624 (−28.4 %) | Sí |
| 30 W/m³ | Lactato (g/L) | 14 | 0.854 | 0.156 | 13.0 | 1.04 | −0.293 (−91.6 %) | Sí |
| 30 W/m³ | NH3 (mmol/L) | 7 | 0.917 | 0.978 | 10.6 | 1.22 | +1.183 (+11.3 %) | Sí |
| 30 W/m³ | Título (g/L) | 4 | 0.948 | 0.094 | 9.0 | 1.17 | +0.095 (+5.0 %) | Sí |
| 19 W/m³ (fuera de muestra) | VCD (1e6 cél/mL) | 5 | 0.750 | 2.759 | 18.1 | 1.84 | +3.482 (+20.2 %) | Sí |
| 19 W/m³ | Viabilidad día 14 (%) | 1 | — | 2.779 | — | 1.39 | −2.779 (−3.1 %) | Sí (2σ) |
| 19 W/m³ | Pico de lactato (g/L, día 5) | 1 | — | 0.109 | — | 0.73 | −0.109 (−7.5 %) | Sí (1σ) |
| 19 W/m³ | Lactato día 14 (g/L) | 1 | — | 0.173 | — | 1.15 | −0.173 (−86.5 %) | Sí (2σ) |
| 19 W/m³ | NH3 día 14 (mmol/L) | 1 | — | 1.183 | — | 1.18 | +1.183 (+11.3 %) | Sí (2σ) |
| 19 W/m³ | Título día 14 (g/L) | 1 | — | 0.111 | — | 1.39 | +0.111 (+5.9 %) | Sí (2σ) |

El R² de la viabilidad es bajo porque su varianza es pequeña (99 a 90.55 %); su RMSE es 0.71σ. El
error relativo del lactato del día 14 es grande porque el valor observado es pequeño (0.32 g/L). El
modelo no tiene efecto de P/V entre 19 y 30 W/m³, por lo que a 19 W/m³ repite la curva de 30 W/m³.

### 11.1 Experimento K_I,L fijo → m_G libre (auditoría, `compare_k_i_l_m_g_swap`)

Mismos datos, objetivo, solver y prior; 10 parámetros libres en ambos escenarios. A es la calibración
vigente (K_I,L libre, m_G fijo en 0.05). B fija K_I,L = 10.0 g/L (punto medio del rango CHO de
literatura de 5–15 g/L, por falta de lactato > 1.5 g/L en Bionova) y libera m_G en [0.03, 0.25].

| Parámetro | A: valor (estado, RSE) | B: valor (estado, RSE) |
|-----------|------------------------|------------------------|
| μmax(36.5) | 0.832867 (interior, 10.9 %) | 0.802235 (interior, 3.0 %) |
| μmax(34.0) | 0.322098 (interior, 18.7 %) | **0.35 (AT_BOUND superior)** |
| K_I,L | 5.01088 (**NEAR_BOUND**, 65.5 %) | 10.0 (fijo) |
| G_BOOST_CONC | 76.4406 (interior, 3.8 %) | 82.2171 (interior, 7.8 %) |
| X_max | 42.6493 (interior, 10.5 %) | 38.1368 (interior, 7.1 %) |
| q_L,max | 0.285600 (interior, 21.2 %) | 0.304419 (interior, 7.8 %) |
| q_NH3 | 0.0582430 (interior, 6.3 %) | 0.0584052 (interior, 6.2 %) |
| k_d,NH3 | 0.0177939 (interior, 22.6 %) | 0.0167158 (interior, 23.9 %) |
| qp(36.5) | 0.0150130 (interior, 13.9 %) | 0.0148634 (interior, 13.8 %) |
| qp(34.0) | 0.00888312 (interior, 10.5 %) | 0.00900473 (interior, 10.6 %) |
| m_G | 0.05 (fijo) | 0.0610219 (interior, 17.1 %) |

| Diagnóstico | A | B |
|-------------|---|---|
| SSR ponderada | 68.814 | 70.677 |
| cond(J) | 398.8 | 45.2 |
| Valores singulares | 649.14, 77.58, 33.81, 27.57, 19.44, 17.41, 12.18, 7.16, 5.19, 1.63 | 133.06, 44.71, 33.41, 23.91, 18.78, 16.08, 7.49, 6.32, 4.70, 2.95 |
| Pares con \|r\| > 0.90 | 6 (μmax(36.5), K_I,L, X_max y q_L,max entre sí; máx. \|r\| 0.979) | ninguno entre los 9 libres en el interior |
| Parámetros en cota | K_I,L (NEAR_BOUND) | μmax(34.0) (AT_BOUND) |
| G pre-feed mínima en día de alimentación | 2.007 g/L (día 12): no repone | 1.757 g/L (día 12): repone 0.16 mL; día 10: 2.52 g/L |

| Métrica | A | B | ¿Mantiene o mejora? |
|---------|---|---|---------------------|
| 30 W/m³ VCD: R² / RMSE | 0.9814 / 1.1530 | 0.9811 / 1.1634 | sí (dentro de tolerancia) |
| 30 W/m³ viabilidad | 0.6235 / 1.4178 | 0.7072 / 1.2503 | sí |
| 30 W/m³ glucosa | 0.8907 / 0.6812 | 0.8902 / 0.6827 | sí (dentro de tolerancia) |
| 30 W/m³ lactato | 0.8535 / 0.1558 | 0.8274 / 0.1691 | **no** |
| 30 W/m³ NH3 | 0.9167 / 0.9779 | 0.9183 / 0.9687 | sí |
| 30 W/m³ título | 0.9477 / 0.0936 | 0.9488 / 0.0926 | sí |
| 19 W/m³ VCD | 0.7500 / 2.7588 | 0.7839 / 2.5653 | sí |
| 19 W/m³ \|error\| viabilidad d14 | 2.779 | 2.247 | sí |
| 19 W/m³ \|error\| pico de lactato | 0.109 | 0.001 | sí |
| 19 W/m³ \|error\| lactato d14 | 0.173 | 0.176 | **no** (+1.5 %) |
| 19 W/m³ \|error\| NH3 d14 | 1.183 | 1.159 | sí |
| 19 W/m³ \|error\| título d14 | 0.111 | 0.117 | **no** (+5.2 %) |

Tolerancias de "mantiene": R² puede bajar hasta 0.005 y RMSE o error puntual subir hasta 1 %.
Regla de adopción: cond(J) mejora (sí), todas las métricas se mantienen o mejoran (no) y ningún
parámetro en cota (no). **B no se adopta; las constantes de `src/bioreactor_twin.py` siguen siendo
las de A y la elección queda pendiente del auditor.** Ninguno de los dos escenarios queda con todos
sus parámetros en el interior.

Diagnóstico de la cota de μmax(34): sin el punto digitalizado de VCD del día 7 (17.8e6 cél/mL), A da
μmax(34) = 0.296 y K_I,L = 6.39 (ambos en el interior, SSR 66.03) y B da μmax(34) = 0.308 y m_G =
0.0626 (en el interior, SSR 67.30). Sin el punto del día 8, ambos quedan en cota. La subida de 17.8 a
23.5e6 entre los días 7 y 8 (0.28 1/d netos ya a 34 °C, sin bolo en ese intervalo, frente a
0.21 1/d entre los días 6 y 7 a 36.5 °C tras corregir la dilución del bolo del día 6) es la que
empuja μmax(34) a la cota; en A, K_I,L = 5 compensa con alivio de la inhibición
por lactato. Antes de elegir, conviene revisar ese punto contra la figura original.

### 11.2 Barrido del día de cambio térmico (constantes vigentes, protocolo Bionova)

| Día de cambio | VCD pico (1e6 cél/mL) | Viabilidad final (%) | NH3 final (mM) | Título final (g/L) | Masa cosechada (g) |
|---------------|-----------------------|----------------------|----------------|--------------------|--------------------|
| 4 | 20.086 | 92.89 | 8.801 | 1.3424 | 0.3258 |
| 7 (Bionova) | 23.963 | 88.22 | 11.683 | 1.9915 | 0.4833 |
| 10 | 30.454 | 86.04 | 13.069 | 2.6499 | 0.6467 |
| 14 (sin cambio) | 30.505 | 85.04 | 13.800 | 3.4569 | 0.8456 |

Todas las columnas son monótonas en el día de cambio. Enfriar antes modera el crecimiento y el NH3
y sostiene la viabilidad, como en NISTCHO; con qp(36.5) > qp(34.0) también baja el título. Solo el
día 7 tiene datos; las otras filas son extrapolación (documento 01, URS-02).

### 11.3 Convergencia numérica

Convergencia (`check_numerical_convergence`, error máximo relativo a la magnitud de cada serie):
RK45 1e-6 frente a RK45 1e-9: 1.24e-6; frente a Radau 1e-9: 1.24e-6; RK45 1e-9 frente a Radau 1e-9:
8.4e-9; Euler dt = 0.1 d (esquema de v1.3.2) frente a RK45 1e-9: 8.4e-2.

## Historial de versiones

Historial de versiones del documento. Las versiones son las del software (`src/__init__.py`); ver `CHANGELOG.md`.

| Versión | Fecha | Resumen |
|---------|-------|---------|
| 1.1.2 | 2026-11-08 | f34af71 y f2a64d1: trazabilidad de 13 pruebas OQ (en inglés). |
| 1.2.0 | 2026-11-10 | 98ffe46: traza de `test_oq_01` y `test_oq_09b`. |
| 1.3.0 | 2026-11-11 | 664efca: traducción al español. 6d8c509: trazas de `test_oq_03b`, `03c`, `04b` y `06b`. |
| 1.3.1 | 2026-11-11 | fd01ad7: trazas de `test_oq_03d` y `03e`. e6857b3: valores medidos de DO actualizados. |
| 1.3.2 | 2026-11-14 | b0fa17d y 99116f9 (Bloques 1 y 2): textos alineados con el código y la evidencia bibliográfica; versión del documento alineada con el software; historial añadido. cb5a484 (Bloque 3): casos negativos y de frontera de `test_oq_04` (ya no pendientes). 9c9ab7d (Bloque 4): kLa medido por escala (URS-06, `test_oq_05b`) y valores de DO 85 %. |
| 1.4.0 | 2026-11-20 | URS-16, NFR-06 y NFR-07; `model_validation.py` y dataset Bionova; 24 pruebas OQ (nuevas `test_oq_03f`, `03g`, `03h`, `08b`; `03d` reemplazada; `03`, `03b`, `03c`, `03e`, `04b`, `06b` y `test_exploratory_10` revisadas, sección 10); sección 11 con la evidencia de calibración, identificabilidad y validación. Ajustes de auditoría del PR #5: `mode` binario con `glucose_feedback_in_static`, experimento K_I,L → m_G (11.1, no adoptado), barrido del día de cambio (11.2), DO 5–90 % y sensibilidad direccional en `test_oq_03h`. |

*Fin del documento RTM-BRX-001.*
