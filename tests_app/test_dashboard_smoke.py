"""Headless smoke test for app/dashboard.py (Streamlit AppTest).

Kept OUTSIDE tests/ on purpose: tests/conftest.py writes the FDA CSA OQ log for
the 13 qualified tests, and this UI smoke test must not change that record.

Run with:  python -m pytest tests_app -v
"""

import warnings
from pathlib import Path

import pytest
from streamlit.testing.v1 import AppTest

from src.models import ProcessDescription
from src.bioreactor_twin import simulate_cho_fed_batch
from src.spc_six_sigma import GORSKY_TABLE_6_2_TORQUE_N30, compute_process_capability

APP = str(Path(__file__).resolve().parent.parent / "app" / "dashboard.py")
TIMEOUT = 60


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
    oq_pass = _metric_values(at, "Pruebas aprobadas")
    assert len(oq_pass) == 1
    _by_label(at.button, "Registrar cambio").click().run()
    _clean(at)
    _by_label(at.button, "Verificar cadena SHA-256").click().run()
    _clean(at)
    _by_label(at.button, "Demostrar falla de integridad").click().run()
    _clean(at)
    assert len(at.session_state["audit_logger"].records) == 1
    assert at.session_state["audit_logger"].verify_chain_integrity() is True
