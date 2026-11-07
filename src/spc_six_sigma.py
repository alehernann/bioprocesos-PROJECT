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
        "k_factor": round(float(k_factor), 2),
        "lower_tolerance": round(float(lower), 2),
        "upper_tolerance": round(float(upper), 2),
    }


def compute_process_capability(data, lsl: float = 5.0, usl: float = 12.0) -> dict:
    """Compute process-capability indices per ASTM E2281 / Gorsky (2020).

    Returns Cp, Cpu, Cpl, Cpk, the +/-3-sigma control limits, and a flag for
    4-sigma capability (Cpk >= 1.33).
    """
    mean = np.mean(data)
    std = np.std(data, ddof=1)
    cp = (usl - lsl) / (6 * std)
    cpu = (usl - mean) / (3 * std)
    cpl = (mean - lsl) / (3 * std)
    cpk = min(cpu, cpl)
    ucl = mean + 3 * std
    lcl = mean - 3 * std
    capable_4sigma = bool(cpk >= 1.33)
    return {
        "mean": round(float(mean), 2),
        "std": round(float(std), 2),
        "cp": round(float(cp), 2),
        "cpu": round(float(cpu), 2),
        "cpl": round(float(cpl), 2),
        "cpk": round(float(cpk), 2),
        "ucl": round(float(ucl), 2),
        "lcl": round(float(lcl), 2),
        "capable_4sigma": capable_4sigma,
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
