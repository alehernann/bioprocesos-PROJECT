# 02 — Evaluación de riesgo FDA Computer Software Assurance (CSA) — 2026

| Campo | Valor |
|-------|-------|
| **ID del documento** | CSA-RA-2026-001 |
| **Título** | Evaluación de riesgo bajo FDA CSA para software de producción y del sistema de calidad |
| **Versión** | 1.4.0 |
| **Guía principal** | FDA *Computer Software Assurance for Production and Quality Management System Software*, CDRH/CBER/CDER, Feb 3, 2026 |
| **Normas de soporte** | ISO 13485:2016, 21 CFR Part 820 (QMSR, vigente desde 2026-02-02), GAMP 5 (2nd ed.), ASME V&V 40-2018 (credibilidad de modelos, por analogía), 21 CFR Part 11, EudraLex Annex 11, Draft Annex 22 (AI) |
| **Sistema evaluado** | Sistema de control del biorreactor CHO-K1 fed-batch (gemelo digital) |

---

## 1. Propósito

Esta evaluación de riesgo aplica el enfoque **FDA Computer Software Assurance (CSA)** al sistema de
control del biorreactor. CSA desplaza el énfasis desde la *Computer System Validation (CSV)*
exhaustiva y cargada de documentación hacia el **pensamiento crítico** y el **aseguramiento basado
en riesgo**: el esfuerzo se concentra donde una falla del software afectaría más directamente la
**calidad del producto**, la **seguridad del paciente** o la **integridad de los datos**.

La pregunta central de CSA para cada funcionalidad del software es:

> *"Si esta funcionalidad del software fallara o se comportara de forma incorrecta, ¿podría
> comprometer directamente la calidad del producto, la seguridad del proceso o la integridad de un
> registro de calidad?"*

- Si la respuesta es **sí**, la funcionalidad es **High Process Risk** y recibe **Robust Scripted
  Testing** (scripts paso a paso aprobados previamente, con resultados esperados y evidencia
  objetiva).
- Si la respuesta es **no**, la funcionalidad es **Not High Process Risk** y puede asegurarse con el
  método apropiado menos oneroso: **Unscripted Exploratory Testing**, **Ad-hoc Testing** o
  **Error-Guessing Testing**, con un registro de la actividad en lugar de evidencia completamente
  pre-escrita.

## 2. Base regulatoria e interpretación

### 2.1 FDA CSA (2026)
CSA promueve un enfoque de aseguramiento **least-burdensome** (el menos oneroso), proporcional al
riesgo. Respalda de forma explícita el **unscripted testing** (exploratorio, ad-hoc, error-guessing)
para funcionalidades de menor riesgo y reserva el **scripted testing** (limitado y robusto) para las
de mayor riesgo. La actividad de aseguramiento y su evidencia deben ser **proporcionales al riesgo**.

### 2.2 ISO 13485:2016
La cláusula 4.1.6 exige validar el software usado en el sistema de gestión de calidad con un enfoque
**basado en riesgo**, proporcional al riesgo asociado a su uso. Esto coincide directamente con los
pasos de uso previsto y determinación de riesgo de CSA.

### 2.3 21 CFR Part 820 (Quality Management System Regulation, QMSR)
Desde el 2 de febrero de 2026, 21 CFR Part 820 es la Quality Management System Regulation (QMSR), que
reemplaza a la Quality System Regulation (QSR). La QMSR incorpora ISO 13485:2016 por referencia y
retira el § 820.70, incluido el antiguo § 820.70(i) sobre validación del software de producción y del
sistema de calidad. El requisito equivalente es ahora la cláusula 4.1.6 de ISO 13485:2016 (sección
2.2). Fuente: guía FDA CSA (Feb 2026), nota 3, p.2.

## 3. Metodología de determinación del riesgo CSA

La evaluación sigue los cuatro pasos de CSA:

1. **Identificar el uso previsto** de cada funcionalidad del software.
2. **Determinar el riesgo** que la funcionalidad representa para el proceso/producto (High vs. Not-High Process Risk).
3. **Determinar la actividad de aseguramiento apropiada** (scripted vs. unscripted).
4. **Establecer el registro apropiado** (evidencia objetiva proporcional al riesgo).

### 3.1 Factores de riesgo considerados
- **Impacto directo en la calidad del producto** — ¿la funcionalidad controla un CPP o evalúa un CQA?
- **Impacto en la seguridad** — ¿la funcionalidad actúa como interlock de seguridad?
- **Impacto en la integridad de datos** — ¿la funcionalidad crea o modifica un registro de Part 11?
- **Detectabilidad** — ¿una falla sería evidente o silenciosa?
- **Propagación aguas abajo** — ¿un error se propaga hasta las decisiones de liberación?

## 4. Matriz de clasificación de riesgo

| # | Funcionalidad / función del software | Módulo | Uso previsto | Impacto de una falla | **Process Risk** | **Método de aseguramiento CSA** |
|---|-----------------------------|--------|--------------|----------------|------------------|--------------------------|
| 1 | **Set-points de control y lógica de actuación** (set-points de T y cambio del día 7, split-range de pH, set-point de DO con verificación OTR ≥ OUR, reposición adaptativa de glucosa) | `bioreactor_twin.py`, `models.py`, `amab_design_space.py` | Define los set-points de los CPP y la lógica de los actuadores del lote. | Lote fuera de especificación, falla de un CQA. | **High Process Risk** | **Robust Scripted Testing** |
| 2 | **Interlocks de seguridad** (cizalla P/V, velocidad de CIP, F0 de SIP) | `bioreactor_twin.py` | Previene el daño celular y asegura la eficacia de la limpieza y la esterilización. | Contaminación, liberación no estéril, pérdida de equipo o producto. | **High Process Risk** | **Robust Scripted Testing** |
| 3 | **Cálculo de MKT** (térmica de cadena de frío) | `thermal_vtb_mkt.py` | Determina si las excursiones de almacenamiento o transporte comprometen el producto. | Pérdida de potencia o estabilidad no detectada, disposición equivocada. | **High Process Risk** | **Robust Scripted Testing** |
| 4 | **Ecuaciones del Design Space** (centro/bordes de A-Mab) | `amab_design_space.py` | Define la región operativa aceptable multivariada (ICH Q8). | Operación fuera del espacio validado, incumplimiento regulatorio. | **High Process Risk** | **Robust Scripted Testing** |
| 5 | **Audit Trail** (21 CFR Part 11) | `audit_trail_part11.py` | Crea registros GxP atribuibles y con evidencia de manipulación. | Brecha de integridad de datos, pérdida de confiabilidad de los registros. | **High Process Risk** | **Robust Scripted Testing** |
| 6 | **Capacidad SPC / Six Sigma** (Cpk, intervalos de tolerancia, estabilidad I-MR, equivalencia TOST + Levene) | `spc_six_sigma.py` | Decisiones estadísticas de liberación y monitoreo sobre datos de proceso. | Conclusión de capacidad o de equivalencia incorrecta que alimenta la disposición. | **High Process Risk** | **Robust Scripted Testing** |
| 6b | **Gemelo mecanístico calibrado y su validación** (6 estados, solver RK45/Radau, calibración e identificabilidad) | `bioreactor_twin.py`, `model_validation.py`, `data/bionova_nistcho_2026.json` | Comparar estrategias de alimentación con un modelo calibrado contra Bionova NISTCHO (2026). | Una predicción no creíble podría orientar mal el desarrollo del proceso; un error numérico daría resultados no físicos. | **High Process Risk** | **Robust Scripted Testing** (verificación y validación, sección 9) |
| 7 | **Validación de entradas** (modelos tipados Pydantic) | `models.py` | Protege el núcleo High-Risk de entradas mal formadas. | Propaga datos erróneos a la lógica de control y de registros. | **High Process Risk** | **Robust Scripted Testing** |
| 8 | **Gráficas** (figuras Plotly) | capa de visualización | Representación visual de datos ya calculados y validados. | Solo cosmético o de presentación; los datos subyacentes no se afectan. | **Not High Process Risk** | **Unscripted Exploratory / Error-Guessing Testing** |
| 9 | **Diseño y navegación de la UI** (widgets de Streamlit) | capa de visualización | Ergonomía y presentación para el operador. | Incomodidad; sin impacto directo en calidad, seguridad o datos. | **Not High Process Risk** | **Unscripted Exploratory / Error-Guessing Testing** |

## 5. Justificación de cada clasificación

### 5.1 High Process Risk — Robust Scripted Testing

**Set-points de control y lógica de actuación.** THE SYSTEM envía los set-points de temperatura
validados y el cambio automático del día 7 (URS-01/02), acciona los actuadores split-range de pH con
dead-band (URS-03/04/05), envía el set-point de DO y verifica la suficiencia de la transferencia de
oxígeno OTR ≥ OUR (URS-06), y dosifica la reposición adaptativa de glucosa (URS-07/08). La regulación
de la temperatura y el DO medidos dentro de sus bandas operacionales se delega a los controladores
locales; aquí no se simula ni se califica ningún lazo PID de temperatura o de DO. Un error en estos
set-points o en la lógica de actuación cambia el estado físico del lote y puede sacar un Critical
Quality Attribute de especificación. Estas funcionalidades exigen scripts paso a paso aprobados
previamente (`test_oq_01`, `test_oq_02`, `test_oq_03`), con resultados esperados definidos y
evidencia objetiva conservada.

**Interlocks de seguridad.** La alarma de cizalla hidrodinámica (P/V > 47.6 W/m³ OR sparge > 0.15 vvm, URS-09/10;
47.6 W/m³ = P/V máximo demostrado aceptable a 2 L, A-Mab Tabla 3.22, criterio conservador, no umbral
de daño; 0.15 vvm = supuesto de modelado), el indicador de velocidad de CIP (≥ 1.52 m/s según ASME
BPE, URS-11) y el indicador de letalidad de SIP (F0 ≥ 15 min a ≥ 121.1 °C, URS-12) calculan los
indicadores y, cuando se les pasa un logger, registran los disparos en el Audit Trail; no abortan
ni bloquean ciclos. Son la última línea de defensa contra el daño celular, la limpieza
insuficiente y el producto no estéril. Una falla es catastrófica y a menudo silenciosa hasta que se
manifiesta como contaminación. Es obligatorio el robust scripted testing (`test_oq_04`).
`test_oq_04` cubre el caso nominal (cizalla alta, CIP bloqueado, velocidad de CIP = 1.52 m/s, SIP
conforme) y los casos de frontera y de falla: velocidad de CIP de 1.52 m/s (cumple) frente a 1.51,
1.0 y 0.0 m/s (no cumple); SIP con F0 = 15.0 min exactos a 121.1 °C (cumple); F0 < 15 min a
121.1 °C; temperatura < 121.1 °C con F0 ≥ 15 min (incluida una sola lectura baja); y ambas fallas a
la vez (no cumple). `test_oq_04b` cubre la frontera de la alarma de cizalla.

**Cálculo de MKT.** La Mean Kinetic Temperature (URS-14) gobierna las decisiones de disposición de
producto sensible a la temperatura. Un error de cálculo podría liberar material degradado o
descartar sin necesidad material en buen estado; ambos casos son de alto impacto. Se requiere
scripted testing contra datasets de referencia (`test_oq_06`).

**Ecuaciones del Design Space.** El A-Mab Design Space (URS-13) codifica la región aceptable
multivariada de ICH Q8. Una lógica errónea del punto central o de los bordes de falla podría
permitir operar fuera del espacio validado. Se requiere verificación scripted del centro y los
bordes (`test_oq_05`).

**Audit Trail.** El Audit Trail de 21 CFR Part 11 (URS-15) sostiene la confiabilidad de cada
registro GxP. Cualquier defecto es un defecto de integridad de datos. Se requiere scripted testing
de la atribuibilidad, la marca de tiempo y la evidencia de manipulación, junto con el guardrail de
AI del Annex 22 (`test_oq_09`) y la protección por hash del indicador `human_approved` (`test_oq_09b`).

**SPC / Six Sigma.** El cálculo de capacidad de proceso y de intervalos de tolerancia (metodología
de Gorsky) alimenta decisiones estadísticas de liberación y monitoreo. Un Cpk o unos intervalos de
tolerancia incorrectos corrompen las decisiones de calidad, por lo que se requiere scripted testing
(`test_oq_08`). Desde v1.4.0 la capacidad solo se declara interpretable si el proceso está en control
estadístico (regla 1 de Shewhart en la carta I-MR) y es normal, y la comparación entre biorreactores
dispone de una prueba formal de equivalencia (TOST + Levene; Gorsky 2020, p.131), porque una prueba t
no significativa no demuestra equivalencia (`test_oq_08b`).

**Gemelo mecanístico calibrado.** El gemelo de 6 estados (Xv, Xd, G, L, NH3, título más el volumen)
se integra por tramos con RK45 y cambio automático a Radau. Un error numérico (estado negativo, NaN,
pérdida de masa en un bolo) daría resultados no físicos de forma silenciosa, y una calibración no
documentada daría predicciones sin respaldo. Por eso la verificación del software (`test_oq_03b`,
`test_oq_03f`, `test_oq_03h`) y la validación del modelo frente a datos medidos (`test_oq_03g`) son
scripted; el marco de credibilidad se detalla en la sección 9.

**Validación de entradas.** Los modelos tipados Pydantic (`models.py`) son el filtro que impide que
datos mal formados lleguen al núcleo High-Risk. Aunque su función es defensiva, un hueco en la
validación propagaría datos erróneos a todas partes, por lo que se trata como High Process Risk.
Explorar entradas *inválidas* es complementario y lo cubre el unscripted
`test_exploratory_10_invalid_pydantic_inputs`, junto con `test_exploratory_11_audit_trail_requires_reason`
(error-guessing sobre razones de cambio inválidas en el Audit Trail) y
`test_exploratory_12_welch_ttest_identical_groups_not_significant` (caso de frontera de SPC con
grupos idénticos, es decir, diferencia de medias igual a cero, en la prueba t de Welch).

### 5.2 Not High Process Risk — Unscripted Exploratory / Error-Guessing Testing

**Gráficas.** Las figuras Plotly representan datos que los módulos High-Risk *ya* calcularon y
validaron. Un defecto de representación es cosmético: no cambia los datos del lote, las acciones de
control ni los registros. El aseguramiento apropiado y menos oneroso es el unscripted exploratory
testing y el error-guessing (¿se dibuja la gráfica?, ¿los ejes tienen etiqueta?, ¿maneja bien una
serie vacía?), con un registro de la actividad en lugar de un script completo aprobado previamente.

**Diseño y navegación de la UI.** Los widgets de Streamlit y la disposición de la página afectan la
ergonomía del operador, no la calidad del producto, la seguridad ni la integridad de los datos. Las
pruebas exploratorias y de error-guessing (recorrido por clics, interacciones de frontera,
comportamiento al redimensionar) son suficientes y proporcionales.

## 6. Asignación del esfuerzo de aseguramiento (principio CSA)

```
          Esfuerzo de aseguramiento ALTO
                 ▲
                 │   ┌─────────────────────────────────────┐
   Robust        │   │ Set-points, interlocks, MKT,         │
   Scripted      │   │ Design Space, Audit Trail, SPC,      │
   Testing       │   │ validación de entradas (Category 5)  │
                 │   └─────────────────────────────────────┘
                 │
   Unscripted    │        ┌───────────────────────────┐
   Exploratory / │        │ Gráficas, UI / navegación  │
   Error-Guessing│        │ (capa de presentación)     │
                 │        └───────────────────────────┘
                 ▼
          Esfuerzo de aseguramiento BAJO
```

La mayor parte del esfuerzo de validación se concentra a propósito en el núcleo High Process Risk de
código a la medida (GAMP Category 5), en línea con el principio least-burdensome de CSA.

## 7. Vínculo con las pruebas y la trazabilidad

- Las funcionalidades High Process Risk se corresponden con las pruebas OQ scripted `test_oq_01` a
  `test_oq_09` en `tests/test_csa_oq_validation.py`.
- Las funcionalidades Not-High-Risk y la exploración de entradas inválidas y de casos de frontera se
  corresponden con las pruebas unscripted `test_exploratory_10_invalid_pydantic_inputs`,
  `test_exploratory_11_audit_trail_requires_reason` y
  `test_exploratory_12_welch_ttest_identical_groups_not_significant`.
- La suite cubre 24 pruebas: 21 pruebas scripted (`test_oq_01` a `test_oq_09`, incluidas
  `test_oq_03b`, `test_oq_03c`, `test_oq_03d_lactate_switch_state_governed`, `test_oq_03e`,
  `test_oq_03f_rk45_convergence_and_nh3_decline`, `test_oq_03g_bionova_validation_fit_and_oos`,
  `test_oq_03h_slider_domain_physical_stability`, `test_oq_04b`,
  `test_oq_05b_amab_scale_up_kla_pilot_commercial_range`, `test_oq_06b`,
  `test_oq_08b_spc_control_stability_and_tost_equivalence` y
  `test_oq_09b_part11_human_approved_mutation_breaks_chain`) y 3 pruebas exploratorias
  (`test_exploratory_10` a `test_exploratory_12`).
- La trazabilidad completa hacia adelante y hacia atrás se mantiene en `03_RTM_Traceability_Matrix.md`.

## 8. Conclusión

Al aplicar FDA CSA (2026), ISO 13485:2016 y 21 CFR Part 820 (QMSR), los set-points de control y la lógica de
actuación, los interlocks de seguridad, el cálculo de MKT, las ecuaciones del Design Space, la
capacidad SPC, el Audit Trail, la validación de entradas y el gemelo mecanístico calibrado se
clasifican como **High Process Risk** y se verifican con **Robust Scripted Testing**; la credibilidad
del modelo se evalúa además con el marco de ASME V&V 40 (sección 9). Las gráficas y la UI se clasifican como **Not High
Process Risk** y se aseguran con **Unscripted Exploratory / Error-Guessing Testing**. Esta asignación
concentra el aseguramiento donde una falla afectaría más la calidad del producto, la seguridad y la
integridad de los datos.

## 9. Credibilidad del modelo mecanístico (ASME V&V 40 / FDA CSA)

ASME V&V 40-2018 (Ref. 21 del documento 05) se escribió para modelos computacionales de dispositivos
médicos; aquí se aplica por analogía al gemelo de bioproceso. FDA CSA gobierna el aseguramiento del
software (secciones 1 a 8). V&V 40 añade la pregunta de si el **modelo** es creíble para su uso, y
separa dos actividades que este paquete mantiene separadas:

- **Verificación del software (OQ):** ¿el código resuelve correctamente las ecuaciones documentadas?
- **Validación del modelo biológico:** ¿las ecuaciones calibradas reproducen datos medidos con la
  exactitud que pide el contexto de uso?

### 9.1 Pregunta de interés, contexto de uso y riesgo del modelo

| Elemento | Definición para este gemelo |
|----------|-----------------------------|
| Pregunta de interés | ¿Qué estrategia de alimentación (static, bionova_baseline, closed_loop) y qué set-points conviene probar primero en el laboratorio? |
| Contexto de uso | Cribado en desarrollo de proceso con NISTCHO (CHO-K1) en fed-batch de 14 d; los resultados se confirman siempre con un experimento. No se usa para liberar lotes ni para fijar especificaciones. |
| Influencia del modelo | Baja: la decisión final se toma con datos experimentales. |
| Consecuencia de una decisión errónea | Media: un mal cribado cuesta corridas de laboratorio; no llega al paciente. |
| Riesgo del modelo | Bajo a medio. |
| Meta de credibilidad | RMSE ≤ 2 × incertidumbre declarada en cada variable dentro de muestra y en VCD fuera de muestra; cada punto fuera de muestra dentro de 2 × su incertidumbre (`CREDIBILITY_RMSE_OVER_SIGMA_MAX` en `src/model_validation.py`). |

### 9.2 Actividades de credibilidad y evidencia

| Actividad (V&V 40) | Evidencia | Prueba |
|--------------------|-----------|--------|
| Verificación del código | Balance de masa exacto de Xv, Xd, G, L, NH3 y título en cada bolo; regla de glucosa evento por evento; balance de O2 cuasi estacionario; desacople alarma–cinética. | `test_oq_03b`, `test_oq_03`, `test_oq_06b`, `test_oq_04b` |
| Verificación del cálculo | RK45 (rtol 1e-6) frente a RK45 y Radau con rtol 1e-9: error máximo 1.24e-6 relativo a la magnitud de cada serie; RK45 1e-9 frente a Radau 1e-9: 8.4e-9; el cambio automático a Radau reproduce RK45; el Euler de v1.3.2 (dt 0.1 d) tiene error 8.4e-2 (lactato). | `test_oq_03f` |
| Robustez en el dominio de uso | 256 esquinas del dominio de los sliders: sin NaN ni Inf, concentraciones ≥ 0, viabilidad en [0, 100] %, V(t) ≤ recipiente; 5.1 ms de media y 15.8 ms de máximo por corrida. | `test_oq_03h` |
| Validación: comparador | Bionova Stratyx 30 W/m³ (calibración, 60 puntos pre-feed) y 19 W/m³ (fuera de muestra). | `test_oq_03g` |
| Validación: calibración e identificabilidad | 10 parámetros libres por `least_squares` (TRF); las constantes del código reproducen una calibración nueva desde el prior documentado; K_I_L no identificable. | `test_oq_03g` |
| Aplicabilidad | El comparador cubre NISTCHO, 0.25 L Stratyx, 14 d, DO 30 %, P/V 19–30 W/m³. Escalas, duraciones y set-points fuera de ese rango son extrapolación del modelo. | — |

### 9.3 Resultado frente a la meta de credibilidad

Dentro de muestra (30 W/m³) las seis variables cumplen la meta (RMSE/σ: VCD 0.77, viabilidad 0.71,
glucosa 1.36, lactato 1.04, NH3 1.22, título 1.17). Fuera de muestra (19 W/m³) la serie de VCD cumple
(RMSE/σ 1.84) y los cinco puntos quedan dentro de 2σ. El detalle está en el documento 03, sección 11.

### 9.4 Limitaciones conocidas (se reportan, no se corrigen ajustando ecuaciones)

- K_I_L no es identificable con lactato ≤ 1.4 g/L (RSE 65.5 %, cerca de la cota inferior de 5 g/L).
- El modelo no tiene un efecto de P/V entre 19 y 30 W/m³: a 19 W/m³ predice la misma curva que a
  30 W/m³ y sobrestima la VCD tardía (+3.5e6 cél/mL el día 14).
- El lactato tardío queda por debajo de lo medido (0.03 frente a 0.2–0.3 g/L entre los días 8 y 14) y
  el consumo tardío de glucosa también, por lo que la regla 2 → 5 g/L no se dispara en el modelo.
- Los parámetros de hipoxia, cizalla por burbujeo, inanición, lisis, rendimientos fijos y K_I_NH3 son
  supuestos no calibrados (no hay datos en la bibliografía del proyecto que los activen).
- Sin aminoácidos ni otros nutrientes, los bolos extra de Ark solo diluyen y aportan glucosa no
  limitante; el modelo no reproduce el +43 % de Ark.

## Historial de versiones

Historial de versiones del documento. Las versiones son las del software (`src/__init__.py`); ver `CHANGELOG.md`.

| Versión | Fecha | Resumen |
|---------|-------|---------|
| 1.1.2 | 2026-11-08 | f34af71 y f2a64d1: trazabilidad de 13 pruebas OQ y texto de las pruebas exploratorias (en inglés). |
| 1.2.0 | 2026-11-10 | 98ffe46: sincronización con la cinética unificada y el Audit Trail de Part 11. |
| 1.3.0 | 2026-11-11 | 664efca: traducción al español. 6d8c509: compuerta OR de cizalla y pruebas nuevas. |
| 1.3.1 | 2026-11-11 | fd01ad7: lista de pruebas OQ actualizada (20 pruebas). |
| 1.3.2 | 2026-11-14 | b0fa17d y 99116f9 (Bloques 1 y 2): textos alineados con el código y la evidencia bibliográfica; versión del documento alineada con el software; historial añadido. cb5a484 (Bloque 3): casos negativos y de frontera de `test_oq_04` (ya no pendientes). 9c9ab7d (Bloque 4): 21 CFR Part 820 de QSR a QMSR. |
| 1.4.0 | 2026-11-20 | Fila 6b (gemelo calibrado y su validación) y SPC con estabilidad I-MR y TOST + Levene. Nueva sección 9: credibilidad del modelo según ASME V&V 40 (por analogía) junto a FDA CSA, con contexto de uso, riesgo del modelo, verificación, validación y limitaciones. Lista de pruebas: 24 (21 scripted, 3 exploratorias). |

*Fin del documento CSA-RA-2026-001.*
