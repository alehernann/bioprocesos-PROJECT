# 01 — Especificación de Requisitos de Usuario (URS)
## Sistema de control del biorreactor — Gemelo digital CHO-K1 fed-batch

| Campo | Valor |
|-------|-------|
| **ID del documento** | URS-BRX-001 |
| **Título** | Especificación de Requisitos de Usuario del sistema de control del biorreactor CHO-K1 fed-batch |
| **Versión** | 1.4.0 |
| **Estado** | Aprobado para implementación |
| **Marco regulatorio** | GAMP 5 (2nd ed.), ICH Q8(R2)/Q9(R1)/Q10/Q11, FDA CSA (Feb 2026), ASME V&V 40-2018 (por analogía), 21 CFR Part 11, EudraLex Annex 11 |
| **Producto** | Anticuerpo monoclonal (caso de referencia A-Mab) expresado en CHO-K1 |
| **Tipo de proceso** | Fed-batch, tren controlado single-use / acero inoxidable |
| **Rango de escala** | Micro-escala de 0.25 L (Stratyx™ / Ambr®) hasta 15,000 L comercial |

---

### 1. Propósito y alcance

Esta Especificación de Requisitos de Usuario (URS) define los requisitos de usuario, funcionales,
de desempeño, de seguridad, de integridad de datos y regulatorios del **sistema de control del
biorreactor** (en adelante "THE SYSTEM"), que gobierna un proceso **CHO-K1 fed-batch** para la
producción de un anticuerpo monoclonal. THE SYSTEM se implementa como un **gemelo digital**
validado que reproduce la estrategia de control física desde la escala de banco hasta la
manufactura comercial.

El alcance cubre todo el continuo de escalas: los **micro-biorreactores Stratyx™/Ambr® de 0.25 L**
usados en desarrollo de procesos y caracterización por Design-of-Experiments (DoE), los recipientes
piloto intermedios y el biorreactor de producción **comercial de 15,000 L**. THE SYSTEM está diseñado
para ser **independiente de la escala** en su lógica de control y **consciente de la escala** en sus
límites de ingeniería (cizalla hidrodinámica, transferencia de masa, tiempo de mezcla).

Este documento está escrito para ser **verificable mediante pruebas**. Cada requisito usa la
notación **EARS** (Easy Approach to Requirements Syntax) en su forma canónica:

> **WHEN** [condición de disparo], **THE SYSTEM SHALL** [acción observable del sistema].

Cada requisito se clasifica según las categorías de software **GAMP 5** y su impacto en el riesgo
de proceso, y se traza mediante la Requirements Traceability Matrix (RTM, documento 03) hasta un
módulo fuente en `src/` y una prueba de Operational Qualification (OQ) en
`tests/test_csa_oq_validation.py`.

### 2. Definiciones, acrónimos y abreviaturas

| Término | Definición |
|------|------------|
| **CHO-K1** | Línea celular Chinese Hamster Ovary K1, el hospedero de producción. |
| **Fed-batch** | Modo de cultivo en el que se alimentan nutrientes durante la corrida sin retirar medio. |
| **PID** | Controlador de lazo cerrado Proporcional-Integral-Derivativo. |
| **DO / OD** | Dissolved Oxygen (DO en inglés; "Oxígeno Disuelto", OD, en español). |
| **P/V** | Potencia volumétrica aplicada (W/m³), indicador indirecto de la cizalla hidrodinámica. |
| **CIP** | Clean-In-Place (limpieza in situ). |
| **SIP** | Sterilize-In-Place (esterilización in situ). |
| **F0** | Letalidad acumulada (minutos equivalentes a 121.1 °C, z = 10 °C). 121.1 °C = 250 °F, temperatura de referencia convencional de F0 con z = 10 °C; la fuente farmacéutica no está en la bibliografía del proyecto. |
| **MKT** | Mean Kinetic Temperature (temperatura cinética media). |
| **VTB** | Virtual thermal buffer (amortiguador térmico virtual; Rusnack). |
| **GAMP** | Good Automated Manufacturing Practice. |
| **EARS** | Easy Approach to Requirements Syntax. |
| **Split-range** | Esquema de control en el que una sola salida del controlador acciona dos elementos finales. |
| **Dead-band** | Región de control en la que no se ejecuta ninguna acción de los actuadores. |
| **PAT** | Process Analytical Technology. |
| **CQA** | Critical Quality Attribute (atributo crítico de calidad). |
| **CPP** | Critical Process Parameter (parámetro crítico de proceso). |

### 3. Categorización de software GAMP 5

| Categoría GAMP | Descripción | Aplicabilidad a THE SYSTEM |
|---------------|-------------|------------------------------|
| **Category 1** | Software de infraestructura (sistema operativo, runtime). | Runtime de Python, sistema operativo — evaluados vía proveedor. |
| **Category 3** | COTS no configurado. | Bibliotecas numéricas NumPy, SciPy, Pandas. |
| **Category 4** | Productos configurados. | Capa de visualización Streamlit/Plotly (UI configurada). |
| **Category 5** | Software a la medida. | Lógica de control, Design Space, interlocks, Audit Trail — el núcleo crítico GxP. |

El código a la medida de Category 5 exige el mayor rigor de validación y se somete a **Robust
Scripted Testing** según la guía FDA CSA 2026 (ver documento 02).

### 4. Base regulatoria y normativa

- **GAMP 5, 2nd ed. (ISPE, 2022)** — ciclo de vida de validación basado en riesgo.
- **FDA Computer Software Assurance (CSA), Feb 3, 2026** — aseguramiento basado en pensamiento crítico y en riesgo.
- **ICH Q8(R2) / Q9(R1) / Q10 / Q11 / Q12** — QbD, gestión de riesgos de calidad, ciclo de vida.
- **21 CFR Part 11 / EudraLex Annex 11 / Draft Annex 22 (AI)** — registros y firmas electrónicas.
- **ASME BPE-2014** — diseño higiénico de equipos de bioprocesamiento (velocidad de CIP).
- **ISPE A-Mab Case Study (2009)** — proceso de referencia del Design Space.
- **ASME V&V 40-2018** — marco de credibilidad de modelos computacionales (escrito para dispositivos
  médicos; aquí se aplica por analogía al gemelo digital). Separa la **verificación** del software
  (¿el código resuelve bien las ecuaciones?) de la **validación** del modelo (¿las ecuaciones
  reproducen datos medidos para el contexto de uso?). Ver URS-16 y el documento 02, sección 9.

---

## 5. Requisitos de usuario (URS-01 a URS-16)

### 5.1 Set-point de temperatura

#### URS-01 — Set-point inicial de temperatura validado
**WHEN** el biorreactor está en la fase de crecimiento (día de cultivo < 7.0),
**THE SYSTEM SHALL** enviar al controlador local de temperatura el set-point inicial validado de
**36.5 °C** (`ProcessDescription.temp_initial_C`). La regulación de la temperatura medida dentro de
su banda operacional se delega a ese controlador local; THE SYSTEM no simula ni califica un lazo PID
de temperatura.

*Fuente del perfil:* el perfil 36.5 → 34.0 °C en el día 7 sigue a Bionova (Ref. 2, NISTCHO, CHO-K1).
La fase a 36.5 °C queda fuera del Design Space de A-Mab (34–36 °C, Tabla 3.14) pero dentro del rango
del DoE de A-Mab (34–37 °C, Tabla 3.10). El Design Space se evalúa en la fase de producción (34.0 °C).
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulos:* `models.py`, `bioreactor_twin.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`

#### URS-02 — Cambio automático de temperatura en el día 7
**WHEN** el tiempo de cultivo llega al **día 7.0**,
**THE SYSTEM SHALL** cambiar el set-point de temperatura de **36.5 °C a 34.0 °C** de forma automática
y sin intervención del operador (temperature-shift / hipotermia leve para productividad), como un
**escalón** (sin rampa) en el día 7.0, y, cuando se le pasa un logger de Audit Trail, registrar el
evento en el Audit Trail. El perfil sigue a Bionova (Ref. 2, NISTCHO, CHO-K1); ver la nota de URS-01
sobre el Design Space de A-Mab.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_02_automated_day7_temperature_shift`

### 5.2 Lazo de control de pH (split-range con dead-band)

#### URS-03 — Set-point y tolerancia de pH
**WHEN** el cultivo está activo,
**THE SYSTEM SHALL** mantener el pH del caldo en **7.00 ± 0.20** (dead-band 6.80–7.20) mediante una
estrategia de control split-range, de modo que no se haga ninguna adición correctiva mientras el pH
permanezca dentro de la dead-band.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`

#### URS-04 — Rama ácida de pH (sparge de CO2)
**WHEN** el pH medido supera el límite superior de la dead-band (**pH > 7.20**),
**THE SYSTEM SHALL** accionar la rama de sparge de **CO2** del controlador split-range para bajar el
pH, y **SHALL NOT** accionar la rama de base al mismo tiempo.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`

#### URS-05 — Rama básica de pH (Na2CO3 1 M)
**WHEN** el pH medido cae por debajo del límite inferior de la dead-band (**pH < 6.80**),
**THE SYSTEM SHALL** accionar la rama de adición de base que dosifica **Na2CO3 1 M** para subir el
pH, y **SHALL NOT** accionar la rama de CO2 al mismo tiempo, preservando la exclusión mutua del
split-range.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`

### 5.3 Set-point de oxígeno disuelto y suficiencia de transferencia de masa

#### URS-06 — Set-point de DO y suficiencia de la transferencia de oxígeno
**WHEN** el cultivo está activo,
**THE SYSTEM SHALL** enviar al controlador local de DO un set-point de oxígeno disuelto (OD) de
**30 %** de saturación de aire (`ProcessDescription.do_setpoint_pct`), y **SHALL** verificar que la
velocidad de transferencia de oxígeno alcanza para la demanda del cultivo (**OTR ≥ OUR**) en las
esquinas de prueba Vs 0.005–0.017 m/s × P/V 19–30 W/m³ (P/V 19 y 30 W/m³ de Bionova, Ref. 2; banda
de Vs: supuesto de modelado) con la correlación de kLa (forma de A-Mab Ec. 4, p.101, anclada al
punto de 15,000 L). El gemelo y los presets de escala usan el kLa medido de A-Mab Tabla 3.22 (p.105):
2 L 10, 500 L 8, 1,000 L 10, 5,000 L 10, 15,000 L 20 y 25,000 L (Future) 20 h⁻¹, con la columna
inmediatamente inferior al volumen del recipiente; por debajo de 2 L se usa 10 h⁻¹ del modelo
estándar de 2 L como proxy (supuesto de modelado). En el gemelo, P/V no afecta el suministro de
O2. Cuando OTR < OUR con aire, THE SYSTEM muestra un aviso del modelo: el déficit viene de
C* = 0.210 mmol/L (solo aire) y qO2 = 0.10 pmol/cél/h, supuestos sin fuente, mientras A-Mab Tabla 3.23
(p.106) demostró operación a 18–30e6 cél/mL en 2 L; el aviso indica además el OTR con O2 puro. El
set-point de DO es configurable (por defecto 30 %; `ProcessDescription.do_setpoint_pct`, límites de
validación 5–100 % desde v1.4.0) y entra en la fuerza impulsora: OTR = kLa × (C*_gas − C*_aire × DO/100),
con C*_gas = C*_aire × y_O2 / 0.2095 (ley de Henry; `o2_mole_fraction`, por defecto aire, con lo que
OTR = kLa × C* × (1 − DO/100) y a 30 % de DO la fuerza impulsora es 0.147 mmol/L). A mayor set-point
de DO, menor OTR disponible.

*Gemelo (v1.4.0):* el controlador de DO del gemelo sostiene el set-point enriqueciendo el gas con O2
puro (`o2_enrichment_enabled`, por defecto activo, hasta `max_o2_mole_fraction`; A-Mab Fig. 3.12). El
DO real del líquido sale del balance cuasi estacionario C_L = min(C_sp, max(0, C*_max − OUR/kLa)). Si
ni el tope de O2 alcanza, el controlador se satura (`do_controller_saturated`) y el DO real cae bajo
el set-point; eso no es hipoxia por sí mismo. La respuesta biológica depende **solo del DO real**:
f_do vale exactamente 1.0 desde 15 % de DO real y baja de forma continua por debajo; el efecto Pasteur
actúa bajo 15 % y la muerte hipóxica bajo 10 %. Con solo aire y kLa 10 h⁻¹ el DO real baja de 15 %
cuando Xv supera 17.85e6 cél/mL (límite físico de transferencia), mientras que con enriquecimiento el
set-point se mantiene por encima de 20e6 cél/mL. Las bandas de 15 % y 10 % son supuestos de modelado
(no calibrados); A-Mab operó la producción a 30–70 % de DO (Tabla 3.14). La regulación del DO medido
se delega al controlador local; THE SYSTEM no simula ni califica un lazo PID de DO.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulos:* `models.py`, `amab_design_space.py`, `bioreactor_twin.py` — *OQ:* `test_oq_01_setpoints_and_ph_split_range_exclusivity`, `test_oq_05b_amab_scale_up_kla_pilot_commercial_range`, `test_oq_06b_do_setpoint_driving_force`

### 5.4 Alimentación adaptativa de glucosa

#### URS-07 — Disparo de la alimentación adaptativa de glucosa
**WHEN** en cada día de alimentación la glucosa medida antes del bolo (medición pre-feed, como en
Bionova, Ref. 2) está **por debajo de 2.0 g/L**,
**THE SYSTEM SHALL** disparar una reposición de glucosa en bolo que lleve la glucosa exactamente al
objetivo de **5.0 g/L** después del bolo base, sin sobrepasar ese objetivo, y no disparar la
reposición cuando el bolo base ya alcanza el objetivo. Entre días de alimentación no se evalúa el
disparo. La regla aplica en los modos `bionova_baseline` (protocolo exacto de Bionova: bolos fijos
de 4.62 % de V0 más esta regla) y `closed_loop` (además, modulación de Ark de los bolos de los días 8
y 10); el modo `static` no tiene retroalimentación de glucosa. El bolo base de Cell Boost aporta
glucosa por sí mismo (G_BOOST_CONC calibrado en 76.44 g/L), así que la glucosa post-bolo puede
superar 5.0 g/L sin intervención del controlador (Bionova midió 8.1 g/L el día 3).

*Hallazgo v1.4.0:* con la glucosa calibrada del Cell Boost, las corridas por defecto mantienen la
glucosa pre-feed ≥ 2.0 g/L en todos los días de alimentación, así que la reposición no llega a
dispararse con la regla 2 → 5 g/L (en los datos de Bionova la glucosa pre-feed de los días 10 y 12,
1.2 y 1.9 g/L, queda bajo el disparo; el modelo consume menos glucosa al final del cultivo que lo
medido). La lógica se verifica evento por evento
con la regla por defecto y con un disparo validado más alto (6.0 → 9.0 g/L), donde sí se activa.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_03_closed_loop_vs_static_titer_gain`

#### URS-08 — Comparación del lazo cerrado frente a la receta estática
**WHEN** se compara la estrategia `closed_loop` con la receta `static` (misma ley cinética; el modo
solo cambia la dosificación),
**THE SYSTEM SHALL** reportar la diferencia emergente de título final (g/L), masa cosechada (g) y
viabilidad final, y **SHALL** demostrar de forma reproducible la ventaja que explica el balance de
masa: mayor masa cosechada y mayor viabilidad final con el mayor volumen de alimentación. La
diferencia de título en g/L se reporta tal cual, sin restringirla a una banda ni a un signo.

*Control de cambios v1.4.0:* hasta v1.3.2 este requisito exigía un aumento del título en g/L. Con la
cinética calibrada contra Bionova, a 14 d la glucosa no limita en ninguno de los dos modos y los bolos
extra de Ark (×1.80 el día 8 y ×1.82 el día 10) diluyen el título: −3.37 % en g/L, +2.29 % de masa
cosechada y +0.76 puntos de viabilidad (NH3 final 11.32 frente a 11.68 mM). A 21 d, sin alimentación
después del día 12, la glucosa extra retrasa el agotamiento: +9.30 % en g/L, +15.70 % de masa y +5.45
puntos de viabilidad. El gemelo no tiene aminoácidos ni otros nutrientes que los bolos extra
podrían aportar, por lo que no puede reproducir el +43 % de Ark (dato de literatura).
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_03_closed_loop_vs_static_titer_gain`

### 5.5 Interlock de seguridad por cizalla hidrodinámica

#### URS-09 — Interlock de cizalla hidrodinámica (P/V)
**WHEN** `power_density_W_m3` > **47.6 W/m³** **OR** `sparge_vvm` > **0.15 vvm** (basta con que se
cumpla una de las dos condiciones: la cizalla del impulsor o la del sparge dispara la alarma por sí
sola; en P/V = 47.6 W/m³ y sparge = 0.15 vvm exactos no se dispara),
**THE SYSTEM SHALL** levantar la alarma de cizalla hidrodinámica (`high_shear_alarm = True`) y,
cuando se le pasa un logger de Audit Trail, registrar el disparo en el Audit Trail de Part 11,
aplicando el mismo límite en todas las escalas. THE SYSTEM no limita por sí mismo la agitación ni el
sparge; la acción correctiva queda a cargo del operador o del controlador local.

*Base de los umbrales:* 47.6 W/m³ es el P/V máximo demostrado aceptable a 2 L (A-Mab Tabla 3.22),
usado como criterio conservador, no como umbral de daño (el daño celular ocurre a P/V órdenes de
magnitud mayores, A-Mab p.100 / Ma 2002). 0.15 vvm es un supuesto de modelado sin fuente
bibliográfica.

*Desacople alarma–cinética (v1.4.0):* la alarma conservadora no entra en la cinética del gemelo. En las
ecuaciones, el estrés hidrodinámico responde al burbujeo (sparge > 0.15 vvm, interfaz gas-líquido) y
el impulsor solo penaliza por encima de 476 W/m³ (diez veces la alarma y aún por debajo del daño
documentado; A-Mab opera sano a 60 W/m³ de P/V local según la revisión de v1.4.0 de la Tabla 3.22).
Como `ProcessDescription` limita P/V a 100 W/m³, dentro del dominio validado P/V dispara la alarma
pero no cambia título ni viabilidad.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_04_safety_shear_and_cip_sip_interlocks`, `test_oq_04b_shear_or_gate_and_continuous_penalty`

#### URS-10 — Mismo umbral de cizalla en todas las escalas
**WHEN** el proceso opera a cualquier escala entre 0.25 L y 15,000 L,
**THE SYSTEM SHALL** aplicar el mismo umbral de P/V de **47.6 W/m³** (P/V máximo demostrado aceptable
a 2 L, A-Mab Tabla 3.22, criterio conservador, no umbral de daño) y el mismo umbral de sparge de
**0.15 vvm** (supuesto de modelado). THE SYSTEM no usa geometría por escala (diámetro del impulsor,
número de potencia) para evaluar la cizalla; A-Mab (p.98) indica que P/V y Vs no tienen por qué
mantenerse constantes al escalar.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_04_safety_shear_and_cip_sip_interlocks`

### 5.6 Interlocks de CIP / SIP

#### URS-11 — Interlock de velocidad de flujo en CIP (ASME BPE)
**WHEN** se está ejecutando un ciclo de Clean-In-Place (CIP),
**THE SYSTEM SHALL** calcular el indicador `cip_velocity_compliant` (velocidad del fluido de
limpieza **≥ 1.52 m/s**, requisito higiénico de flujo turbulento de ASME BPE-2014) y, cuando se le
pasa un logger de Audit Trail, registrar en el Audit Trail cada vez que la velocidad cae por debajo
de ese umbral. THE SYSTEM no aborta ni bloquea el ciclo de CIP; la acción queda a cargo del operador
o del controlador local.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_04_safety_shear_and_cip_sip_interlocks`

#### URS-12 — Interlock de letalidad en SIP (F0)
**WHEN** se está ejecutando un ciclo de Sterilize-In-Place (SIP),
**THE SYSTEM SHALL** calcular la letalidad acumulada **F0** y el indicador `sip_sterile_compliant`
(True solo cuando **F0 ≥ 15 min** y todas las temperaturas de SIP son **≥ 121.1 °C**) y, cuando se le
pasa un logger de Audit Trail, registrar en el Audit Trail cada resultado no conforme. THE SYSTEM no
libera ni retiene el recipiente por sí mismo; la decisión de liberación queda fuera de su alcance.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `bioreactor_twin.py` — *OQ:* `test_oq_04_safety_shear_and_cip_sip_interlocks`

### 5.7 Requisitos de Design Space, térmicos y de integridad de datos

#### URS-13 — Cumplimiento del Design Space ISPE A-Mab
**WHEN** el operador propone una combinación de set-points de parámetros críticos de proceso,
**THE SYSTEM SHALL** evaluar si la combinación cae dentro del **A-Mab Design Space** validado (punto
central y bordes de falla) y **SHALL** señalar cualquier punto fuera de la región aceptable
multivariada.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `amab_design_space.py` — *OQ:* `test_oq_05_ispe_amab_design_space_center_and_edges`

#### URS-14 — Mean Kinetic Temperature y amortiguamiento en cadena de frío
**WHEN** se suministran series de tiempo de temperatura de almacenamiento o transporte,
**THE SYSTEM SHALL** calcular la **Mean Kinetic Temperature (MKT)** y modelar el amortiguamiento
térmico de un virtual thermal buffer (VTB, Rusnack). THE SYSTEM expone los valores calculados; no
genera reportes de excursión ni compara contra las condiciones de almacenamiento rotuladas.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulo:* `thermal_vtb_mkt.py` — *OQ:* `test_oq_06_mkt_and_vtb_damping`

#### URS-15 — Audit Trail de Part 11 y capacidad SPC
**WHEN** se crea o modifica cualquier registro relevante para GxP, o se dispara un interlock con un
logger de Audit Trail pasado a la función,
**THE SYSTEM SHALL** capturar una entrada de Audit Trail conforme a **21 CFR Part 11**, con marca de
tiempo, atribuible y con evidencia de manipulación, y **SHALL** soportar el análisis de Statistical
Process Control (SPC) y de capacidad de proceso (Cpk) de los datos registrados, respetando el
guardrail de AI del Draft Annex 22. Desde v1.4.0 **SHALL** verificar la estabilidad estadística I-MR
(regla 1 de Shewhart) antes de declarar cumplidos los supuestos de capacidad
(`capability_assumptions_met` = normalidad Y control estadístico) y **SHALL** ofrecer una prueba
formal de equivalencia entre biorreactores (TOST de Schuirmann con pruebas t de Welch y prueba de
Levene; Gorsky 2020, p.131).
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulos:* `audit_trail_part11.py`, `spc_six_sigma.py` — *OQ:* `test_oq_09_part11_audit_trail_and_annex22_guardrail`, `test_oq_08_gorsky_spc_tolerance_and_capability`, `test_oq_08b_spc_control_stability_and_tost_equivalence`

### 5.8 Credibilidad del modelo mecanístico (ASME V&V 40 / FDA CSA)

#### URS-16 — Calibración, identificabilidad y validación predictiva contra datos medidos
**WHEN** el gemelo digital se usa para comparar estrategias de alimentación (contexto de uso: cribado
de estrategias en desarrollo de proceso, influencia baja del modelo en la decisión, sin uso para
liberación de lotes),
**THE SYSTEM SHALL** usar parámetros cinéticos calibrados contra datos medidos y documentados como
constantes (`src/bioreactor_twin.py`), **SHALL** reportar para cada parámetro libre su valor, sus
cotas, si quedó en una cota (`AT_BOUND` / `NEAR_BOUND`) y su identificabilidad práctica (valores
singulares del Jacobiano escalado, cond(J), pares colineales |r| > 0.90, error estándar relativo), y
**SHALL** reportar R², RMSE, NRMSE y el error del día 14 dentro de muestra (Bionova Stratyx 30 W/m³)
y fuera de muestra (Stratyx 19 W/m³, nunca usado en la calibración), comparando con el estado pre-feed
del gemelo (`daily_pre_feed`), que coincide con el momento del muestreo de Bionova.

*Criterio de credibilidad (fijado para este contexto de uso):* RMSE ≤ 2 × la incertidumbre declarada
de cada variable dentro de muestra y para la serie de VCD fuera de muestra, y cada punto de 19 W/m³
dentro de 2 × su incertidumbre. *Verificación separada:* la OQ verifica el software (balances,
positividad, convergencia del integrador, estabilidad en todo el dominio de los sliders); la
validación del modelo biológico es esta URS.
- *Categoría GAMP:* 5 — *Riesgo de proceso:* High — *Módulos:* `model_validation.py`, `bioreactor_twin.py`, `data/bionova_nistcho_2026.json` — *OQ:* `test_oq_03g_bionova_validation_fit_and_oos`, `test_oq_03f_rk45_convergence_and_nh3_decline`

---

## 6. Requisitos no funcionales

| ID | Requisito |
|----|-------------|
| NFR-01 | Todos los cálculos numéricos deben ser deterministas y reproducibles con semillas y entradas idénticas. |
| NFR-02 | Los parámetros de entrada deben validarse con modelos Pydantic de tipado estricto que rechacen valores fuera de rango o mal formados. |
| NFR-03 | El subsistema de procesamiento de señales debe respetar el criterio de Nyquist en el muestreo (ver `test_oq_07`). |
| NFR-04 | El sistema debe degradarse de forma segura: ante una entrada inválida lanza un error validado en lugar de producir silenciosamente una salida incorrecta. |
| NFR-05 | Las alarmas e interlocks que se registran en el Audit Trail (cuando se pasa un logger) llevan marca de tiempo ISO-8601 en UTC. Sin logger, THE SYSTEM solo devuelve los indicadores y no registra nada. |
| NFR-06 | Estabilidad numérica en todo el dominio de los sliders del tablero (P/V 2–100 W/m³, sparge 0–1 vvm, día de cambio térmico 1–14 d, DO 10–90 %, volumen 0.25–35,000 L, duración 5–21 d, con y sin enriquecimiento de O2): sin NaN ni Inf, concentraciones ≥ 0, viabilidad en [0, 100] % y V(t) ≤ volumen del recipiente (`test_oq_03h`). Integración RK45 (rtol 1e-6, atol 1e-9) con cambio automático a Radau, con error frente a la referencia rtol 1e-9 < 1e-4 (`test_oq_03f`). |
| NFR-07 | Desempeño interactivo: una corrida de 14 d del gemelo tarda en promedio < 80 ms y ninguna esquina del dominio de los sliders tarda ≥ 0.25 s (`test_oq_03h`). |

## 7. Trazabilidad

Cada requisito, de URS-01 a URS-16, se traza hacia adelante a un módulo de `src/`, un nivel de
riesgo CSA y un caso de prueba OQ en la Requirements Traceability Matrix (documento
`03_RTM_Traceability_Matrix.md`). La justificación de la clasificación de riesgo se define en
`02_FDA_CSA_Risk_Assessment_2026.md`.

## 8. Aceptación

Esta URS se acepta cuando los 16 requisitos de usuario quedan demostrados con evidencia OQ aprobada
y la RTM muestra 100 % de trazabilidad bidireccional, sin requisitos huérfanos ni pruebas huérfanas.

## Historial de versiones

Historial de versiones del documento. Las versiones son las del software (`src/__init__.py`); ver `CHANGELOG.md`.

| Versión | Fecha | Resumen |
|---------|-------|---------|
| 1.1.2 | 2026-11-08 | Documento en inglés vigente en la versión 1.1.2 del software (creado en 24464b3; la cabecera decía 2.1). |
| 1.2.0 | 2026-11-10 | 98ffe46: URS-01 y URS-06 delegan la regulación al controlador local; URS-09 con compuerta AND. |
| 1.3.0 | 2026-11-11 | 664efca: traducción al español. 6d8c509: URS-09 con compuerta OR; URS-06 con fuerza impulsora del DO configurable. |
| 1.3.1 | 2026-11-11 | fd01ad7: URS-06 describe el acople del DO con la cinética del gemelo. |
| 1.3.2 | 2026-11-14 | b0fa17d y 99116f9 (Bloques 1 y 2): textos alineados con el código y la evidencia bibliográfica; versión del documento alineada con el software; historial añadido. cb5a484 (Bloque 3): sin cambios en este documento. 9c9ab7d (Bloque 4): URS-06 con el kLa medido por escala de A-Mab Tabla 3.22 y el proxy de 2 L por debajo de 2 L. |
| 1.4.0 | 2026-11-20 | Modelo mecanístico calibrado de 6 estados (rama `feat/v1.4.0-mechanistic-validation`, Draft PR). URS-06: DO real, enriquecimiento con O2 y saturación del controlador sin hipoxia falsa; límite inferior de DO 5 %. URS-07: modo `bionova_baseline` y hallazgo de que la regla 2 → 5 g/L no se dispara con la glucosa calibrada. URS-08 revisado bajo control de cambios (ventaja en masa y viabilidad; g/L reportado). URS-09: desacople alarma–cinética. URS-15: estabilidad I-MR y TOST + Levene. Nuevos URS-16 (credibilidad ASME V&V 40), NFR-06 y NFR-07. |

*Fin del documento URS-BRX-001.*
