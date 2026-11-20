"""Headless smoke test for app/dashboard.py (Streamlit AppTest).

Kept OUTSIDE tests/ on purpose: tests/conftest.py writes the FDA CSA OQ log
(docs/04) for the qualified OQ tests in tests/, and this UI smoke test must not
change that record. The CI runs it as a separate step after tests/.

17 tests here; together with the 24 OQ tests in tests/ the full run is 41 tests.
Every interaction runs with DeprecationWarning promoted to an error.

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
from src.amab_design_space import AMAB_MEASURED_KLA_H_INV, compute_scale_up_engineering
from src.bioreactor_twin import simulate_cho_fed_batch
from src.model_validation import (
    compute_validation_metrics,
    load_bionova_reference_dataset,
    simulate_bionova_condition,
)
from src.spc_six_sigma import (
    GORSKY_TABLE_6_2_TORQUE_N30,
    compare_bioreactor_equivalence_tost,
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
        return [w.value for w in at.warning if "oxigeno insuficiente" in w.value]

    assert at.slider(key="do_setpoint_pct").value == 30.0
    otr_30 = otr_shown()
    assert otr_30 == [f"{compute_scale_up_engineering(0.015, 26.0)['otr_mmol_L_h']:.2f}"]
    assert alarms() == []
    assert any("URS-06 OK" in s.value for s in at.success)

    _run_strict(at.slider(key="do_setpoint_pct").set_value(85.0))
    # The oxygen alarm is an intended model warning (st.warning), never an error.
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]
    assert [w.value for w in at.warning] == alarms()
    expected = compute_scale_up_engineering(0.015, 26.0, do_percent=85.0)
    assert expected["oxygen_sufficient"] is False
    assert otr_shown() == [f"{expected['otr_mmol_L_h']:.2f}"]
    assert otr_shown() != otr_30
    assert len(alarms()) == 1

    _run_strict(at.slider(key="do_setpoint_pct").set_value(30.0))
    _clean(at)
    assert otr_shown() == otr_30
    assert alarms() == []


def test_do_slider_changes_scaleup_and_twin(at):
    """DO set-point drives OTR always; the twin responds only to the real DO (v1.4.0).

    With O2 enrichment on, DO 85 % is held by the controller and the culture is the same
    as at 30 % (no false hypoxia); DO 10 % is real hypoxia (f_do < 1) and changes the KPIs.
    With enrichment off, DO 85 % saturates the controller and the air-limited transfer
    lowers the titer.
    """
    def titers():
        return _metric_values(at, "Titulo final (g/L)")

    def viabilities():
        return _metric_values(at, "Viabilidad final (%)")

    base_otr = _metric_values(at, "OTR (mmol/L/h)")
    base_titer, base_viab = titers(), viabilities()
    for do, same_as_base in ((10.0, False), (85.0, True)):
        _run_strict(at.slider(key="do_setpoint_pct").set_value(do))
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
        assert (titers() == base_titer) is same_as_base, do
    _run_strict(_by_label(at.toggle, "Enriquecimiento con O2 puro (A-Mab Fig. 3.12)").set_value(False))
    assert not at.exception, [e.value for e in at.exception]
    air = [
        simulate_cho_fed_batch(
            ProcessDescription(mode=m, vessel_volume_L=2.0, do_setpoint_pct=85.0, o2_enrichment_enabled=False)
        )
        for m in ("static", "closed_loop")
    ]
    assert titers() == [f"{r['final_titer_g_L']:.4f}" for r in air]
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
    _run_strict(_by_label(at.slider, "Volumen nominal del biorreactor (L)").set_value(15000.0))
    _clean(at)
    closed = simulate_cho_fed_batch(ProcessDescription(mode="closed_loop", vessel_volume_L=15000.0))
    masses = _metric_values(at, "Masa cosechada de mAb (kg)")
    assert masses[1] == f"{closed['harvested_mass_g'] / 1000.0:,.3f} kg"


def test_scale_presets_and_amab_mode(at):
    # Presets map 1:1 to the A-Mab Table 3.22 columns and show the measured kLa. At
    # VCC 15e6 cells/mL and DO 30 the O2 model warning appears only at 2, 500, 1,000
    # and 5,000 L (kLa 8-10 h^-1); never as an error.
    presets = {
        "Personalizado": None,
        "2 L (modelo estandar scale-down)": 2.0,
        "500 L piloto": 500.0,
        "1,000 L": 1000.0,
        "5,000 L": 5000.0,
        "15,000 L comercial (referencia A-Mab)": 15000.0,
        "25,000 L (Future)": 25000.0,
    }
    warn_volumes = {2.0, 500.0, 1000.0, 5000.0}
    assert list(at.selectbox(key="scale_preset").options) == list(presets)
    for preset, volume in presets.items():
        _run_strict(at.selectbox(key="scale_preset").set_value(preset))
        assert not at.exception, [e.value for e in at.exception]
        assert not at.error, [e.value for e in at.error]
        shown = [w.value for w in at.warning]
        if volume in warn_volumes:
            assert len(shown) == 1 and "oxigeno insuficiente" in shown[0], (preset, shown)
            assert "Tabla 3.23" in shown[0]
        else:
            assert shown == [], (preset, shown)
        if volume is not None:
            kla = AMAB_MEASURED_KLA_H_INV[volume]
            assert _metric_values(at, "kLa (1/h)") == [f"{kla:.2f}"], preset
    assert any("coinciden" in c.value and "20.00 h^-1" in c.value for c in at.caption)
    _run_strict(at.selectbox(key="scale_preset").set_value("15,000 L comercial (referencia A-Mab)"))
    _clean(at)
    for option in at.radio(key="amab_mode").options:
        _run_strict(at.radio(key="amab_mode").set_value(option))
        _clean(at)
        _run_strict(_by_label(at.slider, "Osmolalidad (mOsm/kg)").set_value(440.0))
        _clean(at)


def test_fft_intervals_and_sources(at):
    for source in _by_label(at.radio, "Senal analizada").options:
        _run_strict(_by_label(at.radio, "Senal analizada").set_value(source))
        for dt in (5.0, 15.0, 30.0, 60.0):
            _run_strict(_by_label(at.selectbox, "target_sampling_interval_min (min)").set_value(dt))
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


def _chart_specs(app):
    return [json.loads(c.proto.spec) for c in app.get("plotly_chart")]


def _chart(app, title):
    for spec in _chart_specs(app):
        if json.dumps(spec["layout"].get("title", {})).find(f'"{title}"') >= 0:
            return spec
    raise AssertionError(f"chart not found: {title}")


def _banners(app):
    return [m.value for m in app.markdown if 'class="bp-banner"' in m.value]


def test_nh3_and_do_real_charts_and_controller_banner(at):
    """Tab 1 plots NH3 and the real DO from the twin and states controller saturation vs real hypoxia."""
    runs = {
        m: simulate_cho_fed_batch(ProcessDescription(mode=m, vessel_volume_L=2.0))
        for m in ("static", "closed_loop")
    }
    nh3 = _chart(at, "Amonio NH3")
    do = _chart(at, "DO real en el liquido")
    for idx, mode in ((0, "static"), (1, "closed_loop")):
        assert nh3["data"][idx]["y"] == pytest.approx(runs[mode]["nh3_mmol_L"], rel=1e-12)
        assert do["data"][idx]["y"] == pytest.approx(runs[mode]["do_real_pct"], rel=1e-12)
    assert sum("DO real = set-point (30 %)" in b for b in _banners(at)) == 2

    _run_strict(_by_label(at.toggle, "Enriquecimiento con O2 puro (A-Mab Fig. 3.12)").set_value(False))
    _clean(at)
    air = simulate_cho_fed_batch(
        ProcessDescription(mode="closed_loop", vessel_volume_L=2.0, o2_enrichment_enabled=False)
    )
    assert air["min_do_real_pct"] < 15.0
    hypoxia = [b for b in _banners(at) if "hipoxia real" in b]
    assert len(hypoxia) == 2
    assert f"{air['min_do_real_pct']:.1f} %" in hypoxia[1]


def test_bionova_validation_block_matches_model_validation(at):
    """The Bionova block overlays the dataset and its table reproduces compute_validation_metrics."""
    ds = load_bionova_reference_dataset()
    m30 = compute_validation_metrics(simulate_bionova_condition("stratyx_30_W_m3", dataset=ds), ds, "stratyx_30_W_m3")
    m19 = compute_validation_metrics(simulate_bionova_condition("stratyx_19_W_m3", dataset=ds), ds, "stratyx_19_W_m3")
    tables = [d.value for d in at.dataframe if "Cumple RMSE <= 2 sigma" in d.value.columns]
    assert len(tables) == 1
    table = tables[0]
    assert len(table) == len(m30["variables"]) + len(m19["variables"]) + len(m19["points"])
    for label, metrics in (("30 W/m3 (calibracion)", m30), ("19 W/m3 (fuera de muestra)", m19)):
        for key, v in metrics["variables"].items():
            row = table[(table["Condicion"] == label) & (table["Variable"] == key)].iloc[0]
            assert row["RMSE"] == f"{v['RMSE']:.3f}"
            assert row["R2"] == ("n/a" if v["R2"] is None else f"{v['R2']:.3f}")
    vcd = _chart(at, "VCD (1e6 cel/mL): modelo vs Bionova")
    names = [tr.get("name") for tr in vcd["data"]]
    assert "Bionova 30 W/m3 (digitalizado)" in names and "Bionova 30 W/m3 (impreso)" in names
    assert "Bionova 19 W/m3 (fuera de muestra)" in names
    digitized = vcd["data"][names.index("Bionova 30 W/m3 (digitalizado)")]
    assert digitized["error_y"]["value"] == ds["calibration_set"]["series"]["vcd_1e6_mL"]["uncertainty_abs"]


def test_duration_slider_and_shift_clamp(at):
    """Duration slider feeds the twin; a shift later than the run is clamped, never an error."""
    for days in (21, 5):
        _run_strict(_by_label(at.slider, "Duracion del cultivo en el gemelo (d)").set_value(days))
        _clean(at)
        shift = min(7.0, float(days))
        expected = [
            simulate_cho_fed_batch(
                ProcessDescription(mode=m, vessel_volume_L=2.0, duration_days=days, temp_shift_day=shift)
            )
            for m in ("static", "closed_loop")
        ]
        assert _metric_values(at, "Titulo final (g/L)") == [f"{r['final_titer_g_L']:.4f}" for r in expected]
        clamp = [c.value for c in at.caption if "Dia del cambio termico ajustado" in c.value]
        assert (len(clamp) == 1) is (days == 5)


def test_tost_levene_section_and_stability_chips(at):
    """Tab 4 shows I-MR stability and the TOST + Levene result of compare_bioreactor_equivalence_tost."""
    cap = compute_process_capability(GORSKY_TABLE_6_2_TORQUE_N30)
    assert _metric_values(at, "Puntos fuera de control (regla 1)") == [f"{cap['n_out_of_control_points']}"]
    html = " ".join(m.value for m in at.markdown)
    assert "in_statistical_control" in html and "capability_assumptions_met" in html
    a = [8.1, 7.9, 8.4, 8.0, 8.3, 7.8]
    b = [8.6, 8.9, 9.1, 8.7, 9.0, 8.8]
    for margin in (1.0, 0.5):
        _run_strict(at.number_input(key="tost_margin").set_value(margin))
        _clean(at)
        tost = compare_bioreactor_equivalence_tost(a, b, equiv_margin=margin)
        assert _metric_values(at, "p TOST") == [f"{tost['p_tost']:.4f}"]
        assert _metric_values(at, "p Levene") == [f"{tost['levene_p_value']:.4f}"]
        assert _metric_values(at, "IC 90 % de la diferencia") == [
            f"[{tost['ci_90_low']:+.3f}, {tost['ci_90_high']:+.3f}]"]
        word = "Equivalentes" if tost["statistically_equivalent"] else "No equivalentes"
        chips = [m.value for m in at.markdown if "statistically_equivalent" in m.value and "bp-chip" in m.value]
        assert len(chips) == 1 and f">{word}<" in chips[0]
