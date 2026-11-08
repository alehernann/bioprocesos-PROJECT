"""Pytest hooks that auto-generate the FDA CSA Automated OQ Execution Log.

On every test run these hooks accumulate per-test results (ID, CSA risk category,
result and duration) and, on session finish, write
``docs/04_Automated_OQ_Execution_Log.md``. The generated log provides the objective
evidence of operational-qualification acceptability required by the FDA Computer
Software Assurance (CSA) guidance, Section V.A.6.

The CSA category for each test is derived from its name, per the risk assessment in
``docs/02_FDA_CSA_Risk_Assessment_2026.md``:

* ``test_oq_*``          -> "Scripted Testing (High Process Risk)"
* ``test_exploratory_*`` -> "Unscripted / Error-Guessing (Not High Process Risk)"
"""

import datetime
import importlib.metadata
import platform
from pathlib import Path

# Accumulated per-test records across the session.
_OQ_RESULTS: list[dict] = []

# Packages whose installed versions are recorded for the qualified environment.
_REPORTED_PACKAGES = (
    "numpy",
    "scipy",
    "pandas",
    "pydantic",
    "plotly",
    "streamlit",
    "pytest",
)


def _csa_category(nodeid: str) -> str:
    """Map a test node id to its FDA CSA risk category."""
    name = nodeid.split("::")[-1]
    if name.startswith("test_exploratory_"):
        return "Unscripted / Error-Guessing (Not High Process Risk)"
    if name.startswith("test_oq_"):
        return "Scripted Testing (High Process Risk)"
    return "Uncategorized"


def pytest_runtest_logreport(report):
    """Collect the result and duration of each executed test.

    The main pass/fail outcome is taken from the ``call`` phase; a setup-phase
    failure (collection/fixture error) is recorded as an ERROR so it still appears
    in the execution log.
    """
    if report.when == "call":
        if report.passed:
            result = "PASSED"
        elif report.failed:
            result = "FAILED"
        elif report.skipped:
            result = "SKIPPED"
        else:
            result = "UNKNOWN"
        _OQ_RESULTS.append(
            {
                "id": report.nodeid,
                "category": _csa_category(report.nodeid),
                "result": result,
                "duration": float(report.duration),
            }
        )
    elif report.when == "setup" and (report.failed or report.skipped):
        result = "SKIPPED" if report.skipped else "ERROR"
        _OQ_RESULTS.append(
            {
                "id": report.nodeid,
                "category": _csa_category(report.nodeid),
                "result": result,
                "duration": float(report.duration),
            }
        )


def _package_versions() -> list[tuple[str, str]]:
    """Return (name, version) for each reported package, guarded for absence."""
    versions = []
    for name in _REPORTED_PACKAGES:
        try:
            versions.append((name, importlib.metadata.version(name)))
        except importlib.metadata.PackageNotFoundError:
            versions.append((name, "not installed"))
    return versions


def pytest_sessionfinish(session, exitstatus):
    """Write the Automated OQ Execution Log once the test session completes."""
    report_path = Path(__file__).parent.parent / "docs" / "04_Automated_OQ_Execution_Log.md"

    now_utc = datetime.datetime.now(datetime.timezone.utc)
    total = len(_OQ_RESULTS)
    passed = sum(1 for r in _OQ_RESULTS if r["result"] == "PASSED")
    failed = sum(1 for r in _OQ_RESULTS if r["result"] == "FAILED")
    errored = sum(1 for r in _OQ_RESULTS if r["result"] == "ERROR")
    skipped = sum(1 for r in _OQ_RESULTS if r["result"] == "SKIPPED")

    lines: list[str] = []
    lines.append("# Automated OQ Execution Log")
    lines.append("")
    lines.append(
        "FDA Computer Software Assurance (CSA) Operational Qualification (OQ) "
        "automated execution record."
    )
    lines.append("")
    lines.append(
        "> This document is GENERATED automatically by `tests/conftest.py` on every "
        "`pytest` run. Do not edit it by hand."
    )
    lines.append("")

    lines.append("## Execution Environment")
    lines.append("")
    lines.append(
        f"- **Execution timestamp (UTC):** {now_utc.strftime('%Y-%m-%d %H:%M:%S %Z')}"
    )
    lines.append(f"- **Python version:** {platform.python_version()}")
    lines.append(f"- **Platform:** {platform.platform()}")
    lines.append("- **Qualified package versions:**")
    for name, version in _package_versions():
        lines.append(f"    - {name}: {version}")
    lines.append("")

    lines.append("## Execution Summary")
    lines.append("")
    lines.append(f"- **Total tests executed:** {total}")
    lines.append(f"- **Passed:** {passed}")
    lines.append(f"- **Failed:** {failed}")
    lines.append(f"- **Errored:** {errored}")
    lines.append(f"- **Skipped:** {skipped}")
    lines.append(f"- **Pytest exit status:** {exitstatus}")
    lines.append("")

    lines.append("## Test Results")
    lines.append("")
    lines.append("| ID | CSA Category | Result | Duration (s) |")
    lines.append("| --- | --- | --- | --- |")
    for record in _OQ_RESULTS:
        lines.append(
            f"| {record['id']} | {record['category']} | {record['result']} "
            f"| {record['duration']:.4f} |"
        )
    lines.append("")

    lines.append("## Acceptability Statement (FDA CSA Section V.A.6)")
    lines.append("")
    overall = "ACCEPTABLE" if (failed == 0 and errored == 0) else "NOT ACCEPTABLE"
    lines.append(
        "In accordance with the FDA guidance *Computer Software Assurance for "
        "Production and Quality System Software*, Section V.A.6, this automated OQ "
        "execution constitutes objective evidence that the software performs as "
        "intended for its risk-based use. The scripted high-process-risk tests "
        "(`test_oq_*`) and the unscripted / error-guessing tests "
        "(`test_exploratory_*`) above, together with their recorded results and "
        "durations, document the assurance activities performed."
    )
    lines.append("")
    lines.append(
        f"Based on the results recorded in this log, the OQ execution status is "
        f"**{overall}** for this test run. This status means that the recorded "
        f"assurance activities completed with the stated result; it is not a "
        f"regulatory approval, batch release decision, or quality signature."
    )
    lines.append("")

    report_path.write_text("\n".join(lines), encoding="utf-8")
