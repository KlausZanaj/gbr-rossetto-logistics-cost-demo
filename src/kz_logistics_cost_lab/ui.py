"""Single-page Italian demo. Economics come only from the shared engine."""
from dataclasses import asdict

import pandas as pd
import streamlit as st

from .excel import make_workbook
from .io import load_inputs
from .optimization import analyze, assess_union, group_for
from .reporting import assumption_rows, comparison_rows, euros, proposal_rows, quality_rows, spend_rows, summary
from .sample_data import CASE_NAMES, read_sample
from .state import Upload, parse_calendar, request_signature, synchronize, uploaded_files
from .validation import validate


def euro_text(value):
    return "Non calcolabile" if value is None else f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".") + " €"


def decimal_text(value):
    return "n.d." if value is None else f"{value:.2f}".replace(".", ",")


def frame(rows):
    # Arrow can struggle with arbitrary precision Decimal columns. Display
    # them as exact text; only the chart below uses presentation floats.
    return pd.DataFrame([{key: str(value) if hasattr(value, "as_tuple") else value for key, value in row.items()} for row in rows])


def evaluation_rows(evaluations, selected=None):
    return [{"Servizio": e.service_id, "Tariffa": e.tariff_id, "Esito": "NOT_FEASIBLE" if not e.feasible else ("SELEZIONATO" if selected and e.tariff_id == selected.tariff_id else "ALTERNATIVA AMMISSIBILE"),
             "Costo EUR": euro_text(e.cost) if e.feasible else "Non calcolabile",
             "Arrivo previsto": str(e.expected_delivery_date or "n.d."), "Motivo": " | ".join(e.reasons) or "Vincoli rispettati"} for e in evaluations]


def render_result(result):
    st.subheader("Qualità dei dati e copertura")
    if result.data.blocked:
        st.error("Analisi bloccata: correggere gli errori strutturali indicati. Costi e download non disponibili.")
        st.dataframe(frame(quality_rows(result)), hide_index=True, width="stretch")
        return
    kpi = summary(result)
    columns = st.columns(4)
    columns[0].metric("Spedizioni importate", kpi["imported"])
    columns[1].metric("Confrontabili", kpi["comparable"])
    columns[1].caption("Copertura: " + decimal_text(kpi["coverage_pct"]) + ("%" if kpi["coverage_pct"] is not None else ""))
    columns[2].metric("Escluse", len(result.exclusions))
    columns[3].metric("Ordini confrontabili", kpi["orders"])
    st.caption(f"Escluse per dati: {kpi['excluded_data']} · Fuori perimetro: {kpi['excluded_scope']} · Baseline non confrontabile: {kpi['excluded_baseline']}. Ogni spedizione esclusa è contata una sola volta.")
    if result.issues:
        with st.expander("Motivi, ID e colonne extra", expanded=not kpi["comparable"]):
            st.dataframe(frame(quality_rows(result)), hide_index=True, width="stretch")
    else:
        st.success("Nessuna anomalia rilevata nei dati caricati.")

    st.subheader("Confronto dei costi")
    st.caption("Costi IVA esclusa, solo sulla popolazione confrontabile. Le conclusioni non rappresentano la spesa totale aziendale.")
    for column, scenario, label in zip(st.columns(3), ("c0", "c1", "c2"), ("C0 · Piano originale", "C1 · Scelta servizio", "C2 · Consolidamento"), strict=True):
        column.metric(label, euro_text(kpi[scenario + "_eur"]))
    if not kpi["comparable"]:
        st.info("Nessuna spedizione" if not kpi["imported"] else "Nessuna spedizione confrontabile. Costi e risparmi: Non calcolabile.")
    else:
        for column, key, label in zip(st.columns(3), ("service_saving_cents", "consolidation_saving_cents", "saving_cents"),
                                      ("Effetto cambio servizio", "Ulteriore consolidamento", "Risparmio totale"), strict=True):
            column.metric(label, euro_text(euros(kpi[key])))
        st.caption("Risparmio totale / C0: " + decimal_text(kpi["saving_pct"]) + ("%" if kpi["saving_pct"] is not None else "") + ". Le due componenti sommano al risparmio totale.")
        chart = pd.DataFrame({"Scenario": ["C0", "C1", "C2"], "Costo EUR": [float(kpi[key + "_eur"]) for key in ("c0", "c1", "c2")]})
        st.bar_chart(chart, x="Scenario", y="Costo EUR", color="#3B7C8A", height=230)
        rows = []
        for scenario in ("c0", "c1", "c2"):
            rows.append({"Scenario": scenario.upper(), "Spedizioni / gruppi": kpi["groups"] if scenario == "c2" else kpi["comparable"],
                         "EUR per spedizione / gruppo": euro_text(kpi[scenario + "_per_shipment_eur"]),
                         "EUR per ordine": euro_text(kpi[scenario + "_per_order_eur"]),
                         "Spedizioni / gruppi per ordine": decimal_text(kpi[scenario + "_shipments_per_order"]),
                         "Peso reale kg": kpi["actual_weight_kg"], "Peso tassabile kg": kpi[scenario + "_billable_weight_kg"]})
        st.dataframe(frame(rows), hide_index=True, width="stretch")
        st.caption(f"In C2 il denominatore EUR per spedizione diventa il numero di gruppi. Gli ordini confrontabili restano {kpi['orders']}; i {kpi['packages']} colli fisici sono conservati.")

        st.subheader("Proposte operative")
        st.caption("Una riga per gruppo finale, inclusi quelli invariati. Euristica a coppie: nessuna garanzia di ottimo globale.")
        proposals = proposal_rows(result)
        zones = sorted({row["zona"] for row in proposals})
        zone = st.selectbox("Filtro visivo zona", ["Tutte", *zones], key="zone_filter")
        visible = [row for row in proposals if zone == "Tutte" or row["zona"] == zone]
        display = [{key: row[key] for key in ("shipment_id_membri", "destinazione", "zona", "colli", "servizio_C2", "arrivo_previsto", "promessa_minima", "C0_EUR", "C1_EUR", "C2_EUR", "risparmio_EUR", "motivazione")} for row in visible]
        st.dataframe(frame(display), hide_index=True, width="stretch")
        options = [group.proposal_id for group in result.groups]
        by_id = {group.proposal_id: group for group in result.groups}
        selected = st.selectbox("Dettaglio proposta", options, format_func=lambda pid: ", ".join(by_id[pid].members), key="selected_proposal")
        group = by_id[selected]
        st.caption("ID proposta: " + group.proposal_id)
        st.dataframe(frame(evaluation_rows((group.selected,), group.selected)), hide_index=True, width="stretch")
        with st.expander("Traccia del calcolo e colli conservati"):
            st.json(asdict(group.selected.trace), expanded=False)
        member_choices = {c.shipment.shipment_id: c for c in result.choices if c.shipment.shipment_id in group.members}
        selected_shipment = st.selectbox("Alternative per spedizione originaria", list(member_choices), key="selected_shipment")
        choice = member_choices[selected_shipment]
        st.dataframe(frame(evaluation_rows(choice.alternatives, choice.selected)), hide_index=True, width="stretch")
        with st.expander("Verifica una coppia di spedizioni"):
            partners = [c.shipment.shipment_id for c in result.choices if c.shipment.shipment_id != selected_shipment]
            if partners:
                partner_id = st.selectbox("Seconda spedizione", partners, key="selected_pair")
                partner = next(c for c in result.choices if c.shipment.shipment_id == partner_id)
                details = assess_union(result, group_for((selected_shipment,), choice.selected), group_for((partner_id,), partner.selected))
                st.write(details["status"] + (": " + " | ".join(details["reasons"]) if details["reasons"] else ""))
                if details["saving_cents"] is not None:
                    st.write("Guadagno rispetto ai due singoli C1: " + euro_text(euros(details["saving_cents"])))
                st.dataframe(frame(evaluation_rows(details["evaluations"])), hide_index=True, width="stretch")
                st.caption("Valutazione della sola coppia selezionata. Non riesegue il piano C2 e non va sommata ai risparmi del piano.")
        with st.expander("Confronto originario C0/C1 e distribuzione della spesa"):
            st.dataframe(frame([{k: v for k, v in row.items() if not k.startswith("traccia")} for row in comparison_rows(result)]), hide_index=True, width="stretch")
            st.dataframe(frame(spend_rows(result)), hide_index=True, width="stretch")

    with st.expander("Dati di origine e ipotesi del risultato"):
        for table in result.data.inputs.tables:
            st.write(table.name)
            st.dataframe(pd.DataFrame(table.records(), columns=table.columns), hide_index=True, width="stretch")
        st.dataframe(frame(assumption_rows(result)), hide_index=True, width="stretch")
    if st.session_state.get("report_bytes"):
        st.download_button("Scarica report Excel", data=st.session_state["report_bytes"], file_name="kz-logistics-report.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="download_report")
        st.caption("Formule semplici con risultati cached. L'XLSX non riesegue il motore quando si modificano le origini.")
    elif st.session_state.get("report_error"):
        st.error(st.session_state["report_error"])


def main():
    st.set_page_config(page_title="KZ Logistics Cost Lab", page_icon="📦", layout="wide")
    st.title("KZ Logistics Cost Lab")
    st.caption("Demo indipendente — dati e tariffe sintetici")
    st.write("Confronta il piano originale, la scelta del servizio e il consolidamento prudente, mantenendo partenze, promesse e colli.")
    mode = st.radio("Origine dei dati", ("Sample incluso", "Carica tre CSV"), horizontal=True, key="input_mode")
    files, uploads, errors, sample = {}, [], [], ""
    if mode == "Sample incluso":
        sample = st.selectbox("Dataset sintetico", ("demo", *CASE_NAMES), format_func=lambda name: "Demo principale · 200 spedizioni" if name == "demo" else name, key="sample_name")
        try:
            files = read_sample(sample)
            uploads = [Upload(name, content) for name, content in files.items()]
        except OSError:
            errors.append("Sample non leggibile. Verificare i file in data/sample con il comando --check documentato.")
    else:
        st.caption("Esattamente shipments.csv, packages.csv e tariffs.csv. UTF-8, virgola separatrice, punto decimale. Massimo 10 MiB per file; tutto in memoria della sessione.")
        uploaded = st.file_uploader("Carica i tre CSV", type=["csv"], accept_multiple_files=True, key="csv_uploads")
        uploads = [Upload(item.name, item.getvalue()) for item in uploaded]
        files, upload_errors = uploaded_files(uploads)
        errors.extend(upload_errors)
    with st.expander("Ipotesi e calendario", expanded=True):
        st.write("Giorni lavorativi: lunedì–venerdì, Europe/Rome. I festivi non inseriti sono ignorati: questo non è un calendario italiano completo.")
        st.caption("EUR IVA esclusa. Fuel sull'intera base sintetica. Solo spedizioni standard con baseline ammissibile. Nessun reimballaggio; nessuna partenza o promessa modificata.")
        calendar_text = st.text_area("Date non lavorative aggiuntive", placeholder="2026-09-08\n2026-12-08", help="Date ISO YYYY-MM-DD, una per riga o separate da virgole.", key="calendar_input")
    config = None
    try:
        config = parse_calendar(calendar_text)
    except ValueError as exc:
        errors.append(str(exc))
    signature = request_signature(mode, uploads, calendar_text, sample)
    synchronize(st.session_state, signature)
    for message in errors:
        st.warning(message)
    if st.button("Analizza e confronta", type="primary", disabled=bool(errors), key="analyze"):
        with st.spinner("Validazione, tariffazione e confronto in corso…"):
            result = analyze(validate(load_inputs(files), config), config)
            st.session_state["analysis_result"] = result
            st.session_state.pop("report_bytes", None)
            st.session_state.pop("report_error", None)
            if not result.data.blocked:
                try:
                    st.session_state["report_bytes"] = make_workbook(result)
                except (ValueError, OverflowError) as exc:
                    st.session_state["report_error"] = "Report Excel non generabile: " + str(exc)
    result = st.session_state.get("analysis_result")
    if result is not None and not errors:
        render_result(result)
    else:
        st.info("Scegli i dati e premi Analizza e confronta. Qualsiasi cambiamento agli input o al calendario richiede una nuova analisi.")
    st.divider()
    st.caption("Prototipo indipendente per portfolio. Dati e tariffe sintetici. Nessuna integrazione aziendale verificata.")
