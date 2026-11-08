"""Statistical process control and Six Sigma routines for process validation.

Implements the process-validation statistics from Gorsky, "Chapter 6: Use of
Statistics in Process Validation," in *Principles of Parenteral Solution
Validation*, Elsevier, 2020, pp. 115-136, together with the tolerance-interval
machinery of ISO 16269-6:2014 and the capability indices of ASTM E2281.

The two torque datasets reproduce Gorsky (2020) Tables 6-1 (n=10) and 6-2 (n=30).
"""

import numpy as np
from scipy import stats

# Gorsky (2020) Table 6-1: closure-removal torque measurements, n = 10.
GORSKY_TABLE_6_1_TORQUE_N10 = [6.7, 9.5, 7.7, 6.7, 6.8, 11.0, 11.1, 6.2, 10.7, 8.2]

# Gorsky (2020) Table 6-2: closure-removal torque measurements, n = 30.
GORSKY_TABLE_6_2_TORQUE_N30 = [
    7.7, 8.1, 12.1, 5.6, 6.7, 8.1, 8.6, 6.2, 8.9, 7.2,
    9.4, 8.6, 3.3, 10.0, 9.3, 8.4, 10.3, 7.4, 9.3, 6.5,
    8.6, 7.7, 5.9, 7.9, 8.4, 10.1, 3.4, 8.4, 5.9, 8.8,
]


def compute_iso16269_tolerance_interval(data, k_factor: float = 3.394) -> dict:
    """Compute a two-sided statistical tolerance interval per ISO 16269-6:2014.

    The default k-factor (3.394) corresponds to the Gorsky (2020) n=10 example.
    The lower tolerance limit is clamped at zero since torque cannot be negative.
    """
    mean = np.mean(data)
    std = np.std(data, ddof=1)
    lower = max(0.0, mean - k_factor * std)
    upper = mean + k_factor * std
    return {
        "mean": round(float(mean), 2),
        "std": round(float(std), 2),
        "k_factor": round(float(k_factor), 3),
        "lower_tolerance": round(float(lower), 2),
        "upper_tolerance": round(float(upper), 2),
    }


def compute_process_capability(data, lsl: float = 5.0, usl: float = 12.0) -> dict:
    """Compute process-capability indices per ASTM E2281 / Gorsky (2020).

    Distinguishes OVERALL (long-term, "performance") indices from WITHIN
    (short-term, "capability") indices, per Gorsky (2020) Chapter 6:

    * OVERALL (Pp/Ppk): computed from the overall sample standard deviation
      ``std_overall = std(data, ddof=1)``. Gorsky Table 6.2 (n=30) reference:
      Pp 0.61, Ppu 0.72, Ppl 0.51, Ppk 0.51.
    * WITHIN (Cp/Cpk): computed from the moving-range estimate of short-term
      variation ``std_within = mean(|diff(data)|) / d2`` with d2 = 1.128 for a
      moving range of n = 2. Gorsky Fig. 6.5 (p.130) reference: Cpk_within ~0.42.

    For backward compatibility ``cpk`` is retained as ``round(ppk, 2)`` and the
    +/-3-sigma control limits and the 4-sigma capability flag use the overall std.

    A Shapiro-Wilk normality test (``scipy.stats.shapiro``) is also returned as
    ``normality_p_value`` with ``is_normal = (p >= 0.05)``; capability indices are
    only strictly valid for approximately normal data.

    Returns mean, std (overall), pp, ppu, ppl, ppk, cp_within, cpu_within,
    cpl_within, cpk_within, cpk (= round(ppk, 2)), ucl, lcl, capable_4sigma,
    normality_p_value and is_normal.
    """
    arr = np.asarray(data, dtype=float)
    mean = np.mean(arr)

    # --- OVERALL (Pp / Ppk) from the overall standard deviation ---
    std_overall = float(np.std(arr, ddof=1))
    pp = (usl - lsl) / (6 * std_overall)
    ppu = (usl - mean) / (3 * std_overall)
    ppl = (mean - lsl) / (3 * std_overall)
    ppk = min(ppu, ppl)

    # --- WITHIN (Cp / Cpk) from the moving-range short-term estimate ---
    mr_bar = float(np.mean(np.abs(np.diff(arr))))
    d2 = 1.128  # control-chart constant for a moving range of n = 2
    std_within = mr_bar / d2
    cp_within = (usl - lsl) / (6 * std_within)
    cpu_within = (usl - mean) / (3 * std_within)
    cpl_within = (mean - lsl) / (3 * std_within)
    cpk_within = min(cpu_within, cpl_within)

    # Backward-compatible cpk (= overall Ppk rounded) and +/-3-sigma limits.
    cpk = round(float(ppk), 2)
    ucl = mean + 3 * std_overall
    lcl = mean - 3 * std_overall
    capable_4sigma = bool(cpk >= 1.33)

    # Shapiro-Wilk normality test (capability indices assume approximate normality).
    shapiro_result = stats.shapiro(arr)
    normality_p_value = float(shapiro_result.pvalue)
    is_normal = bool(normality_p_value >= 0.05)

    return {
        "mean": round(float(mean), 2),
        "std": round(float(std_overall), 2),
        "pp": round(float(pp), 2),
        "ppu": round(float(ppu), 2),
        "ppl": round(float(ppl), 2),
        "ppk": round(float(ppk), 2),
        "cp_within": round(float(cp_within), 2),
        "cpu_within": round(float(cpu_within), 2),
        "cpl_within": round(float(cpl_within), 2),
        "cpk_within": round(float(cpk_within), 2),
        "cpk": cpk,
        "ucl": round(float(ucl), 2),
        "lcl": round(float(lcl), 2),
        "capable_4sigma": capable_4sigma,
        "normality_p_value": round(normality_p_value, 4),
        "is_normal": is_normal,
    }


def compare_bioreactor_equivalence_ttest(group_a, group_b, alpha: float = 0.05) -> dict:
    """Welch's two-sample t-test for bioreactor equivalence (Gorsky 2020).

    Uses ``scipy.stats.ttest_ind`` with ``equal_var=False`` (Welch's correction).
    Returns the t-statistic, p-value and a significance flag at the given alpha.
    """
    result = stats.ttest_ind(group_a, group_b, equal_var=False)
    t_stat = float(result.statistic)
    p_value = float(result.pvalue)
    return {
        "t_stat": round(t_stat, 4),
        "p_value": round(p_value, 6),
        "statistically_significant_diff": bool(p_value < alpha),
    }
