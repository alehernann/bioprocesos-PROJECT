"""Headless smoke test for app/dashboard.py (Streamlit AppTest).

Kept OUTSIDE tests/ on purpose: tests/conftest.py writes the FDA CSA OQ log for
the 13 qualified tests, and this UI smoke test must not change that record.

Run with:  python -m pytest tests_app -v
"""

import ast
import hashlib
import json
import warnings
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.models import ProcessDescription
from src.bioreactor_twin import simulate_cho_fed_batch
from src.spc_six_sigma import (
    GORSKY_TABLE_6_2_TORQUE_N30,
    compute_moving_range_summary,
    compute_process_capability,
)

ROOT = Path(__file__).resolve().parent.parent
APP = str(ROOT / "app" / "dashboard.py")
OQ_LOG = ROOT / "docs" / "04_Automated_OQ_Execution_Log.md"
OQ_TESTS = ROOT / "tests" / "test_csa_oq_validation.py"
TIMEOUT = 60
RERUN_TIMEOUT = 240


def _clean(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert not at.warning, [w.value for w in at.warning]


def _by_label(elements, label):
    matches = [e for e in elements if e.label == label]
    assert matches, f"widget not found: {label}"
    return matches[0]


def _metric_values(at, label):
    return [m.value for m in at.metric if m.label == label]


def _run_strict(action, timeout=TIMEOUT):
    """Run an AppTest action with DeprecationWarning promoted to an error."""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        return action.run(timeout=timeout)


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _n_qualified_tests():
    tree = ast.parse(OQ_TESTS.read_text(encoding="utf-8"))
    return sum(1 for n in tree.body if isinstance(n, ast.FunctionDef) and n.name.startswith("test_"))


@pytest.fixture()
def at():
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    _clean(app)
    return app


def test_default_render_is_clean_and_kpis_are_live(at):
    static = simulate_cho_fed_batch(ProcessDescription(mode="static", vessel_volume_L=2.0))
    closed = simulate_cho_fed_batch(ProcessDescription(mode="closed_loop", vessel_volume_L=2.0))
    titers = _metric_values(at, "Titulo final (g/L)")
    assert titers == [f"{static['final_titer_g_L']:.4f}", f"{closed['final_titer_g_L']:.4f}"]
    gain = (closed["final_titer_g_L"] - static["final_titer_g_L"]) / static["final_titer_g_L"] * 100
    assert _metric_values(at, "Ganancia real de titulo (%)") == [f"{gain:+.2f}"]

    cap = compute_process_capability(GORSKY_TABLE_6_2_TORQUE_N30, lsl=5.0, usl=12.0)
    assert _metric_values(at, "Pp") == [f"{cap['pp']:.2f}"]
    assert _metric_values(at, "Cp within") == [f"{cap['cp_within']:.2f}"]


def test_spc_metrics_are_live_and_non_zero(at):
    cap = compute_process_capability(GORSKY_TABLE_6_2_TORQUE_N30)
    mr = compute_moving_range_summary(GORSKY_TABLE_6_2_TORQUE_N30)
    # The new helper must agree with the within sigma used by compute_process_capability.
    assert mr["std_within"] == cap["std_within"]

    expected = {
        "Pp": f"{cap['pp']:.2f}",
        "Ppk": f"{cap['ppk']:.2f}",
        "Ppu": f"{cap['ppu']:.2f}",
        "Ppl": f"{cap['ppl']:.2f}",
        "Std global (N)": f"{cap['std']:.2f}",
        "Cp within": f"{cap['cp_within']:.2f}",
        "Cpk within": f"{cap['cpk_within']:.2f}",
        "Cpu within": f"{cap['cpu_within']:.2f}",
        "Cpl within": f"{cap['cpl_within']:.2f}",
        "Std within (N)": f"{cap['std_within']:.2f}",
        "MR-bar (N)": f"{mr['mr_bar']:.2f}",
        "Media global (N)": f"{cap['mean']:.2f}",
        "N (muestras)": f"{len(GORSKY_TABLE_6_2_TORQUE_N30)}",
    }
    for label, value in expected.items():
        shown = _metric_values(at, label)
        assert shown == [value], (label, shown, value)
        assert float(shown[0]) > 0.0, f"{label} rendered as zero"
    # The combined label that truncated N is gone.
    assert _metric_values(at, "Media / std global (N)") == []


def test_shewhart_legend_is_below_the_plot(at):
    charts = at.get("plotly_chart")
    specs = [json.loads(c.proto.spec) for c in charts]
    shewhart = [s for s in specs if "Shewhart" in json.dumps(s["layout"].get("title", {}))]
    assert len(shewhart) == 1
    legend = shewhart[0]["layout"]["legend"]
    assert legend["orientation"] == "h"
    assert legend["yref"] == "container" and legend["yanchor"] == "bottom" and legend["y"] == 0
    # Every chart uses the same below-plot legend, so none can overlap a title.
    for s in specs:
        assert s["layout"]["legend"]["yref"] == "container"


def test_volume_slider_switches_to_kg(at):
    _by_label(at.slider, "Volumen nominal del biorreactor (L)").set_value(15000.0).run()
    _clean(at)
    closed = simulate_cho_fed_batch(ProcessDescription(mode="closed_loop", vessel_volume_L=15000.0))
    masses = _metric_values(at, "Masa cosechada de mAb (kg)")
    assert masses[1] == f"{closed['harvested_mass_g'] / 1000.0:,.3f} kg"


def test_scale_presets_and_amab_mode(at):
    for preset in at.selectbox(key="scale_preset").options:
        at.selectbox(key="scale_preset").set_value(preset).run()
        _clean(at)
    for option in at.radio(key="amab_mode").options:
        at.radio(key="amab_mode").set_value(option).run()
        _clean(at)
        _by_label(at.slider, "Osmolalidad (mOsm/kg)").set_value(440.0).run()
        _clean(at)


def test_fft_intervals_and_sources(at):
    for source in _by_label(at.radio, "Senal analizada").options:
        _by_label(at.radio, "Senal analizada").set_value(source).run()
        for dt in (5.0, 15.0, 30.0, 60.0):
            _by_label(at.selectbox, "target_sampling_interval_min (min)").set_value(dt).run()
            _clean(at)


def test_oq_viewer_and_audit_trail(at):
    n_tests = _n_qualified_tests()
    assert _metric_values(at, "Pruebas aprobadas") == [f"{n_tests}/{n_tests}"]
    # Timestamp is a caption now (no truncated st.metric).
    assert _metric_values(at, "Ejecucion (UTC)") == []
    assert any("Ejecucion (UTC):" in c.value for c in at.caption)
    # Verdict code path is read live from tests/conftest.py.
    assert any("overall" in c.value and "ACCEPTABLE" in c.value for c in at.code)
    # OQ table carries the requirement from each test docstring.
    tables = [d.value for d in at.dataframe if "Requisito verificado (docstring)" in d.value.columns]
    assert tables and len(tables[0]) == n_tests
    assert (tables[0]["Requisito verificado (docstring)"] != "n/d").all()

    _run_strict(_by_label(at.button, "Registrar cambio").click())
    _clean(at)
    _run_strict(_by_label(at.button, "Verificar integridad").click())
    _clean(at)
    _run_strict(_by_label(at.button, "Demostrar falla de integridad").click())
    _clean(at)
    assert any("se rompe en el registro #0" in m.value for m in at.markdown)
    _run_strict(_by_label(at.button, "Simular cambio del gemelo digital sin aprobacion humana").click())
    _clean(at)
    assert any("Bloqueado. PermissionError" in m.value for m in at.markdown)
    assert len(at.session_state["audit_logger"].records) == 1
    assert at.session_state["audit_logger"].verify_chain_integrity() is True


def test_oq_rerun_button_runs_suite_without_touching_committed_log(at):
    before = _sha256(OQ_LOG)
    n_tests = _n_qualified_tests()
    _run_strict(_by_label(at.button, "Re-ejecutar verificacion OQ ahora").click(), timeout=RERUN_TIMEOUT)
    _clean(at)
    rerun = at.session_state["oq_rerun"]
    assert rerun["ok"], rerun["error"]
    assert rerun["returncode"] == 0
    assert rerun["oq"]["verdict"] == "ACCEPTABLE"
    assert rerun["committed_unchanged"] is True
    assert _metric_values(at, "Aprobadas (re-ejecucion)") == [f"{n_tests}/{n_tests}"]
    assert _metric_values(at, "Fallidas o con error (re-ejecucion)") == ["0"]
    assert _sha256(OQ_LOG) == before
