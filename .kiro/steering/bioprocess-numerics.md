---
inclusion: fileMatch
fileMatchPattern: ["src/**/*.py", "tests_pbt/**/*.py"]
---

# Numérica del gemelo CHO-K1 (src/ y tests_pbt/)

## Integración por tramos

- `scipy.integrate.solve_ivp` por tramos: `[0, duration]` se parte en cada día de alimentación
  anterior a la cosecha y en `temp_shift_day`. Cada tramo usa RK45 (rtol 1e-6, atol 1e-9) con
  respaldo automático Radau (`MAX_RHS_EVALS_PER_SEGMENT`). Euler queda solo como referencia de
  verificación (`check_numerical_convergence`).
- El RHS es C0/C1-continuo dentro de un tramo. Bolos, cambio de set-point y reglas de glucosa se
  aplican entre tramos, nunca con `if t > día` dentro del RHS.
- Positividad sin polos: el RHS lee cada estado con `max(0, ·)`, todo consumo lleva un factor de
  Monod que se anula en C → 0+, y ningún denominador puede anularse en el dominio (`K + C` con
  `K > 0`; nunca `1/C`).
- `config.mode` no entra al RHS (ver gxp-scientific-integrity).

## Balances y capacidad

- Cada bolo conserva la masa de las 6 especies (Xv, Xd, G, L, NH3, título):
  `C_new·V_new = C_old·V_old + aportado`, con error ≤ 1e-9. Solo la glucosa recibe aporte
  (Cell Boost y stock de 500 g/L).
- `0 < V(t) ≤ vessel_volume_L`. Si el bolo no cabe se escala y se levanta `bolus_clipped_alarm`.
- Ninguna salida con NaN ni Inf; concentraciones ≥ 0; viabilidad en [0, 100] %.

## Recalibración (ASME V&V 40, URS-16)

Una recalibración o un cambio del conjunto de parámetros libres solo se propone con:

- multi-arranque (≥ 8 arranques además del prior) y la dispersión de la SSR resultante;
- cond(J) del Jacobiano escalado, RSE por parámetro y todo par con |r| > 0.90;
- estado de cota de cada parámetro (`interior`, `NEAR_BOUND`, `AT_BOUND`);
- métricas dentro de muestra (30 W/m³) separadas de fuera de muestra (19 W/m³, nunca ajustado);
- latencia: corrida de 14 d < 80 ms de media para Streamlit (NFR-07) y ninguna esquina del
  dominio de sliders ≥ 0.25 s;
- regla de adopción fijada antes de calibrar y evaluada en código (`compare_calibration_variants`).

## Pruebas de propiedades (tests_pbt/)

- Hypothesis con `@settings(max_examples=60, deadline=None, derandomize=True)`; la suite completa
  corre en < 20 s y no escribe archivos (`derandomize` desactiva la base de ejemplos).
- Cada propiedad prueba un invariante físico o regulatorio real, trazado a URS/NFR, y debe matar al
  menos un mutante en memoria (`python scripts/mutation_check_pbt.py`).
- Las tolerancias se fijan antes de correr y se justifican (redondeo de la salida, cota de error de
  punto flotante). Un contraejemplo se reporta; nunca se amplía la tolerancia para silenciarlo.
