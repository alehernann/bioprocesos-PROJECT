"""Mean Kinetic Temperature, virtual thermal buffer and FFT/Nyquist analysis.

Implements the cold-chain thermal-excursion analytics from Rusnack,
"Quantifying the Limitations of Fixed Physical Temperature Buffers,"
*Pharmaceutical Engineering* (ISPE), vol. 46, no. 5, pp. 54-66, Sep./Oct. 2026
(Zenodo doi: 10.5281/zenodo.15871349 and doi: 10.5281/zenodo.20788524).

The virtual thermal buffer (VTB) emulates the first-order thermal lag of a fixed
physical buffer by a single-pole exponential filter calibrated per container volume.
The Nyquist/FFT routine supports effective-sampling verification of excursion monitors.
"""

import math

import numpy as np

# Rusnack (Pharm. Eng. 2026) per-volume first-order VTB calibration constants.
# alpha is the exponential-filter coefficient; tau is the thermal time constant.
VTB_CALIBRATION_TABLE = {
    "1 mL": {"alpha": 0.369, "tau_s": 652, "tau_min": 10.9},
    "10 mL": {"alpha": 0.212, "tau_s": 1259, "tau_min": 21.0},
    "20 mL (Glycol Ref)": {"alpha": 0.119, "tau_s": 2368, "tau_min": 39.5},
    "30 mL": {"alpha": 0.119, "tau_s": 2368, "tau_min": 39.5},
    "50 mL": {"alpha": 0.083, "tau_s": 3444, "tau_min": 57.4},
    "120 mL": {"alpha": 0.042, "tau_s": 7007, "tau_min": 116.8},
    "600 mL": {"alpha": 0.037, "tau_s": 7904, "tau_min": 131.7},
    "300 mL (Bulk)": {"alpha": 0.002, "tau_s": 126600, "tau_min": 2110.0},
}


def calculate_mkt_celsius(
    temps_C: list[float], delta_h_kJ_mol: float = 83.144
) -> float:
    """Return the Mean Kinetic Temperature (MKT) in Celsius.

    Uses the Haynes/Arrhenius MKT formulation as applied by Rusnack (Pharm. Eng.
    2026). With the default activation energy delta_h = 83.144 kJ/mol and
    R = 0.0083144 kJ/(mol*K), the ratio dH/R equals exactly 10000 K.
    """
    R = 0.0083144  # kJ/(mol*K)
    dH_over_R = delta_h_kJ_mol / R  # = 10000 K for the default delta_h
    temps_K = [t + 273.15 for t in temps_C]
    mean_exp = sum(math.exp(-(dH_over_R) / T_K) for T_K in temps_K) / len(temps_K)
    T_MKT_K = (dH_over_R) / (-math.log(mean_exp))
    return round(T_MKT_K - 273.15, 4)


def apply_vtb_filter(
    air_temps_C: list[float], volume_key: str = "20 mL (Glycol Ref)"
) -> list[float]:
    """Apply the single-pole virtual thermal buffer filter to an air-temperature trace.

    The filter emulates the thermal lag of a fixed physical buffer of the given
    container volume (Rusnack, Pharm. Eng. 2026), using the per-volume alpha from
    :data:`VTB_CALIBRATION_TABLE`:

        vtb[k] = alpha * air[k] + (1 - alpha) * vtb[k-1]
    """
    alpha = VTB_CALIBRATION_TABLE[volume_key]["alpha"]
    vtb = [air_temps_C[0]]
    for k in range(1, len(air_temps_C)):
        vtb.append(alpha * air_temps_C[k] + (1 - alpha) * vtb[-1])
    return vtb


def analyze_fft_nyquist(
    air_temps_C_5min: list[float], target_sampling_interval_min: float = 5.0
) -> dict:
    """Perform rigorous FFT/Nyquist aliasing analysis of a temperature trace.

    The input ``air_temps_C_5min`` is always a 5-minute-resolution air-temperature
    trace. The FFT is ALWAYS computed on this base 5-min signal (dt_base = 5.0 min,
    base Nyquist f_nyquist_base = 6.0 cph) so that the true dominant frequency of
    the physical signal (Rusnack, Pharm. Eng. 2026: compressor cycling ~2.8-3.0
    cycles/hour) is recovered independently of the sampling rate under test.

    ``target_sampling_interval_min`` is the candidate monitor sampling interval
    being qualified. Its Nyquist limit is ``target_nyquist_cph = 60 / (2 * dt)``.
    Aliasing risk is raised when the target Nyquist limit is at or below the true
    dominant frequency (``aliasing_risk = target_nyquist_cph <= true_dominant``).
    When aliasing occurs the apparent (folded) frequency the undersampled monitor
    would report is the general baseband fold
    ``folded_alias_freq_cph = |true_dominant - fs * round(true_dominant / fs)|``
    with ``fs = 60 / dt`` (cph), which always lies in [0, target Nyquist].

    The DC (bin 0) component of the mean-removed signal is ignored when locating
    the dominant frequency.

    Returns ``true_dominant_freq_cph``, ``target_nyquist_cph``, ``aliasing_risk``
    and, when aliasing, ``folded_alias_freq_cph`` (0.0 otherwise). Backward-
    compatible aliases ``nyquist_limit_cph`` (= target Nyquist) and
    ``dominant_freq_cph`` (= true dominant) are also provided.
    """
    DT_BASE_MIN = 5.0  # base signal resolution (min); base Nyquist = 6.0 cph

    signal = np.asarray(air_temps_C_5min, dtype=float)
    signal = signal - signal.mean()
    n = signal.size

    # FFT on the base 5-min signal; rfftfreq returns cycles/sample -> cycles/hour.
    spectrum = np.abs(np.fft.rfft(signal))
    freqs_cph = np.fft.rfftfreq(n, d=DT_BASE_MIN) * 60.0

    # Ignore the zero-frequency bin when searching for the dominant component.
    if spectrum.size > 1:
        dominant_idx = int(np.argmax(spectrum[1:]) + 1)
        true_dominant = float(freqs_cph[dominant_idx])
    else:
        true_dominant = 0.0

    target_nyquist = 60.0 / (2.0 * target_sampling_interval_min)
    aliasing_risk = bool(target_nyquist <= true_dominant)

    fs_cph = 60.0 / target_sampling_interval_min
    if aliasing_risk:
        # General baseband folding: distance from the nearest integer multiple of fs.
        folded_alias = abs(true_dominant - fs_cph * round(true_dominant / fs_cph))
    else:
        folded_alias = 0.0

    return {
        "true_dominant_freq_cph": round(true_dominant, 2),
        "target_nyquist_cph": round(target_nyquist, 2),
        "aliasing_risk": aliasing_risk,
        "folded_alias_freq_cph": round(folded_alias, 2),
        # Backward-compatible aliases for the dashboard (tab3).
        "nyquist_limit_cph": round(target_nyquist, 2),
        "dominant_freq_cph": round(true_dominant, 2),
    }
