"""Calibration, identifiability and predictive validation of the CHO twin (v1.4.0).

ASME V&V 40 / FDA CSA framing used in this package:

* Software verification (OQ, ``tests/``): does the code solve the stated equations
  correctly? Mass balance, positivity, solver convergence
  (``check_numerical_convergence``) and stability over the whole slider domain.
* Model validation (this module): how well do the calibrated equations reproduce
  measured culture data? In-sample fit on the Bionova Stratyx 30 W/m3 run and an
  out-of-sample prediction of the Stratyx 19 W/m3 run, which is never used for
  calibration (``compute_validation_metrics``), plus the practical
  identifiability of every free parameter (``compute_jacobian_identifiability``).

The reference data are ``data/bionova_nistcho_2026.json`` (printed values and
digitized figure values with declared uncertainty, pre-feed daily sampling). The
twin is compared through ``daily_pre_feed``, the state exactly before each bolus,
which matches the Bionova sampling time.

``run_parameter_calibration`` is an offline tool: its output is frozen as the
documented constants of ``src/bioreactor_twin.py``. The dashboard never runs it.
"""

import json
import math
import time
from dataclasses import replace
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

from src.bioreactor_twin import (
    CALIBRATED_KINETICS,
    CALIBRATED_PARAMETER_NAMES,
    PARAMETER_BOUNDS,
    CHOKineticParameters,
    simulate_cho_fed_batch,
)
from src.models import ProcessDescription

DATASET_PATH = Path(__file__).resolve().parent.parent / "data" / "bionova_nistcho_2026.json"

# Dataset series key -> daily_pre_feed key of the twin.
SERIES_TO_STATE = {
    "vcd_1e6_mL": "Xv",
    "viability_pct": "viability_pct",
    "glucose_g_L": "G",
    "lactate_g_L": "L",
    "nh3_mmol_L": "NH3",
    "titer_g_L": "Titer",
}
CONDITION_SETS = {"stratyx_30_W_m3": "calibration_set", "stratyx_19_W_m3": "validation_set"}

# Documented starting point of the calibration (neutral prior, not the optimum):
# mid-range of the literature bounds for mu_max, K_I_L and G_BOOST_CONC and round
# CHO-typical magnitudes for the others.
CALIBRATION_INITIAL_GUESS = {
    "mu_max_36_5": 0.80,
    "mu_max_34_0": 0.22,
    "k_i_lactate": 10.0,
    "g_boost_conc": 70.0,
    "x_max": 30.0,
    "q_lac_max": 0.10,
    "q_nh3": 0.05,
    "kd_nh3": 0.01,
    "qp_36_5": 0.012,
    "qp_34_0": 0.012,
    "y_x_glucose": 3.0,
    "m_glucose": 0.05,
    "y_lac_glucose": 0.8,
    "kd_basal": 0.03,
    "k_lysis": 1.0,
    "k_i_nh3": 20.0,
}

# Data that would make each parameter identifiable when the Bionova run cannot.
ADDITIONAL_DATA_NEEDED = {
    "mu_max_36_5": "exponential-phase VCD at higher sampling frequency (twice daily) at 36.5 C",
    "mu_max_34_0": "a run shifted to 34 C early (day 3-4) to separate growth at 34 C from density limitation",
    "k_i_lactate": "lactate pulse or spiking experiments (2-6 g/L) at constant density; Bionova lactate never exceeds 1.4 g/L",
    "g_boost_conc": "glucose assay of the Cell Boost 7a/7b feed, or post-bolus (not only pre-feed) glucose samples",
    "x_max": "runs at different inoculum densities or nutrient-rich feeds (amino-acid profiles)",
    "q_lac_max": "lactate pulse experiments in stationary phase",
    "q_nh3": "amino-acid (glutamine/glutamate) time profiles to separate cellular and chemical NH3 sources",
    "kd_nh3": "NH4Cl spiking experiments (5-15 mM) with viability and dead-cell counts",
    "qp_36_5": "titer samples before day 8 (Bionova reports titer from day 8)",
    "qp_34_0": "titer samples every day after the shift",
    "y_x_glucose": "post-bolus glucose samples in the growth phase",
    "m_glucose": "glucose uptake in stationary phase with daily (post-bolus) samples",
    "y_lac_glucose": "glucose and lactate sampled at least twice daily in the growth phase",
    "kd_basal": "dead-cell (not only viability) counts in the growth phase",
    "k_lysis": "total-cell and LDH measurements to quantify lysis",
    "k_i_nh3": "NH4Cl spiking experiments in the growth phase",
}

# Credibility acceptance criteria (ASME V&V 40, context of use: decision support for
# feeding-strategy screening, low model influence). A variable meets the criterion
# when its RMSE is at most 2x the declared measurement/digitization uncertainty.
CREDIBILITY_RMSE_OVER_SIGMA_MAX = 2.0


def load_bionova_reference_dataset(path: str | Path | None = None) -> dict:
    """Load ``data/bionova_nistcho_2026.json`` (UTF-8 JSON) and return it as a dict."""
    with open(path or DATASET_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def bionova_process_description(
    condition: str = "stratyx_30_W_m3", dataset: dict | None = None
) -> ProcessDescription:
    """Exact Bionova protocol (Ref. 2, pp. 3-4) as a validated ProcessDescription.

    ``mode="static"`` with ``glucose_feedback_in_static=True`` (fixed boluses plus the
    pre-feed glucose rule < 2 -> 5 g/L), 0.25 L vessel, initial fill 0.76 (190 mL),
    sparge 0.5 mL/min / 190 mL, DO 30 %, 36.5 -> 34.0 C on day 7, 14 days;
    ``condition`` selects P/V (30 or 19 W/m3). Every value is read from the dataset.
    """
    ds = dataset or load_bionova_reference_dataset()
    if condition not in CONDITION_SETS:
        raise ValueError(f"unknown condition {condition!r}; expected one of {sorted(CONDITION_SETS)}")
    proto = ds["protocol"]
    return ProcessDescription(
        mode="static",
        glucose_feedback_in_static=True,
        vessel_volume_L=proto["vessel_volume_L"],
        initial_fill_fraction=proto["initial_fill_fraction"],
        power_density_W_m3=ds[CONDITION_SETS[condition]]["power_density_W_m3"],
        sparge_vvm=proto["sparge_vvm_derived"],
        temp_initial_C=proto["temp_initial_C"],
        temp_shift_C=proto["temp_shift_C"],
        temp_shift_day=proto["temp_shift_day"],
        do_setpoint_pct=proto["do_setpoint_pct"],
        ph_setpoint=proto["ph_setpoint"],
        ph_deadband=proto["ph_deadband"],
        glucose_min_threshold_g_L=proto["glucose_trigger_g_L"],
        glucose_refill_target_g_L=proto["glucose_target_g_L"],
        duration_days=proto["duration_days"],
        o2_enrichment_enabled=True,
    )


def simulate_bionova_condition(
    condition: str = "stratyx_30_W_m3",
    kinetics: CHOKineticParameters | None = None,
    dataset: dict | None = None,
) -> dict:
    """Run the twin on the exact Bionova protocol for ``condition``."""
    return simulate_cho_fed_batch(bionova_process_description(condition, dataset), kinetics=kinetics)


def _series_points(series: dict, include_day0: bool = False):
    days, values = series["days"], series["values"]
    keep = [(int(d), float(v)) for d, v in zip(days, values) if include_day0 or int(d) != 0]
    return [d for d, _ in keep], np.array([v for _, v in keep], dtype=float)


def calibration_residuals(sim_res: dict, dataset: dict) -> np.ndarray:
    """Weighted residuals (model - data) / uncertainty over the calibration set.

    Day 0 is excluded (it is the initial condition, not a prediction). Every variable
    uses its declared digitization uncertainty as sigma, including the two printed
    day-14 values, so the six variables are dimensionless and comparable.
    """
    daily = sim_res["daily_pre_feed"]
    res = []
    for key, series in dataset["calibration_set"]["series"].items():
        state_key = SERIES_TO_STATE[key]
        days, obs = _series_points(series)
        model = np.array([daily[d][state_key] for d in days], dtype=float)
        res.append((model - obs) / float(series["uncertainty_abs"]))
    return np.concatenate(res)


def _kinetics_from_vector(names, x, base: CHOKineticParameters) -> CHOKineticParameters:
    return replace(base, **{n: float(v) for n, v in zip(names, x)})


def run_parameter_calibration(
    free_parameters=CALIBRATED_PARAMETER_NAMES,
    initial_guess: dict | None = None,
    dataset: dict | None = None,
    base_kinetics: CHOKineticParameters = CALIBRATED_KINETICS,
    max_nfev: int = 300,
) -> dict:
    """Calibrate the free kinetic parameters on Bionova Stratyx 30 W/m3.

    ``scipy.optimize.least_squares(method="trf")`` minimises the weighted residuals
    of ``calibration_residuals`` within ``PARAMETER_BOUNDS``. Parameters not listed
    in ``free_parameters`` keep their ``base_kinetics`` value (fixed modeling
    assumptions). The shipped constants of ``src/bioreactor_twin.py`` are the
    output of this function with the defaults; passing a longer list reproduces
    the extended screening reported in docs/03.
    """
    ds = dataset or load_bionova_reference_dataset()
    names = list(free_parameters)
    guess = dict(CALIBRATION_INITIAL_GUESS)
    guess.update(initial_guess or {})
    lo = np.array([PARAMETER_BOUNDS[n][0] for n in names], dtype=float)
    hi = np.array([PARAMETER_BOUNDS[n][1] for n in names], dtype=float)
    x0 = np.clip(np.array([guess[n] for n in names], dtype=float), lo, hi)
    n_obs = len(calibration_residuals(simulate_bionova_condition("stratyx_30_W_m3", base_kinetics, ds), ds))
    config = bionova_process_description("stratyx_30_W_m3", ds)

    def fun(x):
        kin = _kinetics_from_vector(names, x, base_kinetics)
        try:
            return calibration_residuals(simulate_cho_fed_batch(config, kinetics=kin), ds)
        except (RuntimeError, ValueError, FloatingPointError):
            return np.full(n_obs, 1.0e3)

    t0 = time.perf_counter()
    opt = least_squares(
        fun, x0, bounds=(lo, hi), method="trf", jac="3-point", diff_step=1e-3,
        x_scale="jac", max_nfev=max_nfev,
    )
    elapsed = time.perf_counter() - t0
    span = hi - lo
    at_lower = (opt.x - lo) <= 1e-4 * span
    at_upper = (hi - opt.x) <= 1e-4 * span
    near_lower = (opt.x - lo) <= 1e-2 * span
    near_upper = (hi - opt.x) <= 1e-2 * span
    active = np.asarray(opt.active_mask) != 0
    at_bound = at_lower | at_upper | active
    calibrated = _kinetics_from_vector(names, opt.x, base_kinetics)
    table = []
    for i, n in enumerate(names):
        # AT_BOUND: on the bound (TRF active constraint or within 0.01 % of the span).
        # NEAR_BOUND: within 1 % of the span; the data push towards the bound.
        if at_bound[i]:
            flag = "AT_BOUND"
        elif near_lower[i] or near_upper[i]:
            flag = "NEAR_BOUND"
        else:
            flag = "interior"
        side = "lower" if near_lower[i] else ("upper" if near_upper[i] else "")
        table.append({
            "parameter": n,
            "initial_guess": float(x0[i]),
            "value": float(opt.x[i]),
            "lower_bound": float(lo[i]),
            "upper_bound": float(hi[i]),
            "status": flag,
            "bound_side": side,
        })
    return {
        "param_names": names,
        "x": opt.x.copy(),
        "x0": x0,
        "bounds": (lo, hi),
        "cost": float(opt.cost),
        "ssr_weighted": float(2.0 * opt.cost),
        "n_observations": int(len(opt.fun)),
        "n_parameters": len(names),
        "success": bool(opt.success),
        "status": int(opt.status),
        "message": str(opt.message),
        "nfev": int(opt.nfev),
        "elapsed_s": elapsed,
        "parameter_table": table,
        "calibrated_kinetics": calibrated,
        "opt_result": opt,
    }


def calibration_cost(kinetics: CHOKineticParameters = CALIBRATED_KINETICS, dataset: dict | None = None) -> float:
    """0.5 * sum of squared weighted residuals (least_squares cost) for ``kinetics``."""
    ds = dataset or load_bionova_reference_dataset()
    r = calibration_residuals(simulate_bionova_condition("stratyx_30_W_m3", kinetics, ds), ds)
    return float(0.5 * np.dot(r, r))


def _metric_block(model: np.ndarray, obs: np.ndarray, sigma: float) -> dict:
    resid = model - obs
    n = int(obs.size)
    rmse = float(math.sqrt(float(np.mean(resid ** 2))))
    ss_res = float(np.sum(resid ** 2))
    ss_tot = float(np.sum((obs - obs.mean()) ** 2))
    span = float(obs.max() - obs.min()) if n > 1 else 0.0
    return {
        "n": n,
        "R2": (1.0 - ss_res / ss_tot) if (n > 2 and ss_tot > 0.0) else None,
        "RMSE": rmse,
        "NRMSE_pct": (100.0 * rmse / span) if span > 0.0 else None,
        "bias": float(np.mean(resid)),
        "max_abs_error": float(np.max(np.abs(resid))),
        "sigma": float(sigma),
        "rmse_over_sigma": rmse / float(sigma),
        "fraction_within_sigma": float(np.mean(np.abs(resid) <= sigma + 1e-12)),
        "meets_credibility_criterion": bool(rmse <= CREDIBILITY_RMSE_OVER_SIGMA_MAX * float(sigma)),
    }


def compute_validation_metrics(sim_res: dict, dataset: dict, condition: str) -> dict:
    """R2, RMSE, NRMSE (% of the observed range) and day-14 error per variable.

    ``condition`` = "stratyx_30_W_m3" (in-sample, the six calibration series) or
    "stratyx_19_W_m3" (out-of-sample: VCD series plus the day-14 and lactate-peak
    points). Day 0 (initial condition) is excluded. R2 is reported only for series
    with more than two points.
    """
    if condition not in CONDITION_SETS:
        raise ValueError(f"unknown condition {condition!r}")
    block = dataset[CONDITION_SETS[condition]]
    daily = sim_res["daily_pre_feed"]
    variables = {}
    for key, series in block["series"].items():
        state_key = SERIES_TO_STATE[key]
        days, obs = _series_points(series)
        model = np.array([daily[d][state_key] for d in days], dtype=float)
        m = _metric_block(model, obs, series["uncertainty_abs"])
        last_obs, last_mod = float(obs[-1]), float(model[-1])
        m.update({
            "day14_observed": last_obs if days[-1] == 14 else None,
            "day14_model": last_mod if days[-1] == 14 else None,
            "day14_abs_error": (last_mod - last_obs) if days[-1] == 14 else None,
            "day14_rel_error_pct": (100.0 * (last_mod - last_obs) / last_obs) if days[-1] == 14 and last_obs else None,
            "days": days,
            "observed": obs.tolist(),
            "model": model.tolist(),
        })
        variables[key] = m
    points = {}
    for key, pt in block.get("points", {}).items():
        if key == "lactate_peak_g_L":
            lac = [(daily[d]["L"], d) for d in sorted(daily)]
            mod, mod_day = max(lac)
        else:
            state_key = {"viability_d14_pct": "viability_pct", "lactate_d14_g_L": "L",
                         "nh3_d14_mmol_L": "NH3", "titer_d14_g_L": "Titer"}[key]
            mod, mod_day = daily[int(pt["day"])][state_key], int(pt["day"])
        err = float(mod) - float(pt["value"])
        points[key] = {
            "observed": float(pt["value"]),
            "observed_day": int(pt["day"]),
            "model": float(mod),
            "model_day": int(mod_day),
            "abs_error": err,
            "rel_error_pct": 100.0 * err / float(pt["value"]),
            "sigma": float(pt["uncertainty_abs"]),
            "within_sigma": bool(abs(err) <= float(pt["uncertainty_abs"]) + 1e-12),
            "within_2sigma": bool(abs(err) <= 2.0 * float(pt["uncertainty_abs"]) + 1e-12),
        }
    return {
        "condition": condition,
        "role": block["role"],
        "power_density_W_m3": block["power_density_W_m3"],
        "variables": variables,
        "points": points,
    }


def compute_jacobian_identifiability(opt_result, param_names, collinearity_threshold: float = 0.90,
                                     rse_identifiable_max_pct: float = 50.0) -> dict:
    """Practical identifiability from the Jacobian at the least-squares optimum.

    J is the Jacobian of the weighted residuals; Js = J * diag(|theta|) is the
    relative-sensitivity matrix. Reports the singular values of Js, cond(Js) =
    s_max/s_min, the covariance s^2 (J^T J)^-1 with s^2 = SSR/(m - n) restricted to
    the parameters not at a bound, relative standard errors (RSE), the
    correlation matrix and every pair with |r| > ``collinearity_threshold``. A
    parameter is declared identifiable when it is not at a bound and its RSE is at
    most ``rse_identifiable_max_pct`` %.
    """
    names = list(param_names)
    x = np.asarray(opt_result.x, dtype=float)
    J = np.asarray(opt_result.jac, dtype=float)
    r = np.asarray(opt_result.fun, dtype=float)
    m, n = J.shape
    Js = J * np.abs(x)[None, :]
    sv = np.linalg.svd(Js, compute_uv=False)
    cond = float(sv[0] / sv[-1]) if sv[-1] > 0 else float("inf")
    active = np.asarray(getattr(opt_result, "active_mask", np.zeros(n)), dtype=int) != 0
    free_idx = [i for i in range(n) if not active[i]]
    dof = max(1, m - len(free_idx))
    s2 = float(np.dot(r, r) / dof)
    rse = {nm: None for nm in names}
    corr_full = np.full((n, n), np.nan)
    if free_idx:
        Jf = J[:, free_idx]
        cov = s2 * np.linalg.pinv(Jf.T @ Jf)
        se = np.sqrt(np.clip(np.diag(cov), 0.0, None))
        with np.errstate(divide="ignore", invalid="ignore"):
            corr = cov / np.outer(se, se)
        for a, i in enumerate(free_idx):
            rse[names[i]] = float(100.0 * se[a] / abs(x[i])) if x[i] != 0 else float("inf")
            for b, j in enumerate(free_idx):
                corr_full[i, j] = corr[a, b]
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            if np.isfinite(corr_full[i, j]) and abs(corr_full[i, j]) > collinearity_threshold:
                pairs.append({"pair": (names[i], names[j]), "r": float(corr_full[i, j])})
    verdict = {}
    for i, nm in enumerate(names):
        if active[i]:
            verdict[nm] = {"identifiable": False, "reason": "AT_BOUND (optimum on the bound; not estimable inside it)",
                           "additional_data": ADDITIONAL_DATA_NEEDED.get(nm, "")}
        elif rse[nm] is None or not math.isfinite(rse[nm]) or rse[nm] > rse_identifiable_max_pct:
            verdict[nm] = {"identifiable": False, "reason": f"RSE {rse[nm]:.0f} % > {rse_identifiable_max_pct:.0f} %"
                           if rse[nm] is not None and math.isfinite(rse[nm]) else "singular",
                           "additional_data": ADDITIONAL_DATA_NEEDED.get(nm, "")}
        else:
            verdict[nm] = {"identifiable": True, "reason": f"RSE {rse[nm]:.1f} %", "additional_data": ""}
    return {
        "param_names": names,
        "n_observations": int(m),
        "n_parameters": int(n),
        "singular_values": sv.tolist(),
        "condition_number": cond,
        "residual_variance": s2,
        "relative_standard_error_pct": rse,
        "correlation_matrix": corr_full.tolist(),
        "collinear_pairs": pairs,
        "at_bound": [names[i] for i in range(n) if active[i]],
        "verdict": verdict,
        "identifiable": [nm for nm in names if verdict[nm]["identifiable"]],
        "not_identifiable": [nm for nm in names if not verdict[nm]["identifiable"]],
    }


_CONVERGENCE_SERIES = ("vcd", "dead_cell_density", "glucose_g_L", "lactate_g_L", "nh3_mmol_L", "titer_g_L")


def _max_rel_errors(test: dict, ref: dict) -> dict:
    out = {}
    for key in _CONVERGENCE_SERIES:
        a = np.asarray(test[key], dtype=float)
        b = np.asarray(ref[key], dtype=float)
        scale = float(np.max(np.abs(b)))
        out[key] = float(np.max(np.abs(a - b)) / scale) if scale > 0 else 0.0
    out["overall"] = max(out.values())
    return out


def check_numerical_convergence(config: ProcessDescription | None = None,
                                kinetics: CHOKineticParameters | None = None) -> dict:
    """Verification of the integrator (ASME V&V 40 'calculation verification').

    Production RK45 (rtol 1e-6, atol 1e-9) is compared on the 0.1 d grid with RK45
    and Radau at rtol 1e-9 / atol 1e-12, and the v1.3.2 explicit Euler scheme
    (dt = 0.1 d) is compared with the same reference. The error of each series is
    max|y - y_ref| / max|y_ref| (relative to the series magnitude).
    """
    cfg = config or bionova_process_description("stratyx_30_W_m3")
    t0 = time.perf_counter()
    prod = simulate_cho_fed_batch(cfg, kinetics=kinetics)
    t_prod = time.perf_counter() - t0
    ref_rk = simulate_cho_fed_batch(cfg, kinetics=kinetics, method="RK45", rtol=1e-9, atol=1e-12)
    ref_radau = simulate_cho_fed_batch(cfg, kinetics=kinetics, method="Radau", rtol=1e-9, atol=1e-12)
    euler = simulate_cho_fed_batch(cfg, kinetics=kinetics, method="Euler", euler_dt=0.1)
    return {
        "production_vs_rk45_1e9": _max_rel_errors(prod, ref_rk),
        "production_vs_radau_1e9": _max_rel_errors(prod, ref_radau),
        "rk45_1e9_vs_radau_1e9": _max_rel_errors(ref_rk, ref_radau),
        "euler_dt0p1_vs_rk45_1e9": _max_rel_errors(euler, ref_rk),
        "production_runtime_ms": 1000.0 * t_prod,
        "production_nfev": prod["solver"]["nfev_total"],
        "reference_nfev": ref_rk["solver"]["nfev_total"],
        "fallback_used": prod["solver"]["fallback_used"],
    }
