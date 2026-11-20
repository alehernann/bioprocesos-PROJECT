"""Statistical process control and Six Sigma routines for process validation.

Implements the process-validation statistics from Gorsky, "Chapter 6: Use of
Statistics in Process Validation," in *Principles of Parenteral Solution
Validation*, Elsevier, 2020, pp. 115-136, together with the tolerance-interval
machinery of ISO 16269-6:2014 and the capability indices of ASTM E2281.

The two torque datasets reproduce Gorsky (2020) Tables 6-1 (n=10) and 6-2 (n=30).

v1.4.0 adds the I-MR statistical-control check that must hold before capability is
interpreted (``in_statistical_control``, ``capability_assumptions_met``) and the
formal equivalence test ``compare_bioreactor_equivalence_tost`` (Schuirmann TOST
with Welch t-tests plus Levene's test, Gorsky 2020 p.131).
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
    cpl_within, cpk_within, cpk (= round(ppk, 2)), ucl, lcl (overall +/-3 std),
    std_within, ucl_within, lcl_within (I-MR Shewhart limits, mean +/- 3*std_within
    = mean +/- 2.66*MR-bar, short-term), capable_4sigma, normality_p_value and
    is_normal.

    STATISTICAL-CONTROL CHECK (v1.4.0)
    ----------------------------------
    Capability indices only describe a process that is in statistical control
    (Gorsky 2020, ch. 6). Shewhart Rule 1 is applied to the individuals chart:
    ``n_out_of_control_points`` counts the points outside
    [lcl_within, ucl_within] (unrounded limits), ``in_statistical_control`` is
    True when that count is 0, and ``capability_assumptions_met`` =
    is_normal AND in_statistical_control. All earlier keys are unchanged.
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

    # Shewhart Rule 1 on the I chart (within limits, unrounded).
    ucl_within = mean + 3 * std_within
    lcl_within = mean - 3 * std_within
    n_out_of_control = int(np.sum((arr > ucl_within) | (arr < lcl_within)))
    in_statistical_control = bool(n_out_of_control == 0)
    capability_assumptions_met = bool(is_normal and in_statistical_control)

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
        "std_within": round(float(std_within), 2),
        "ucl_within": round(float(mean + 3 * std_within), 2),
        "lcl_within": round(float(mean - 3 * std_within), 2),
        "capable_4sigma": capable_4sigma,
        "normality_p_value": round(normality_p_value, 4),
        "is_normal": is_normal,
        "n_out_of_control_points": n_out_of_control,
        "in_statistical_control": in_statistical_control,
        "capability_assumptions_met": capability_assumptions_met,
    }


def compute_moving_range_summary(data, d2: float = 1.128) -> dict:
    """Pure helper: moving-range statistics behind the WITHIN indices.

    Exposes the intermediate values that :func:`compute_process_capability` uses
    for its short-term (within) sigma, so they can be reported: MR-bar is the mean
    absolute difference between consecutive points and ``std_within = MR-bar / d2``
    (d2 = 1.128 for a moving range of n = 2). It does not alter any existing result.
    """
    arr = np.asarray(data, dtype=float)
    mr_bar = float(np.mean(np.abs(np.diff(arr))))
    return {
        "n": int(arr.size),
        "mr_bar": round(mr_bar, 2),
        "d2": float(d2),
        "std_within": round(mr_bar / d2, 2),
    }


def compare_bioreactor_equivalence_tost(
    group_a, group_b, equiv_margin: float, alpha: float = 0.05
) -> dict:
    """Formal equivalence test: Schuirmann TOST (Welch) plus Levene (Gorsky 2020, p.131).

    A non-significant t-test does not prove equivalence. TOST tests
    H0: |mu_A - mu_B| >= equiv_margin against H1: |mu_A - mu_B| < equiv_margin with
    two one-sided Welch t-tests (unequal variances, Welch-Satterthwaite df):

        t_lower = (d + margin) / se,  p_lower = P(T > t_lower)   (H0: d <= -margin)
        t_upper = (d - margin) / se,  p_upper = P(T < t_upper)   (H0: d >= +margin)
        p_tost  = max(p_lower, p_upper);  means_equivalent = p_tost < alpha

    with d = mean_A - mean_B and se = sqrt(s_A^2/n_A + s_B^2/n_B). Equivalently, the
    (1 - 2*alpha) confidence interval of d (``ci_low``, ``ci_high``; 90 % for
    alpha = 0.05, also returned as ``ci_90_low`` / ``ci_90_high``) lies inside
    (-margin, +margin). Levene's test (``scipy.stats.levene``, median centre, i.e.
    the Brown-Forsythe variant) checks that the spreads are compatible
    (p >= alpha). ``statistically_equivalent`` = means_equivalent AND
    variances_compatible. ``equiv_margin`` must be set from a scientific
    justification (e.g. a fraction of the specification range), never from the
    data being compared.
    """
    a = np.asarray(group_a, dtype=float)
    b = np.asarray(group_b, dtype=float)
    if a.size < 2 or b.size < 2:
        raise ValueError("Each group needs at least two values.")
    if not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)):
        raise ValueError("Groups must contain only finite numbers.")
    margin = float(equiv_margin)
    if not margin > 0.0:
        raise ValueError("equiv_margin must be > 0.")
    if not 0.0 < alpha < 0.5:
        raise ValueError("alpha must be in (0, 0.5).")

    n_a, n_b = int(a.size), int(b.size)
    mean_a, mean_b = float(a.mean()), float(b.mean())
    diff = mean_a - mean_b
    va = float(a.var(ddof=1)) / n_a
    vb = float(b.var(ddof=1)) / n_b
    se = float(np.sqrt(va + vb))
    if se > 0.0:
        df = (va + vb) ** 2 / (
            (va ** 2 / (n_a - 1) if va > 0 else 0.0) + (vb ** 2 / (n_b - 1) if vb > 0 else 0.0)
        )
        t_lower = (diff + margin) / se
        t_upper = (diff - margin) / se
        p_lower = float(stats.t.sf(t_lower, df))
        p_upper = float(stats.t.cdf(t_upper, df))
        half = float(stats.t.ppf(1.0 - alpha, df)) * se
        half_90 = float(stats.t.ppf(0.95, df)) * se
    else:
        # Both groups constant: the difference is known exactly.
        df = float(n_a + n_b - 2)
        t_lower = float("inf") if diff > -margin else float("-inf")
        t_upper = float("-inf") if diff < margin else float("inf")
        p_lower = 0.0 if diff > -margin else 1.0
        p_upper = 0.0 if diff < margin else 1.0
        half = half_90 = 0.0
    p_tost = max(p_lower, p_upper)
    means_equivalent = bool(p_tost < alpha)

    if float(a.var(ddof=1)) == 0.0 and float(b.var(ddof=1)) == 0.0:
        levene_stat, levene_p = 0.0, 1.0  # identical (zero) spread
    else:
        lev = stats.levene(a, b, center="median")
        levene_stat, levene_p = float(lev.statistic), float(lev.pvalue)
    variances_compatible = bool(levene_p >= alpha)

    return {
        "n_a": n_a,
        "n_b": n_b,
        "mean_a": mean_a,
        "mean_b": mean_b,
        "mean_diff": diff,
        "se_diff": se,
        "df_welch": float(df),
        "equiv_margin": margin,
        "alpha": float(alpha),
        "t_lower": float(t_lower),
        "p_lower": p_lower,
        "t_upper": float(t_upper),
        "p_upper": p_upper,
        "p_tost": p_tost,
        "ci_level": 1.0 - 2.0 * float(alpha),
        "ci_low": diff - half,
        "ci_high": diff + half,
        "ci_90_low": diff - half_90,
        "ci_90_high": diff + half_90,
        "ci_within_margin": bool(-margin < diff - half and diff + half < margin),
        "means_equivalent": means_equivalent,
        "levene_stat": levene_stat,
        "levene_p_value": levene_p,
        "levene_center": "median",
        "variances_compatible": variances_compatible,
        "statistically_equivalent": bool(means_equivalent and variances_compatible),
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
