"""Headless smoke test for app/dashboard.py (Streamlit AppTest).

Kept OUTSIDE tests/ on purpose: tests/conftest.py writes the FDA CSA OQ log
(docs/04) for the qualified OQ tests in tests/, and this UI smoke test must not
change that record. The CI runs it as a separate step after tests/.

13 tests here; together with the 20 OQ tests in tests/ the full run is 33 tests.

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
from src.amab_design_space import compute_scale_up_engineering
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



def test_shear_or_texts_and_live_lactate_acid_note(at):
    texts = [m.value for m in at.markdown] + [c.value for c in at.caption]
    # Shear legends describe the OR gate (v1.3.0), never the old AND gate.
    assert any("P/V > 47.6 O sparge > 0.15" in t and "W/m3" in t for t in texts)
    assert sum("P/V > 47.6 O sparge > 0.15" in t for t in texts) >= 2
    assert not any("si P/V ya paso 47.6" in t for t in texts)
    # pH panel lactate note is computed from the live simulation (2.0 L default).
    lactate_mw = 90.08
    note = [t for t in texts if "Carga acida de lactato final" in t]
    assert len(note) == 1
    for mode in ("static", "closed_loop"):
        lac = simulate_cho_fed_batch(
            ProcessDescription(mode=mode, vessel_volume_L=2.0)
        )["lactate_g_L"][-1]
        assert f"{lac:.3f} g/L" in note[0]
        assert f"{lac / lactate_mw * 1000.0:.2f} mmol/L" in note[0]


def test_ph_deadband_slider_drives_split_range_panel(at):
    """The "Banda muerta de pH" slider governs the split-range panel (limits and CO2 opening)."""
    def ph_caption():
        return [c.value for c in at.caption if "Set-point de pH" in c.value]

    assert _by_label(at.slider, "Banda muerta de pH").value == pytest.approx(0.20)
    assert "CO2 por encima de 7.20 y base por debajo de 6.80" in ph_caption()[0]

    _run_strict(_by_label(at.slider, "Banda muerta de pH").set_value(0.10))
    _clean(at)
    captions = ph_caption()
    assert len(captions) == 1
    assert "CO2 por encima de 7.10 y base por debajo de 6.90" in captions[0]

    # Proportional CO2 branch: 150 * (7.15 - 7.10) = 7.50 %, base pump idle.
    _run_strict(_by_label(at.slider, "pH medido actual").set_value(7.15))
    _clean(at)
    assert _metric_values(at, "Valvula CO2 (%)") == ["7.50"]
    assert _metric_values(at, "Bomba de base (%)") == ["0.00"]
    assert len(at.exception) == 0


def test_do_slider_drives_otr_and_oxygen_alarm(at):
    def otr_shown():
        return _metric_values(at, "OTR (mmol/L/h)")

    def alarms():
        return [e.value for e in at.error if "oxigeno insuficiente" in e.value]

    assert at.slider(key="do_setpoint_pct").value == 30.0
    otr_30 = otr_shown()
    assert otr_30 == [f"{compute_scale_up_engineering(0.015, 26.0)['otr_mmol_L_h']:.2f}"]
    assert alarms() == []
    assert any("URS-06 OK" in s.value for s in at.success)

    at.slider(key="do_setpoint_pct").set_value(85.0).run()
    # The oxygen alarm is an intended st.error here, so check exceptions only.
    assert not at.exception, [e.value for e in at.exception]
    assert [e.value for e in at.error] == alarms()
    expected = compute_scale_up_engineering(0.015, 26.0, do_percent=85.0)
    assert expected["oxygen_sufficient"] is False
    assert otr_shown() == [f"{expected['otr_mmol_L_h']:.2f}"]
    assert otr_shown() != otr_30
    assert len(alarms()) == 1

    at.slider(key="do_setpoint_pct").set_value(30.0).run()
    _clean(at)
    assert otr_shown() == otr_30
    assert alarms() == []


def test_do_slider_changes_scaleup_and_twin(at):
    def titers():
        return _metric_values(at, "Titulo final (g/L)")

    def viabilities():
        return _metric_values(at, "Viabilidad final (%)")

    base_otr = _metric_values(at, "OTR (mmol/L/h)")
    base_titer, base_viab = titers(), viabilities()
    for do in (10.0, 85.0):
        at.slider(key="do_setpoint_pct").set_value(do).run()
        assert not at.exception, [e.value for e in at.exception]
        expected = [
            simulate_cho_fed_batch(
                ProcessDescription(mode=m, vessel_volume_L=2.0, do_setpoint_pct=do)
            )
            for m in ("static", "closed_loop")
        ]
        assert titers() == [f"{r['final_titer_g_L']:.4f}" for r in expected]
        assert viabilities() == [f"{r['final_viability_pct']:.2f}" for r in expected]
        assert _metric_values(at, "OTR (mmol/L/h)") != base_otr
        assert titers() != base_titer
    assert any("Afecta tanto el margen OTR >= OUR" in m.value for m in at.markdown)
    assert not any("Solo afecta el balance de oxigeno" in m.value for m in at.markdown)


def test_bolus_clipped_warning(monkeypatch):
    import src.bioreactor_twin as twin

    def warnings_shown(app):
        return [w.value for w in app.warning if "Volumen util al 100 %" in w.value]

    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    assert warnings_shown(app) == []

    # Real capacity clamp: start at 95 % fill so the feed train must be cut.
    monkeypatch.setattr(twin, "INITIAL_FILL_FRACTION", 0.95)
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        app = AppTest.from_file(APP, default_timeout=TIMEOUT).run()
    assert not app.exception, [e.value for e in app.exception]
    shown = warnings_shown(app)
    assert len(shown) == 1
    assert "receta estatica" in shown[0] and "lazo cerrado" in shown[0]

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
        "Std global (lb/in)": f"{cap['std']:.2f}",
        "Cp within": f"{cap['cp_within']:.2f}",
        "Cpk within": f"{cap['cpk_within']:.2f}",
        "Cpu within": f"{cap['cpu_within']:.2f}",
        "Cpl within": f"{cap['cpl_within']:.2f}",
        "Std within (lb/in)": f"{cap['std_within']:.2f}",
        "MR-bar (lb/in)": f"{mr['mr_bar']:.2f}",
        "Media global (lb/in)": f"{cap['mean']:.2f}",
        "N (muestras)": f"{len(GORSKY_TABLE_6_2_TORQUE_N30)}",
    }
    for label, value in expected.items():
        shown = _metric_values(at, label)
        assert shown == [value], (label, shown, value)
        assert float(shown[0]) > 0.0, f"{label} rendered as zero"
    # The old combined label (truncated, wrong unit) is gone.
    assert _metric_values(at, "Media / std global (lb/in)") == []


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
