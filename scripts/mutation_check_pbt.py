"""In-memory mutation check of the property-based suite (tests_pbt/).

Each mutant runs in a fresh Python process that imports the target module, rewrites one
function's source in memory (``inspect.getsource``, exact-once text replacement, ``exec`` in
the module namespace) and runs the targeted property with pytest. A mutant is KILLED when the
property fails with an AssertionError and a Hypothesis falsifying example. The baseline run
of the whole suite on the unmutated code must pass first. Nothing under src/ is written: the
SHA-256 of every file under src/ is compared before and after the run.

Every property must kill at least one mutant; M1-M3 are the three faults of the task
specification (pH exclusivity, Part 11 payload field, vessel capacity clamp).

Usage (repository root):  python scripts/mutation_check_pbt.py [--only M1,M3]
Exit status: 0 when the baseline passes, every mutant is killed and src/ is unchanged.
"""

import argparse
import hashlib
import json
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SUITE = "tests_pbt/test_gxp_invariants_pbt.py"
P01 = "test_pbt_01_fedbatch_positivity_capacity_and_mass_conservation"
P02 = "test_pbt_02_ph_split_range_universal_exclusivity_and_bounds"
P03 = "test_pbt_03_oxygen_scaleup_monotonicity_and_enrichment"
P04 = "test_pbt_04_amab_design_space_bounds_gate"
P05 = "test_pbt_05_mkt_arrhenius_jensen_and_vtb_contraction"
P06 = "test_pbt_06_part11_audit_chain_any_field_tamper_detection"
P07 = "test_pbt_07_spc_tost_symmetry_and_capability_ordering"
TWIN, AMAB, AUDIT = "src.bioreactor_twin", "src.amab_design_space", "src.audit_trail_part11"
THERMAL, SPC = "src.thermal_vtb_mkt", "src.spc_six_sigma"

# (id, fault, property, [(module, qualname, [(anchor, replacement), ...]), ...])
MUTANTS = (
    ("M1", "pH split-range exclusivity removed (inverted dead-band, independent branches)", P02,
     [(TWIN, "compute_split_range_ph_actuators", [(
         "    if current_ph > setpoint + deadband:\n"
         "        co2_valve_pct = min(100, kp * (current_ph - (setpoint + deadband)))\n"
         "        base_pump_pct = 0.0\n"
         "    elif current_ph < setpoint - deadband:\n"
         "        base_pump_pct = min(100, kp * ((setpoint - deadband) - current_ph))\n"
         "        co2_valve_pct = 0.0\n"
         "    else:\n"
         "        co2_valve_pct = 0.0\n"
         "        base_pump_pct = 0.0\n",
         "    co2_valve_pct = max(0.0, min(100, kp * (current_ph - (setpoint - deadband))))\n"
         "    base_pump_pct = max(0.0, min(100, kp * ((setpoint + deadband) - current_ph)))\n")])]),
    ("M2", "Part 11: human_approved left out of the SHA-256 payload (the v1.1.x regression)", P06,
     [(AUDIT, "AuditTrailLogger.append_record", [
         ('f"{old_value}|{new_value}|{reason_for_change}|"', 'f"{old_value}|{new_value}|{reason_for_change}"'),
         ('f"{bool(human_approved)}".encode("utf-8")', '"".encode("utf-8")')]),
      (AUDIT, "AuditTrailLogger.verify_chain_integrity", [
          ("f\"{record['new_value']}|{record['reason_for_change']}|\"",
           "f\"{record['new_value']}|{record['reason_for_change']}\""),
          ("f\"{bool(record['human_approved'])}\".encode(\"utf-8\")", '"".encode("utf-8")')])]),
    ("M3", "vessel capacity clamp disabled (bolus never scaled to the headspace)", P01,
     [(TWIN, "simulate_cho_fed_batch", [
         ("scale = headspace / requested if requested > 0.0 else 0.0", "scale = 1.0")])]),
    ("M4", "A-Mab gate: design_space_holds no longer requires in_bounds", P04,
     [(AMAB, "evaluate_amab_design_space", [("in_bounds and z1 >= 4.60", "z1 >= 4.60")])]),
    ("M5", "O2 driving force sign error (OTR grows with the DO set-point)", P03,
     [(AMAB, "compute_scale_up_engineering", [
         ("gas_saturation_ratio - (do_percent / 100.0)", "gas_saturation_ratio + (do_percent / 100.0)")])]),
    ("M6", "MKT Arrhenius sign error (exp(+dH/RT))", P05,
     [(THERMAL, "calculate_mkt_celsius", [
         ("math.exp(-(dH_over_R) / T_K)", "math.exp((dH_over_R) / T_K)"),
         ("(dH_over_R) / (-math.log(mean_exp))", "(dH_over_R) / (math.log(mean_exp))")])]),
    ("M7", "VTB extrapolates (lead) instead of lagging: leaves the air range", P05,
     [(THERMAL, "apply_vtb_filter", [
         ("vtb.append(alpha * air_temps_C[k] + (1 - alpha) * vtb[-1])",
          "vtb.append(air_temps_C[k] + alpha * (air_temps_C[k] - vtb[-1]))")])]),
    ("M8", "Nyquist folding replaced by a modulo (alias can exceed f_Nyquist)", P05,
     [(THERMAL, "analyze_fft_nyquist", [
         ("folded_alias = abs(true_dominant - fs_cph * round(true_dominant / fs_cph))",
          "folded_alias = true_dominant % fs_cph")])]),
    ("M9", "TOST reduced to one one-sided test (p_tost = p_lower)", P07,
     [(SPC, "compare_bioreactor_equivalence_tost", [("p_tost = max(p_lower, p_upper)", "p_tost = p_lower")])]),
    ("M10", "Ppk computed with max instead of min", P07,
     [(SPC, "compute_process_capability", [("ppk = min(ppu, ppl)", "ppk = max(ppu, ppl)")])]),
    ("M11", "bolus added without diluting the broth (mass created)", P01,
     [(TWIN, "simulate_cho_fed_batch", [("state = state * dilution", "state = state * 1.0")])]),
)
REQUIRED = {"M1", "M2", "M3"}
PROPERTIES = (P01, P02, P03, P04, P05, P06, P07)
NOT_APPLIED_EXIT = 97
# Pytest failure lines only (never the echoed test source): "E   assert ..." / "E   AssertionError:
# ..." for a single failure, "| AssertionError: ..." inside an exception group. Pytest prints the
# failing source line just before it.
ASSERTION_LINE = re.compile(r"^\s*E\s+((?:AssertionError\b|assert\s).*)$|^\s+\|\s+(AssertionError\b.*)$")

# Runs in the child process: apply the mutant in memory, then run pytest.
BOOTSTRAP = r"""
import importlib, inspect, json, sys, textwrap
spec = json.loads(sys.argv[1])
sys.path.insert(0, spec["root"])
for module_name, qualname, replacements in spec["targets"]:
    module = importlib.import_module(module_name)
    *parents, name = qualname.split(".")
    owner = module
    for part in parents:
        owner = getattr(owner, part)
    source = textwrap.dedent(inspect.getsource(getattr(owner, name)))
    for anchor, replacement in replacements:
        count = source.count(anchor)
        if count != 1:
            print(f"MUTATION NOT APPLIED: anchor found {count} times in {qualname}: {anchor!r}")
            sys.exit(spec["not_applied_exit"])
        source = source.replace(anchor, replacement)
    namespace = {}
    exec(compile(source, f"<mutant {spec['id']}: {qualname}>", "exec"), vars(module), namespace)
    setattr(owner, name, namespace[name])
    assert getattr(owner, name).__code__.co_filename.startswith("<mutant")
import pytest
sys.exit(pytest.main(spec["pytest_args"]))
"""


def _src_fingerprint() -> dict:
    return {p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted((ROOT / "src").rglob("*")) if p.is_file() and "__pycache__" not in p.parts}


def _run(mutant_id: str, targets, node_ids) -> tuple[int, str, float]:
    spec = {
        "id": mutant_id, "root": str(ROOT), "targets": targets, "not_applied_exit": NOT_APPLIED_EXIT,
        "pytest_args": ["-q", "-p", "no:cacheprovider", "--no-header", "-W", "error::DeprecationWarning",
                        *[f"{SUITE}::{n}" for n in node_ids]],
    }
    start = time.perf_counter()
    proc = subprocess.run([sys.executable, "-c", BOOTSTRAP, json.dumps(spec)], cwd=ROOT,
                          capture_output=True, text=True, encoding="utf-8", timeout=600)
    return proc.returncode, proc.stdout + proc.stderr, time.perf_counter() - start


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="In-memory mutation check of tests_pbt/.")
    parser.add_argument("--only", help="comma-separated mutant ids, e.g. M1,M3")
    args = parser.parse_args(argv)
    selected = [m for m in MUTANTS if not args.only or m[0] in args.only.split(",")]
    before = _src_fingerprint()

    code, output, seconds = _run("baseline", [], PROPERTIES)
    print(f"baseline  unmutated code, {len(PROPERTIES)} properties: "
          f"{'PASS' if code == 0 else 'FAIL'} ({seconds:.1f} s)")
    if code != 0:
        print(output[-3000:])
        return 1

    killed_by = {p: [] for p in PROPERTIES}
    all_killed = True
    for mutant_id, fault, prop, targets in selected:
        code, output, seconds = _run(mutant_id, targets, [prop])
        # Hypothesis prints "Falsifying example:" (older releases) or "Failing test case:"; the
        # failure must be an assertion ("E   assert ..." or "AssertionError: ..."), not a crash.
        counterexample = "Falsifying example" in output or "Failing test case" in output
        lines = output.splitlines()
        hit = next((i for i, line in enumerate(lines) if ASSERTION_LINE.match(line)), None)
        assertion = statement = ""
        if hit is not None:
            match = ASSERTION_LINE.match(lines[hit])
            assertion = match.group(1) or match.group(2)
            statement = lines[hit - 1].strip(" |>") if hit > 0 else ""  # source line pytest printed
        if code == NOT_APPLIED_EXIT:
            verdict = "NOT APPLIED"
        elif code == 1 and counterexample and assertion:
            verdict = "KILLED"
            killed_by[prop].append(mutant_id)
        elif code == 0:
            verdict = "SURVIVED"
        else:
            verdict = f"ERROR (pytest exit {code})"
        all_killed &= verdict == "KILLED"
        tag = "required" if mutant_id in REQUIRED else "extra"
        print(f"{mutant_id:<4} [{tag:<8}] {verdict:<11} {prop[:11]}  {fault} ({seconds:.1f} s)")
        if verdict == "KILLED":
            if statement:
                print(f"     failing:  {statement[:150]}")
            print(f"     evidence: {assertion[:150]}")
        else:
            print(output[-3000:])

    unchanged = _src_fingerprint() == before
    print(f"src/ unchanged after the run: {unchanged} (SHA-256 of {len(before)} files)")
    if not args.only:
        missing = [p for p, ids in killed_by.items() if not ids]
        print("properties without a killed mutant:", ", ".join(missing) if missing else "none")
        all_killed &= not missing
    return 0 if all_killed and unchanged else 1


if __name__ == "__main__":
    sys.exit(main())
