---
inclusion: always
---

# Integridad científica GxP (bioprocesos-PROJECT)

Rige todo cambio en este repositorio (FDA CSA 2026, GAMP 5, ASME V&V 40, 21 CFR Part 11).

## Honestidad científica

- Los KPI (título, viabilidad, VCD, masa, NH3, Cpk, p-values, R², RMSE) salen de ejecutar el código.
  No se escriben a mano en `src/`, pruebas, tablero ni documentos: cada número citado en README o
  docs debe poder reproducirse con un comando documentado.
- `config.mode` y `glucose_feedback_in_static` solo se leen en el bloque de dosificación de
  `simulate_cho_fed_batch`. Nunca entran en `_build_rhs` ni en mu, kd, qp, q_G, q_L o q_NH3.
  `python scripts/verify_gxp_guards.py` lo comprueba por AST.
- Los criterios de aceptación pre-registrados (RMSE ≤ 2σ, cond(J) < 60, |r| ≤ 0.90, tolerancias de
  pytest e Hypothesis, presupuestos de latencia) no se relajan después de ver un resultado. Si un
  criterio falla, se reporta el fallo; cambiarlo exige control de cambios (docs/03, sección 10) y
  aprobación humana.
- Un hallazgo desfavorable se reporta tal cual; no se ajustan ecuaciones, parámetros ni pruebas
  para que algo pase.

## Tipos de dato

- `printed_exact`: impreso en la fuente; solo aplica la precisión de reporte (`uncertainty_abs = 0`).
- `digitized_figure_approx`: leído de una figura; siempre con su `uncertainty_abs` (el σ del ajuste).
- `modeling_assumption`: constante no calibrada (rotulada "MODELING ASSUMPTION" o
  "NOT CALIBRATED" en `src/`). No se presenta como medida ni calibrada ni se usa para validar.
- Los dos primeros tipos son los únicos de `data/bionova_nistcho_2026.json`; no se mezclan ni se
  promueven (un valor digitalizado no se cita como exacto).

## Módulos congelados (solo con control de cambios aprobado)

- `evaluate_amab_design_space` en `src/amab_design_space.py`.
- `AuditTrailLogger` en `src/audit_trail_part11.py` (payload y cadena SHA-256).
- `src/thermal_vtb_mkt.py` completo (MKT, VTB, FFT/Nyquist y `VTB_CALIBRATION_TABLE`).
- Comprobación: `python scripts/verify_gxp_guards.py --frozen-base <ref>` compara su AST (sin
  docstrings) contra la referencia, por ejemplo `v1.4.0` u `origin/main`.

## Git

- Nunca push directo a `main`: todo entra por PR con la CI de GitHub Actions en verde.
- Nunca mover, borrar ni reescribir tags publicados (`v1.0.0` … `v1.4.0`) ni historia pública.
- Commits atómicos, un propósito por commit, en el estilo del repo (`feat(...)`, `fix(...)`,
  `test(...)`, `docs(...)`, `ci(...)`, `chore(...)`).

## E/S multiplataforma (el autor audita en Windows; la CI corre en Linux)

- Toda lectura y escritura de texto con `encoding="utf-8"` explícito; archivos UTF-8 sin BOM.
- Rutas con `pathlib.Path` ancladas en `Path(__file__)`, nunca con separadores a mano ni
  dependientes del directorio actual.
- Comandos documentados válidos en PowerShell y bash (`python -m pytest ...`, sin heredocs).
