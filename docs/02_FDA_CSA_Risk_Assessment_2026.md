# 02 — Evaluación de riesgo FDA Computer Software Assurance (CSA) — 2026

| Campo | Valor |
|-------|-------|
| **ID del documento** | CSA-RA-2026-001 |
| **Título** | Evaluación de riesgo bajo FDA CSA para software de producción y del sistema de calidad |
| **Versión** | 1.0 |
| **Guía principal** | FDA *Computer Software Assurance for Production and Quality System Software*, CDRH/CBER/CDER, Feb 3, 2026 |
| **Normas de soporte** | ISO 13485:2016, 21 CFR Part 820 (QSR), GAMP 5 (2nd ed.), 21 CFR Part 11, EudraLex Annex 11, Draft Annex 22 (AI) |
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

### 2.3 21 CFR Part 820 (Quality System Regulation)
El § 820.70(i) exige que el software usado para automatizar la producción o el sistema de calidad se
valide para su uso previsto según un protocolo establecido. CSA es la interpretación moderna de la
FDA sobre cómo cumplir el § 820.70(i) de forma eficiente.

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
| 6 | **Capacidad SPC / Six Sigma** (Cpk, intervalos de tolerancia) | `spc_six_sigma.py` | Decisiones estadísticas de liberación y monitoreo sobre datos de proceso. | Conclusión de capacidad incorrecta que alimenta la disposición. | **High Process Risk** | **Robust Scripted Testing** |
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

**Interlocks de seguridad.** La alarma de cizalla hidrodinámica (P/V > 47.6 W/m³ OR sparge > 0.15 vvm, URS-09/10), el
interlock de velocidad de CIP (≥ 1.52 m/s según ASME BPE, URS-11) y el interlock de letalidad de SIP
(F0 ≥ 15 min a ≥ 121.1 °C, URS-12) son la última línea de defensa contra el daño celular, la limpieza
insuficiente y el producto no estéril. Una falla es catastrófica y a menudo silenciosa hasta que se
manifiesta como contaminación. Es obligatorio el robust scripted testing (`test_oq_04`) con casos de
frontera y de modos de falla.

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
(`test_oq_08`).

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
- La suite cubre 18 pruebas: 15 pruebas scripted (`test_oq_01` a `test_oq_09`, incluidas
  `test_oq_03b`, `test_oq_03c`, `test_oq_04b`, `test_oq_05b_amab_scale_up_kla_pilot_commercial_range`,
  `test_oq_06b` y `test_oq_09b_part11_human_approved_mutation_breaks_chain`) y 3 pruebas exploratorias
  (`test_exploratory_10` a `test_exploratory_12`).
- La trazabilidad completa hacia adelante y hacia atrás se mantiene en `03_RTM_Traceability_Matrix.md`.

## 8. Conclusión

Al aplicar FDA CSA (2026), ISO 13485 y 21 CFR Part 820, los set-points de control y la lógica de
actuación, los interlocks de seguridad, el cálculo de MKT, las ecuaciones del Design Space, la
capacidad SPC, el Audit Trail y la validación de entradas se clasifican como **High Process Risk** y
se verifican con **Robust Scripted Testing**. Las gráficas y la UI se clasifican como **Not High
Process Risk** y se aseguran con **Unscripted Exploratory / Error-Guessing Testing**. Esta asignación
concentra el aseguramiento donde una falla afectaría más la calidad del producto, la seguridad y la
integridad de los datos.

*Fin del documento CSA-RA-2026-001.*
