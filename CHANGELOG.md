# Changelog

Todos los cambios relevantes de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog 1.1.0](https://keepachangelog.com/es-ES/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/). La versión del software es
`__version__` en `src/__init__.py`. Desde 1.3.2 la cabecera de versión de docs/01, 02, 03 y 05
sigue la versión del software, y cada documento lleva al final su historial de versiones.

El repositorio tiene tags de git hasta `v1.1.2` (`v1.0.0`, `v1.1.0`, `v1.1.1`, `v1.1.2`). Las
versiones 1.2.0 a 1.3.1 no tienen tag y enlazan a sus commits de cierre; desde `v1.3.2` se
retoman los tags anotados. Entre 1.1.2 y 1.3.1 `__version__` no se actualizó y quedó en
`1.1.2` hasta la versión 1.3.2.

## [Unreleased]

## [1.4.0] - 2026-11-20

Candidato de release en la rama `feat/v1.4.0-mechanistic-validation` (Draft PR hacia `main`). El tag
`v1.4.0` se crea solo después de la auditoría externa. Modelo mecanístico calibrado contra Bionova
NISTCHO (2026), validado fuera de muestra y verificado numéricamente en todo el dominio de los
sliders, con el marco ASME V&V 40 / FDA CSA. `evaluate_amab_design_space`, el payload SHA-256 de
`audit_trail_part11.py` y las ecuaciones de `thermal_vtb_mkt.py` no cambian.

### Added
- `data/bionova_nistcho_2026.json`: protocolo exacto y valores del día 14 impresos (`printed_exact`,
  pp. 3-4 y p.10), series digitalizadas de las Figs. 1-4 (`digitized_figure_approx`, con
  incertidumbre declarada) para Stratyx 30 W/m³ (calibración) y 19 W/m³ (validación fuera de
  muestra), y muestreo `pre_feed_daily`.
- `src/model_validation.py`: `load_bionova_reference_dataset`, `bionova_process_description`,
  `run_parameter_calibration` (`least_squares` TRF, 10 parámetros libres, 60 puntos),
  `compute_validation_metrics` (R², RMSE, NRMSE, error del día 14), `compute_jacobian_identifiability`
  (valores singulares, cond(J), pares |r| > 0.90, RSE) y `check_numerical_convergence`.
- Gemelo de 6 estados (Xv, Xd, G, L, NH3, título) más volumen, integrado por tramos entre eventos con
  `solve_ivp` RK45 (rtol 1e-6, atol 1e-9) y respaldo automático Radau; `daily_pre_feed` (estado
  exacto antes de cada bolo), series de NH3, células muertas, DO real, saturación del controlador y
  fracción de O2 requerida; diagnóstico del solver.
- Amonio: producción específica, inhibición K_I_NH3/(K_I_NH3 + NH3), muerte por encima de 5 mM y
  dilución exacta en cada bolo. Lisis de células muertas.
- `compute_dissolved_oxygen_state` y `compute_hydrodynamic_stress` en `bioreactor_twin.py`;
  `CHOKineticParameters`, `CALIBRATED_KINETICS`, `CALIBRATED_PARAMETER_NAMES` y `PARAMETER_BOUNDS`.
- `Y_O2_AIR`, `C_STAR_PURE_O2_MMOL_L` y el argumento `o2_mole_fraction` (por defecto aire) en
  `compute_scale_up_engineering`, con las claves `o2_mole_fraction` y `c_star_gas_mmol_L`.
- `ProcessDescription`: validadores cruzados (`glucose_min_threshold_g_L < glucose_refill_target_g_L`,
  `temp_shift_day <= duration_days`), `initial_fill_fraction` (0.70 por defecto, 0.20–0.95),
  `o2_enrichment_enabled` (True), `max_o2_mole_fraction` (1.0) y el modo `bionova_baseline`.
- `spc_six_sigma.py`: `n_out_of_control_points`, `in_statistical_control` y
  `capability_assumptions_met` en `compute_process_capability`; `compare_bioreactor_equivalence_tost`
  (TOST de Schuirmann con Welch, IC 90 %, Levene).
- Pruebas OQ `test_oq_03f_rk45_convergence_and_nh3_decline`, `test_oq_03g_bionova_validation_fit_and_oos`,
  `test_oq_03h_slider_domain_physical_stability` y `test_oq_08b_spc_control_stability_and_tost_equivalence`
  (24 pruebas OQ en total).
- `tests/conftest.py`: `pytest_sessionstart` vacía la lista de resultados al inicio de cada sesión.
- Tablero, pestaña 1: gráficas de NH3 y de DO real con avisos de saturación del controlador frente a
  hipoxia real, slider de duración (5–21 d), interruptor de enriquecimiento con O2 y bloque de
  validación contra Bionova (puntos impresos y digitalizados sobre las curvas, tabla de R² y RMSE).
  Pestaña 4: estabilidad I-MR y equivalencia TOST + Levene con margen editable. Pestaña 2: el aviso
  de oxígeno insuficiente muestra el OTR con O2 puro.
- `tests_app`: 4 pruebas nuevas (NH3 y DO real, bloque Bionova, duración y ajuste del cambio
  térmico, TOST y estabilidad); 17 pruebas en total, todas con `DeprecationWarning` como error.
- URS-16 (credibilidad del modelo), NFR-06 (estabilidad numérica) y NFR-07 (desempeño); sección 9 de
  docs/02 (ASME V&V 40) y sección 11 de docs/03 (evidencia de calibración y validación); Ref. 21
  (ASME V&V 40-2018) en docs/05 y README.
- Nota documental en `VTB_CALIBRATION_TABLE` sobre la anomalía física del rótulo "300 mL (Bulk)"
  (tau ≈ 35.2 h frente a ≈ 2.2 h de "600 mL"); valores y lógica sin cambios.

### Changed
- `__version__` pasa a `1.4.0`; docs/01, 02, 03 y 05 a la versión 1.4.0 con su historial.
- Parámetros calibrados (antes supuestos): μmax(36.5) 0.832867 1/d, μmax(34.0) 0.322098 1/d,
  K_I_L 5.01088 g/L (antes 2.5), G_BOOST_CONC 76.4406 g/L (antes 12), X_max 42.6493e6 cél/mL,
  q_L,max 0.2856, q_NH3 0.058243, kd_NH3 0.0177939, qp(36.5) 0.015013, qp(34.0) 0.00888312.
- Lactato: producción de desborde ligada al flujo glucolítico de crecimiento y consumo reprimido por
  la fracción de crecimiento máximo; el pico pasa del día 7 (escalón térmico) al día 5 y el lactato
  baja a 0.53 g/L el día 7, también con el cambio térmico en los días 10 o 14.
- Oxígeno: se eliminó DO_eff = DO × ratio y la doble penalización por ratio. El DO real sale de
  C_L = min(C_sp, max(0, C*_max − OUR/kLa)) con enriquecimiento de O2; f_do depende solo del DO
  real (exactamente 1.0 desde 15 %, K_DO 1.5 %), con efecto Pasteur bajo 15 % y muerte hipóxica bajo
  10 %. Límite inferior de `do_setpoint_pct`: 5 % (antes 10 %).
- Cizalla: la alarma conservadora de 47.6 W/m³ OR 0.15 vvm no entra en la cinética; las ecuaciones
  penalizan el burbujeo sobre 0.15 vvm y el impulsor solo sobre 476 W/m³ (fuera del esquema). Se
  retiró el factor `fPV` (1.08 a ≥ 30 W/m³), sin fuente y contradicho por Bionova (1.896 frente a
  1.88 g/L entre 30 y 19 W/m³).
- Tren de bolos: sin bolo el día de cosecha (los días de alimentación < duración).
- Pruebas revisadas bajo control de cambios (docs/03, sección 10): `test_oq_03`, `03b`, `03c`, `03e`,
  `04b`, `06b`, `test_exploratory_10`; `test_oq_03d_lactate_profile_v131` se reemplazó por
  `test_oq_03d_lactate_switch_state_governed`.
- URS-06, 07, 08, 09 y 15 actualizados; URS-08 pasa a exigir la ventaja en masa cosechada y viabilidad
  y a reportar la diferencia en g/L sin forzar su signo.
- Tablero: la re-ejecución OQ copia también `data/`; textos de P/V, sparge y DO alineados con el
  modelo nuevo.

### Fixed
- Hipoxia falsa a DO 85 % con aire (v1.3.2: f_do 0.545 con un DO físico de ~72 %).
- Techo artificial de 14.7e6 cél/mL a DO 30 % por la fuerza impulsora solo con aire.
- `P/V` de 50–60 W/m³ ya no recorta qp (v1.3.2: −24 % de título a 60 W/m³).
- Integrador: el Euler explícito de v1.3.2 (dt 0.1 d, con recorte de positividad) se reemplazó por
  RK45/Radau; aplicado al modelo nuevo, ese Euler tiene un error máximo de 8.4 % frente a la
  referencia (lactato), y RK45 de 1.24e-6.

### Hallazgos reportados sin maquillar ecuaciones
- A 14 d el lazo cerrado no supera a la receta estática en g/L (−3.37 %), por dilución; sí en masa
  (+2.29 %) y viabilidad (+0.76 puntos). A 21 d: +9.30 % en g/L y +15.70 % en masa.
- Con la regla 2 → 5 g/L la reposición de glucosa no llega a dispararse en el modelo (la glucosa
  pre-feed mínima en día de alimentación es 2.007 g/L); en Bionova la glucosa pre-feed de los días
  10 y 12 (1.2 y 1.9 g/L) queda bajo el disparo.
- K_I_L no es identificable (RSE 65.5 %, cerca de su cota inferior). μmax(36.5), K_I_L, X_max y
  q_L,max son colineales (|r| 0.94–0.98).
- El modelo no tiene efecto de P/V entre 19 y 30 W/m³ y sobrestima la VCD tardía a 19 W/m³
  (+3.48e6 cél/mL el día 14), dentro del criterio de 2σ para la serie.
- Lactato tardío por debajo de lo medido (0.03 frente a 0.2–0.3 g/L).
- No se encontró mojibake ni BOM: todos los archivos versionados (y la historia de git) son UTF-8
  válido sin BOM. Lo que se ve como mojibake es UTF-8 correcto leído como Windows-1252 (por ejemplo,
  la «ó» se guarda como los bytes C3 B3 y un visor en Windows-1252 los muestra como dos caracteres).

## [1.3.2] - 2026-11-14

Incluye b0fa17d y 99116f9 (Bloques 1 y 2: textos, versión, CHANGELOG y CI), cb5a484 (Bloque 3:
casos negativos de `test_oq_04`, constantes deduplicadas y banda muerta de pH explícita) y
9c9ab7d (Bloque 4: kLa medido por escala de A-Mab Tabla 3.22, rótulo 300 mL del VTB y QMSR).
A DO 10 y 30 % las métricas del gemelo son idénticas a las de 1.3.1 (DO 30 %, 2.0 L: static
1.0537 g/L / 80.54 %, closed_loop 1.2189 g/L / 90.55 %); a DO 85 % cambian por el kLa medido
(ver "Changed").

### Added
- `CHANGELOG.md` en la raíz del repositorio.
- La CI de GitHub Actions corre también la prueba de humo del tablero (`tests_app/`), en un
  paso separado de la suite OQ (`tests/`).
- README: versión del software, comando para `tests_app` y nota sobre lo que corre la CI
  (Python 3.11; la CI no publica el log OQ).
- docs/01, 02, 03 y 05: tabla de historial de versiones al final de cada documento.
- `AMAB_MEASURED_KLA_H_INV` y `measured_kla_for_volume` en `src/amab_design_space.py`: kLa
  medido por escala de A-Mab Tabla 3.22 (p.105): 2 L 10 (modelo estándar scale-down;
  caracterización 2 L 8–17), 500 L 8, 1,000 L 10, 5,000 L 10, 15,000 L 20, 25,000 L (Future)
  20 h⁻¹. Argumento opcional `measured_kla_h_inv` en `compute_scale_up_engineering`; las
  fórmulas de OUR, OTR y suficiencia no cambian.
- Tablero, calculadora: tabla de kLa medido por escala y texto que muestra que en 15,000 L la
  correlación y el valor medido coinciden en 20.00 h⁻¹.
- `test_oq_04`: casos de frontera y de falla de URS-11 y URS-12. Velocidad de CIP 1.52 m/s
  cumple y 1.51 / 1.0 / 0.0 m/s no cumplen; SIP con F0 = 15.0 min exactos a 121.1 °C cumple;
  F0 < 15 min, temperatura < 121.1 °C (también una sola lectura) y ambas fallas no cumplen.
  La suite sigue en 20 pruebas OQ.
- Tablero, panel de pH: texto con el set-point, la banda muerta y los umbrales de CO2 y base.
- `tests_app`: prueba 13, `test_ph_deadband_slider_drives_split_range_panel` (AppTest): con
  banda muerta 0.10 el texto muestra los límites 7.10 y 6.90, y con pH 7.15 la válvula de CO2
  abre 7.50 %, sin excepciones. `tests_app/` pasa de 12 a 13 pruebas (33 en total con las
  20 de `tests/`).

### Changed
- `__version__` pasa de `1.1.2` a `1.3.2`.
- Cabecera de versión de docs/01 (antes 2.1) y docs/02, 03 y 05 (antes 1.0) alineada con 1.3.2.
- Tablero: el respaldo del log OQ dice que el log se genera localmente y se verifica en CI.
- README y tablero (SPC): nota sobre la unidad lb/in impresa en Gorsky, Tabla 6-2
  (dimensionalmente lbf·in; observación del repo).
- `0.5 mL/min / 190 mL = 0.00263 vvm (Bionova, Ref. 2, pp. 3-4)` explícito en `models.py`,
  README y docs/05.
- Comentario de `test_oq_08`: 0.42 es la referencia de Gorsky Fig. 6.5 (p.130) y 0.43 el
  valor que calcula el repositorio con la Tabla 6-2.
- F0: nota de que 121.1 °C = 250 °F es la referencia convencional con z = 10 °C y que la
  fuente farmacéutica no está en la bibliografía (docs/01 y `bioreactor_twin.py`).
- `models.py`: los límites de entrada ya no se describen como rangos validados.
- Alineación de textos con el código y con la evidencia bibliográfica (b0fa17d), solo en
  documentos, docstrings, comentarios y etiquetas del tablero:
  - URS-09/10 y RTM: un solo umbral de cizalla en todas las escalas. 47.6 W/m³ es el P/V
    máximo demostrado aceptable a 2 L (A-Mab Tabla 3.22), criterio conservador y no umbral de
    daño; 0.15 vvm es un supuesto de modelado. Se retiró la "geometría por escala".
  - URS-07: la reposición se evalúa en cada día de alimentación con la glucosa pre-feed
    (como Bionova).
  - URS-02: el cambio de temperatura es un escalón, no una rampa.
  - URS-11/12/14/15 y NFR-05: describen solo lo que hace el código (calcula indicadores y
    registra en el Audit Trail cuando se pasa un logger); no hay abortos, bloqueos ni reportes
    de excursión.
  - kLa: forma de A-Mab Ec. 4 (p.101), anclada en el punto de 15,000 L (Tabla 3.22, kLa
    medido 8–20 h⁻¹); el coeficiente 80.14 se recalibró en el repositorio. En 0.25 L y 2 L la
    ley es una extrapolación. Se retiraron "Van't Riet" y el rango "validado 500–25,000 L".
  - Temperatura: el perfil 36.5 → 34 °C en el día 7 viene de Bionova (NISTCHO, CHO-K1); la
    fase a 36.5 °C queda fuera del Design Space de A-Mab (34–36 °C) y dentro de su DoE
    (34–37 °C).
  - Rotulados como supuestos de modelado no calibrados: banda de DO de 20 %, anclas de
    mu_max/qp, C* = 0.210 mmol/L y 0.15 vvm.
  - Título de la guía FDA CSA unificado en docs/02, `tests/conftest.py` y docs/04.
  - VTB = virtual thermal buffer (Rusnack) en docs/01 y RTM.
  - RTM: `test_oq_05b` se traza a URS-06; categoría de `test_exploratory_10` alineada con
    `conftest.py`. docs/02 y RTM marcan como pendientes los casos de frontera y de falla de
    `test_oq_04` (implementados luego en cb5a484; ver sección Added).
  - docs/05: corregida la frase sobre citas por número y la correspondencia de la Ref. 2.
- Gemelo: kLa = kLa medido de la columna inmediatamente inferior al volumen (2 a < 500 L 10,
  500 L 8, 1,000 L 10, 5,000 L 10, ≥ 15,000 L 20 h⁻¹; por encima de 25,000 L, 20 es una
  extrapolación). Por debajo de 2 L (0.25 L de Bionova, 190 mL) se usa 10 h⁻¹ del modelo
  estándar de 2 L como proxy (supuesto de modelado). Antes era la correlación a Vs 0.015 m/s y
  el P/V de la corrida (20.56 h⁻¹ a P/V 30). P/V ya no afecta el suministro de O2; solo la
  productividad (fPV) y la cizalla.
- Métricas a DO 85 % (2 L): static 1.0469 → 0.5943 g/L, 80.55 → 74.38 %, 1.8719 → 1.0626 g;
  closed_loop 1.0734 → 0.5765 g/L, 90.37 → 80.74 %, 2.0700 → 1.1030 g. Con kLa 10 h⁻¹ el
  OTR cae a 0.315 mmol/L/h y f_do limita qp. closed_loop queda por debajo de static en g/L
  porque su mayor volumen de alimentación (1.9133 frente a 1.7881 L finales) diluye la
  concentración y su mayor densidad celular baja algo más el f_do medio (0.726 frente a
  0.752); cosecha más masa (1.1030 frente a 1.0626 g). A DO 10 y 30 % no hay cambios.
- Tablero, calculadora: los presets corresponden 1:1 con las columnas de la Tabla 3.22 (2 L,
  500 L, 1,000 L, 5,000 L, 15,000 L, 25,000 L Future) y usan su kLa medido; la correlación
  solo se usa en "Personalizado". Se quitaron los presets de 0.25 L y 2,000 L, el chip de
  rango 500–25,000 L y el aviso de extrapolación en 0.25 L.
- Tablero: la alarma de oxígeno insuficiente pasa de error rojo a aviso del modelo, que aclara
  que el déficit viene de C* = 0.210 mmol/L (solo aire, sin O2 puro) y qO2 = 0.10 pmol/cél/h,
  supuestos sin fuente, mientras A-Mab Tabla 3.23 (p.106) demostró 18–30e6 cél/mL en 2 L y
  24e6 en 5,000 L. A VCC 15e6 y DO 30 % aparece en 2, 500, 1,000 y 5,000 L.
- `test_oq_05b`: verifica los seis kLa medidos (8–20 h⁻¹), el ancla de la correlación
  (20.0 h⁻¹ en 15,000 L), la búsqueda por columna y el kLa del gemelo a 0.25 L; ya no usa las
  esquinas con banda 8–22 h⁻¹. `test_scale_presets_and_amab_mode` admite el aviso de oxígeno
  solo en 2, 500, 1,000 y 5,000 L y comprueba el kLa de cada preset.
- VTB: la clave `"300 L (Bulk)"` pasa a `"300 mL (Bulk)"`, como la rotula Rusnack; los valores
  (alpha 0.002, tau 35 h) y la lógica térmica no cambian, y `"300 L (Bulk)"` queda como alias.
- docs/02: 21 CFR Part 820 pasa de QSR a QMSR (vigente desde 2026-02-02; incorpora ISO
  13485:2016 por referencia y retira el § 820.70), con cita de la guía FDA CSA, nota 3, p.2.
- Tablero: `AMAB_REF_VS_M_S` y `C_STAR_O2_MMOL_L` se importan de `src/amab_design_space.py`
  en lugar de duplicarse; el valor de P/V del preset (26.0 W/m³) sigue local porque `src/` no
  lo define.
- Tablero, panel de pH: el controlador split-range lee `ProcessDescription.ph_setpoint` y la
  banda muerta del slider, pasada explícitamente (antes el set-point 7.0 estaba fijo en el
  código). Los sliders de pH medido y de banda muerta arrancan en los valores por defecto de
  `ProcessDescription`. Se documenta que el pH solo
  gobierna ese controlador y no tiene efecto cinético en el gemelo.
- docs/02 y RTM: los casos de frontera y de falla de `test_oq_04` ya no figuran como pendientes.
- Docstrings y comentarios actualizados en `src/bioreactor_twin.py`, `src/__init__.py`,
  `tests/test_csa_oq_validation.py` y `tests_app/test_dashboard_smoke.py` (ley cinética con
  sigma_shear y acople del DO, indicadores en lugar de abortos, número de puntos según
  `duration_days`, regla de glucosa pre-feed, set-points "por defecto" en lugar de "validados").

### Removed
- Tablero: claves de paleta sin uso `heat_no` y `heat_yes` (el mapa del Design Space usa su
  escala binaria propia).

## [1.3.1] - 2026-11-11

Incluye fd01ad7 y dos commits posteriores sin cambio de `__version__` (e6857b3 y 14cdd59).
Las etiquetas "v1.3.1" de README, docstrings y pruebas se refieren a este estado del modelo.

### Added
- Acople del oxígeno disuelto con la cinética del gemelo (fd01ad7): kLa_eff con la misma ley
  de `compute_scale_up_engineering`, OTR_cap, OUR, ratio de suministro y DO_eff; reducción de
  mu y qp, aumento del rendimiento de lactato (efecto Pasteur) y muerte por hipoxia.
- `bolus_clipped_alarm`, `n_bolus_clipped` y `clipped_volume_L` cuando un bolo no cabe en el
  recipiente (fd01ad7).
- El slider de set-point de DO del tablero alimenta las dos corridas del gemelo (fd01ad7).
- Pruebas `test_oq_03d_lactate_profile_v131` y `test_oq_03e_bolus_clipped_alarm`
  (20 pruebas OQ en total).
- Tablero: la ecuación de kLa se muestra a partir de las constantes de
  `src/amab_design_space.py` (14cdd59).

### Changed
- Constantes de lactato: `Y_LG_GROWTH` = 0.18 g/g (en lugar de 0.22) para situar el pico de
  lactato en la banda de 1.0–1.35 g/L del día 6–7 (fd01ad7). Es un supuesto de modelado, no
  un ajuste a datos (ver "Correcciones a mensajes de commit").
- Constantes de transferencia de oxígeno centralizadas en `src/amab_design_space.py` y nueva
  función `compute_kla_h_inv` (fd01ad7).
- Tablero: escala de color binaria para los CQA del Design Space (14cdd59).

### Fixed
- Factor de hipoxia C0-continuo `do_hypoxia_factor`, normalizado en 20 % de DO: vale
  exactamente 1.0 a partir de 20 % y no tiene saltos (e6857b3). Cambian los resultados a
  DO 10 % y 85 %; a DO 30 % son idénticos.

## [1.3.0] - 2026-11-11

Incluye 6d8c509. La traducción al español del paquete regulatorio (664efca) se publicó entre
1.2.0 y esta versión.

### Added
- Penalización continua por cizalla `sigma_shear` sobre kd y qp (6d8c509).
- Volumen inicial V0 = 0.70 × `vessel_volume_L`, recorte por capacidad del recipiente y
  `overfill_alarm` en `check_safety_interlocks` (6d8c509).
- Fuerza impulsora explícita del DO, C* × (1 − DO/100), con el argumento `do_percent` en
  `compute_scale_up_engineering`, y slider de set-point de DO en el tablero (6d8c509).
- Pruebas `test_oq_03b`, `test_oq_03c`, `test_oq_04b` y `test_oq_06b` (18 pruebas OQ en total).

### Changed
- Cinética de lactato continua: Y_L/G(T) y consumo con represión por glucosa y modulación
  anaplerótica, sin ventanas de G ni interruptores de tiempo (6d8c509).
- Textos del tablero y nota de carga ácida de lactato sobre el pH (6d8c509).
- docs/01, 02, 03 y 05 traducidos al español, con los términos técnicos en inglés (664efca).
  docs/04 se mantiene en inglés porque lo genera `tests/conftest.py`.

### Fixed
- La alarma de cizalla pasa de compuerta AND a OR: basta P/V > 47.6 W/m³ o
  sparge > 0.15 vvm (6d8c509).

## [1.2.0] - 2026-11-10

Incluye 98ffe46.

### Added
- Prueba `test_oq_09b_part11_human_approved_mutation_breaks_chain` (14 pruebas OQ en total).
- Parámetro `audit_logger` en el gemelo y en los interlocks para registrar eventos
  automáticos en el Audit Trail.
- Alias de volumen "300 L (Bulk)" para el VTB.

### Changed
- Ley cinética única para los modos `static` y `closed_loop`: mu, kd y qp dependen solo del
  estado, la temperatura y la cizalla; `mode` solo decide la dosificación.
- Balance de glucosa y lactato: Y_X_G = 1.80, M_G = 0.175, G_BOOST_CONC = 12 g/L y orden de
  alimentación (paso de Euler, luego G_pre_feed, luego bolo).
- URS-01 y URS-06: la regulación de temperatura y DO se delega al controlador local;
  `test_oq_01` reorganizada.
- Unidades de Gorsky (kp, lb/in), documentación del sparge y RTM de `test_oq_09b`.
- README y bibliografía con la evidencia por módulo.

### Fixed
- La reposición adaptativa de glucosa en `closed_loop` ahora se dispara.
- El indicador `human_approved` entra en el hash del Audit Trail de Part 11, así que mutarlo
  rompe la cadena.

## Correcciones a mensajes de commit

Los mensajes de commit no se reescriben (la historia de `main` es pública). Esta sección deja
constancia de lo que no describen bien:

- **e6857b3** ("C0-continuous DO hypoxia factor normalized at A-Mab 20% lower bound"): la
  banda de DO de 20 % no viene de A-Mab. Es un supuesto de modelado sin fuente. El umbral de
  20 % ya estaba en fd01ad7 y e6857b3 lo usó como punto de normalización. A-Mab operó la
  producción a 30–70 % de DO (Tabla 3.14) y usó 20–70 % solo en el seed N-1 (Tabla 3.7).
- **fd01ad7** ("CHO-K1 physiological lactate calibration"): las constantes de lactato
  (Y_L/G, q_L,cons,max, K_L, K_I_G, f_basal, K_anap) y de DO son supuestos de modelado, no
  calibrados contra datos experimentales. `Y_LG_GROWTH` = 0.18 se eligió para que el pico de
  lactato quedara en una banda objetivo, no por ajuste a mediciones.

[Unreleased]: https://github.com/alehernann/bioprocesos-PROJECT/compare/v1.3.2...main
[1.4.0]: https://github.com/alehernann/bioprocesos-PROJECT/compare/v1.3.2...feat/v1.4.0-mechanistic-validation
[1.3.2]: https://github.com/alehernann/bioprocesos-PROJECT/releases/tag/v1.3.2
[1.3.1]: https://github.com/alehernann/bioprocesos-PROJECT/commit/14cdd5984aab64df489fc8a920b0e71bb5bf7661
[1.3.0]: https://github.com/alehernann/bioprocesos-PROJECT/commit/6d8c509bb10fab29cdde5543e3fa96853a08e2e6
[1.2.0]: https://github.com/alehernann/bioprocesos-PROJECT/commit/98ffe461f73bc07484c172ac7d9f434b2fb48cc2
