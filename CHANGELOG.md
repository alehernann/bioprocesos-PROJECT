# Changelog

Todos los cambios relevantes de este proyecto se documentan en este archivo.

El formato sigue [Keep a Changelog 1.1.0](https://keepachangelog.com/es-ES/1.1.0/) y el
proyecto usa [Versionado Semántico](https://semver.org/lang/es/). La versión del software es
`__version__` en `src/__init__.py`. Desde 1.3.2 la cabecera de versión de docs/01, 02, 03 y 05
sigue la versión del software, y cada documento lleva al final su historial de versiones.

El repositorio no tiene tags de git; cada versión enlaza al commit correspondiente. Entre
1.1.2 y 1.3.1 `__version__` no se actualizó y quedó en `1.1.2` hasta la versión 1.3.2.

## [Unreleased]

Sin cambios en la cinética ni en las constantes numéricas del modelo. Las métricas del gemelo
no cambian (DO 30 %, 2.0 L: static 1.0537 g/L / 80.54 %, closed_loop 1.2189 g/L / 90.55 %).

### Added
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

## [1.3.2] - 2026-11-12

Sin cambios en ecuaciones, constantes ni lógica de `src/`. Las métricas del gemelo son
idénticas a las de 1.3.1 (DO 30 %, 2.0 L: static 1.0537 g/L / 80.54 %, closed_loop
1.2189 g/L / 90.55 %).

### Added
- `CHANGELOG.md` en la raíz del repositorio.
- La CI de GitHub Actions corre también la prueba de humo del tablero (`tests_app/`), en un
  paso separado de la suite OQ (`tests/`).
- README: versión del software, comando para `tests_app` y nota sobre lo que corre la CI
  (Python 3.11; la CI no publica el log OQ).
- docs/01, 02, 03 y 05: tabla de historial de versiones al final de cada documento.

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
    `test_oq_04`.
  - docs/05: corregida la frase sobre citas por número y la correspondencia de la Ref. 2.

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

[1.3.2]: https://github.com/alehernann/bioprocesos-PROJECT/commit/b0fa17dce67372ff27a32d673cf48408be48a792
[1.3.1]: https://github.com/alehernann/bioprocesos-PROJECT/commit/14cdd5984aab64df489fc8a920b0e71bb5bf7661
[1.3.0]: https://github.com/alehernann/bioprocesos-PROJECT/commit/6d8c509bb10fab29cdde5543e3fa96853a08e2e6
[1.2.0]: https://github.com/alehernann/bioprocesos-PROJECT/commit/98ffe461f73bc07484c172ac7d9f434b2fb48cc2
