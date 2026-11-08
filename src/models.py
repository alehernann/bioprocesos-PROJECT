"""Process-description schema for the CHO-K1 fed-batch digital twin.

This module defines the pydantic v2 :class:`ProcessDescription` model, which captures
the critical process parameters (CPPs) and operating setpoints for a single fed-batch
run of the digital twin.

The 0.25 L micro-scale default vessel volume follows the Stratyx(TM) / Bionova
Scientific micro-scale cultivation basis (Kulkarni et al., Culture Biosciences &
Bionova Scientific Whitepaper, 2026) and is consistent with the A-Mab reference
process design space (CMC Biotech Working Group, *A-Mab: A Case Study in Bioprocess
Development*, v2.1, CASSS/ISPE, Oct. 2009). Field bounds encode the validated
operating ranges used throughout the GxP validation package (URS-01, URS-07/08).
"""

from typing import Literal

from pydantic import BaseModel, Field


class ProcessDescription(BaseModel):
    """Critical process parameters and setpoints for one CHO-K1 fed-batch run.

    All field bounds reflect the validated operating ranges of the digital twin.
    The micro-scale 0.25 L default is justified by the Stratyx(TM) / Bionova
    Scientific 2026 whitepaper, and the design-space context derives from the
    A-Mab ISPE 2009 case study.
    """

    vessel_volume_L: float = Field(default=0.25, gt=0.0, le=35000.0)
    power_density_W_m3: float = Field(default=30.0, ge=2.0, le=100.0)
    sparge_vvm: float = Field(default=0.10, ge=0.0, le=1.0)
    temp_initial_C: float = Field(default=36.5, ge=30.0, le=40.0)
    temp_shift_C: float = Field(default=34.0, ge=30.0, le=40.0)
    temp_shift_day: float = Field(default=7.0, ge=1.0, le=14.0)
    ph_setpoint: float = Field(default=7.00, ge=6.0, le=8.0)
    ph_deadband: float = Field(default=0.20, gt=0.0, le=1.0)
    do_setpoint_pct: float = Field(default=30.0, ge=10.0, le=100.0)
    glucose_min_threshold_g_L: float = Field(default=2.0, ge=0.5, le=10.0)
    glucose_refill_target_g_L: float = Field(default=5.0, ge=2.0, le=15.0)
    duration_days: int = Field(default=14, ge=5, le=21)
    mode: Literal["static", "closed_loop"] = Field(default="closed_loop")
