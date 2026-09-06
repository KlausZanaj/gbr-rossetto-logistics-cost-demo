from pathlib import Path
from streamlit.testing.v1 import AppTest
import pytest

from kz_logistics_cost_lab.sample_data import read_sample
from kz_logistics_cost_lab.state import MAX_UPLOAD_BYTES, RESULT_KEYS, Upload, parse_calendar, request_signature, synchronize, uploaded_files

ROOT = Path(__file__).resolve().parents[1]


def test_upload_exact_names_sizes_no_paths():
    uploads = [Upload(name, content) for name, content in read_sample().items()]
    files, errors = uploaded_files(uploads)
    assert not errors and len(files) == 3
    assert uploaded_files(uploads[:2])[1]
    assert uploaded_files(uploads + uploads[:1])[1]
    assert uploaded_files([Upload("../shipments.csv", b"x"), *uploads[1:]])[1]
    assert uploaded_files([Upload("shipments.csv", b"x" * (MAX_UPLOAD_BYTES + 1)), *uploads[1:]])[1]
    assert not uploaded_files([Upload("shipments.csv", b"x" * MAX_UPLOAD_BYTES), *uploads[1:]])[1]


def test_same_name_same_size_content_change_invalidates_every_result():
    before = [Upload("shipments.csv", b"abc")]
    after = [Upload("shipments.csv", b"abd")]
    signature = request_signature("upload", before, "")
    state = {"request_signature": signature, **{key: "old" for key in RESULT_KEYS}}
    assert not synchronize(state, signature)
    assert synchronize(state, request_signature("upload", after, ""))
    assert all(key not in state for key in RESULT_KEYS)
    assert request_signature("sample", before, "") != signature
    assert request_signature("upload", before, "2026-09-08") != signature
    assert request_signature("upload", [], "") != signature


def test_config_immutable_and_invalid():
    config = parse_calendar("2026-09-08,2026-09-08\n2026-12-08")
    assert len(config.nonworking_dates) == 2
    with pytest.raises(ValueError):
        parse_calendar("2026-02-30")


def test_app_sample_button_download_and_visual_filters_do_not_rerun(monkeypatch):
    import kz_logistics_cost_lab.ui as ui
    calls = []
    original = ui.analyze

    def counted(*args):
        calls.append(1)
        return original(*args)

    monkeypatch.setattr(ui, "analyze", counted)
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    assert not app.exception and not app.metric and not calls
    app.button(key="analyze").click().run()
    assert not app.exception and len(calls) == 1
    assert app.session_state["report_bytes"][:2] == b"PK"
    assert app.get("download_button")
    before = app.session_state["analysis_result"]
    app.selectbox(key="zone_filter").select("NORD").run()
    assert not app.exception and len(calls) == 1
    assert app.session_state["analysis_result"] is before
    second = before.groups[1].proposal_id
    app.selectbox(key="selected_proposal").select(second).run()
    assert not app.exception and len(calls) == 1
    app.text_area(key="calendar_input").set_value("2026-09-08").run()
    assert not app.exception and not app.metric and not app.get("download_button")
    assert "analysis_result" not in app.session_state
    app.button(key="analyze").click().run()
    assert not app.exception and len(calls) == 2
    app.text_area(key="calendar_input").set_value("invalid").run()
    assert app.button(key="analyze").disabled and not app.metric and not app.get("download_button")


def test_app_switch_mode_clears_old_results_and_sample_changes():
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    app.selectbox(key="sample_name").select("CONSOLIDATION_SAVING").run()
    app.button(key="analyze").click().run()
    assert not app.exception
    assert any(metric.value == "14,00 €" for metric in app.metric)
    app.selectbox(key="sample_name").select("NO_SAVING").run()
    assert not app.metric and not app.get("download_button")
    app.button(key="analyze").click().run()
    assert not app.exception
    app.radio(key="input_mode").set_value("Carica tre CSV").run()
    assert not app.exception and not app.metric and not app.get("download_button")
    assert app.button(key="analyze").disabled


def test_app_changed_content_and_structural_error_cannot_show_previous_result(monkeypatch):
    import kz_logistics_cost_lab.ui as ui
    files = read_sample("CONSOLIDATION_SAVING")
    monkeypatch.setattr(ui, "read_sample", lambda name: dict(files))
    app = AppTest.from_file(str(ROOT / "app.py"), default_timeout=20).run()
    app.button(key="analyze").click().run()
    assert app.metric and app.get("download_button")
    files["shipments.csv"] = files["shipments.csv"].replace(b"shipment_id", b"shipment_xx", 1)
    app.run()
    assert not app.metric and not app.get("download_button")
    app.button(key="analyze").click().run()
    assert not app.exception and app.error and not app.metric and not app.get("download_button")
    assert app.session_state["analysis_result"].data.blocked
