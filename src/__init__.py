"""Core simulation engine for the GxP CHO-K1 fed-batch bioprocess digital twin.

This package bundles the core-engine modules (software version in ``__version__``;
history in CHANGELOG.md):

- ``models``            : pydantic v2 process-description schema.
- ``bioreactor_twin``   : CHO-K1 fed-batch mechanistic digital twin and control/safety logic.
- ``amab_design_space`` : ISPE A-Mab (2009) multivariate design-space response surfaces.
- ``thermal_vtb_mkt``   : Rusnack (Pharm. Eng. 2026) MKT, virtual thermal buffer and FFT/Nyquist.
- ``spc_six_sigma``     : Gorsky (2020) / ISO 16269-6 / ASTM E2281 SPC statistics.
- ``audit_trail_part11``: 21 CFR Part 11 / EU GMP Annex 22 tamper-evident audit-trail logger.

References
----------
- CMC Biotech Working Group, *A-Mab: A Case Study in Bioprocess Development*, v2.1, CASSS/ISPE, Oct. 2009.
- I. Gorsky, "Use of Statistics in Process Validation," in *Principles of Parenteral Solution Validation*, Elsevier, 2020.
- M. Rusnack, "Quantifying the Limitations of Fixed Physical Temperature Buffers," *Pharmaceutical Engineering* (ISPE), 2026.
- Ark Biotech & Culture Biosciences / Bionova Scientific, closed-loop and Stratyx(TM) technical bulletins, 2026.
- ASME BPE-2014, *Bioprocessing Equipment: An International Standard*.
- 21 CFR Part 11 / EudraLex Vol. 4 Annex 11 and Draft Annex 22.
"""

__version__ = "1.3.2"
