"""Process-description schema for the CHO-K1 fed-batch digital twin.

This module defines the pydantic v2 :class:`ProcessDescription` model, which captures
the critical process parameters (CPPs) and operating setpoints for a single fed-batch
run of the digital twin.

The 0.25 L micro-scale default vessel volume follows the Stratyx(TM) / Bionova
Scientific micro-scale cultivation basis (Kulkarni et al., Culture Biosciences &
Bionova Scientific Whitepaper, 2026; 190 mL initial volume). It does not come from
the A-Mab case study, which scaled from 2 L to 15,000 L. Field bounds are input
validation limits of the digital twin (URS-01, URS-07/08), not process operating
ranges.

v1.4.0 adds cross-field validation (``model_validator``), the configurable initial
fill fraction, pure-O2 enrichment of the sparge gas and the
``glucose_feedback_in_static`` flag. ``mode`` keeps its binary contract
(``static`` / ``closed_loop``); the exact Bionova protocol used for calibration is
``mode="static"`` with ``glucose_feedback_in_static=True``.
"""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ProcessDescription(BaseModel):
    """Critical process parameters and setpoints for one CHO-K1 fed-batch run.

    Field bounds are input validation limits of the digital twin. The micro-scale
    0.25 L default follows the Stratyx(TM) / Bionova Scientific 2026 whitepaper
    (190 mL initial volume), not A-Mab.

    Feeding modes (``mode`` is read only by the feed-dosing block of the twin; it
    never enters a kinetic rate):

    - ``static``: fixed day-0 recipe. Base bolus of 4.62 % of V0 on every feed day,
      no bolus modulation, and no glucose feedback unless
      ``glucose_feedback_in_static`` is True.
    - ``closed_loop``: the same boluses with the Ark adaptive modulation (x1.80 on
      day 8 and x1.82 on day 10, Quint et al. 2026) plus the pre-feed glucose rule
      (G < glucose_min_threshold_g_L -> top-up to glucose_refill_target_g_L).

    ``glucose_feedback_in_static`` (default False) arms the pre-feed glucose rule in
    ``static`` without changing the bolus recipe. ``mode="static"`` with this flag
    is the Bionova protocol (Ref. 2, pp. 3-4: fixed boluses plus the < 2 -> 5 g/L
    rule). The flag has no extra effect in ``closed_loop``, which always has the rule.

    Cross-field rules (``model_validator``): the glucose trigger must be below the
    refill target, and the temperature shift cannot be scheduled after the end of
    the run.
    """

    vessel_volume_L: float = Field(default=0.25, gt=0.0, le=35000.0)
    power_density_W_m3: float = Field(default=30.0, ge=2.0, le=100.0)
    # Default 0.10 vvm is a pilot-scale sparge regime, not the micro-scale one: the
    # Bionova Scientific / Stratyx(TM) micro-scale basis runs at
    # 0.5 mL/min / 190 mL = 0.00263 vvm (Bionova, Ref. 2, pp. 3-4). The high-shear alarm trips when
    # P/V > 47.6 W/m3 OR sparge_vvm > 0.15 (0.15 vvm is a modeling assumption).
    sparge_vvm: float = Field(default=0.10, ge=0.0, le=1.0)
    temp_initial_C: float = Field(default=36.5, ge=30.0, le=40.0)
    temp_shift_C: float = Field(default=34.0, ge=30.0, le=40.0)
    temp_shift_day: float = Field(default=7.0, ge=1.0, le=14.0)
    ph_setpoint: float = Field(default=7.00, ge=6.0, le=8.0)
    ph_deadband: float = Field(default=0.20, gt=0.0, le=1.0)
    # Lower validation limit 5 % (v1.4.0, was 10 %) so the twin can be exercised in
    # real hypoxia (DO_real < 10 %); the dashboard slider reads this limit (5-90 %).
    do_setpoint_pct: float = Field(default=30.0, ge=5.0, le=100.0)
    glucose_min_threshold_g_L: float = Field(default=2.0, ge=0.5, le=10.0)
    glucose_refill_target_g_L: float = Field(default=5.0, ge=2.0, le=15.0)
    duration_days: int = Field(default=14, ge=5, le=21)
    mode: Literal["static", "closed_loop"] = Field(default="closed_loop")
    # Pre-feed glucose rule in the static recipe (Bionova protocol); see class docstring.
    glucose_feedback_in_static: bool = Field(default=False)
    # Initial working volume V0 = initial_fill_fraction * vessel_volume_L. The 0.70
    # default keeps URS-07 / test_oq_03b unchanged; 0.76 = 190/250 mL is the exact
    # Bionova fill (Ref. 2, pp. 3-4).
    initial_fill_fraction: float = Field(default=0.70, ge=0.20, le=0.95)
    # Pure-O2 enrichment of the sparge gas (A-Mab Fig. 3.12; Stratyx). When False the
    # DO controller can only use air (y_O2 = 0.2095).
    o2_enrichment_enabled: bool = Field(default=True)
    # Highest O2 mole fraction the gas blender may reach when enrichment is enabled.
    max_o2_mole_fraction: float = Field(default=1.0, ge=0.2095, le=1.0)

    @model_validator(mode="after")
    def _check_cross_field_consistency(self) -> "ProcessDescription":
        """Reject internally inconsistent set-point combinations."""
        if not self.glucose_min_threshold_g_L < self.glucose_refill_target_g_L:
            raise ValueError(
                "glucose_min_threshold_g_L must be lower than glucose_refill_target_g_L "
                f"(got {self.glucose_min_threshold_g_L} >= {self.glucose_refill_target_g_L})."
            )
        if self.temp_shift_day > self.duration_days:
            raise ValueError(
                "temp_shift_day cannot be later than duration_days "
                f"(got {self.temp_shift_day} > {self.duration_days})."
            )
        return self
