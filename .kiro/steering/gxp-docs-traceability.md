---
inclusion: fileMatch
fileMatchPattern: ["docs/**/*.md", "tests/**/*.py", "CHANGELOG.md"]
---

# Documentación GxP y trazabilidad

## Requisitos (docs/01)

- Sintaxis EARS: **WHEN** <disparador observable>, **THE SYSTEM SHALL** <acción verificable>.
  Cada URS/NFR declara categoría GAMP, riesgo de proceso, módulo de `src/` y prueba OQ.
- Marco vigente: FDA CSA (Feb 3, 2026); 21 CFR Part 820 QMSR (desde 2026-02-02; incorpora
  ISO 13485:2016, cláusula 4.1.6 para validar software); 21 CFR Part 11; EU GMP Annex 11 y Draft
  Annex 22 (IA con aprobación humana); ASME V&V 40-2018 por analogía.
- ASME V&V 40: la verificación del software (OQ: balances, positividad, convergencia, dominio de
  sliders) se reporta separada de la validación predictiva del modelo (RMSE ≤ 2σ contra Bionova
  dentro y fuera de muestra, URS-16). Ninguna evidencia de una se presenta como de la otra.

## Trazabilidad (docs/03)

- 100 % bidireccional: todo URS/NFR tiene al menos una prueba OQ y toda prueba de `tests/` resuelve
  a un URS/NFR. Cero requisitos huérfanos y cero pruebas huérfanas (secciones 4, 5, 6 y 9).
- Al añadir, renombrar, fusionar o eliminar una prueba OQ se actualizan en el mismo cambio docs/03
  (secciones 3 a 6 y registro de la sección 10) y la línea *OQ* del requisito en docs/01.
- Nombres: `test_oq_*` (scripted, High Process Risk) y `test_exploratory_*` (unscripted);
  `tests/conftest.py` deriva la categoría CSA del nombre. Cada prueba lleva un docstring con el
  requisito verificado, que el tablero muestra en la tabla OQ.
- `tests_app/` y `tests_pbt/` quedan fuera de la OQ: son evidencia complementaria y no escriben
  docs/04.
- Las versiones de docs/01, 02, 03 y 05 siguen `src/__init__.py`. Cada cambio añade una fila a su
  historial de versiones y una entrada en `CHANGELOG.md` bajo `## [Unreleased]` (Keep a Changelog).

## docs/04 (log OQ generado)

- `docs/04_Automated_OQ_Execution_Log.md` solo lo escribe `tests/conftest.py` al correr
  `python -m pytest -v tests/`. Nunca se edita a mano.
- Si una corrida local solo cambió la marca de tiempo y las duraciones (sin cambios en `src/` ni
  `tests/`), se restaura con `git restore docs/04_Automated_OQ_Execution_Log.md`.
- La CI no publica docs/04: el log versionado sale de una corrida local completa y aprobada.
