"""In-memory XlsxWriter report. Binary numbers are presentation only."""
from io import BytesIO
from decimal import Decimal
import math

import xlsxwriter

from .domain import AnalysisResult
from .reporting import (COMPARISON_COLUMNS, PROPOSAL_COLUMNS, assumption_rows, comparison_rows,
                        euros, proposal_rows, quality_rows, spend_rows, summary)

SHEETS = ("Spedizioni", "Colli", "Tariffe", "Qualita_dati", "KPI", "Confronto", "Proposte", "Ipotesi")


def excel_number(value):
    if value is None:
        return "n.d."
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("Valore oltre la capacità numerica Excel; ridurre la scala dei dati per esportare. Il risultato Decimal del motore resta disponibile.")
    return number


def make_workbook(result: AnalysisResult) -> bytes:
    if result.data.blocked:
        raise ValueError("Export economico non disponibile per dati strutturalmente invalidi.")
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {"in_memory": True, "strings_to_formulas": False,
                                          "strings_to_urls": False, "strings_to_numbers": False})
    workbook.set_properties({"title": "KZ Logistics Cost Lab", "subject": "Confronto logistico su dati sintetici", "author": "KZ Logistics Cost Lab"})
    workbook.set_calc_mode("auto")
    formats = {
        "header": workbook.add_format({"bold": True, "font_name": "Arial", "font_size": 10, "font_color": "#FFFFFF", "bg_color": "#243B53", "text_wrap": True, "valign": "vcenter"}),
        "text": workbook.add_format({"font_name": "Arial", "font_size": 10, "valign": "top"}),
        "wrap": workbook.add_format({"font_name": "Arial", "font_size": 10, "valign": "top", "text_wrap": True}),
        "eur": workbook.add_format({"font_name": "Arial", "font_size": 10, "valign": "top", "num_format": '#,##0.00 "EUR"'}),
        "number": workbook.add_format({"font_name": "Arial", "font_size": 10, "valign": "top", "num_format": "#,##0.00"}),
        "int": workbook.add_format({"font_name": "Arial", "font_size": 10, "valign": "top", "num_format": "#,##0"}),
        "pct": workbook.add_format({"font_name": "Arial", "font_size": 10, "num_format": "0.00%"}),
        "title": workbook.add_format({"font_name": "Arial", "font_size": 12, "bold": True, "font_color": "#243B53"}),
    }
    sheets = {name: workbook.add_worksheet(name) for name in SHEETS}
    for sheet in sheets.values():
        sheet.hide_gridlines(2)
        sheet.set_default_row(18)
        sheet.freeze_panes(1, 0)
        sheet.set_zoom(90)

    def string(sheet, row, col, value, cell_format=None):
        text = str(value)
        if len(text) > 32767:
            raise ValueError("Una cella supera 32767 caratteri: Excel non può conservare integralmente questo input o questa traccia.")
        if sheet.write_string(row, col, text, cell_format or formats["text"]) != 0:
            raise ValueError("Dimensioni del report oltre i limiti Excel.")

    def cell(sheet, row, col, value, key="", raw=False):
        if value is None:
            string(sheet, row, col, "n.d.")
        elif raw or isinstance(value, str):
            string(sheet, row, col, value, formats["wrap"] if key in ("motivo", "motivazione") and not raw else None)
        elif isinstance(value, int):
            # Excel has only 15 significant decimal digits; preserve larger
            # exact integer cents as text instead of silently rounding them.
            if len(str(abs(value))) > 15:
                string(sheet, row, col, value)
            else:
                sheet.write_number(row, col, value, formats["int"])
        elif isinstance(value, Decimal):
            sheet.write_number(row, col, excel_number(value), formats["eur"] if "EUR" in key or "eur" in key else formats["number"])
        else:
            string(sheet, row, col, value)

    def table(sheet, columns, records, start=0, raw=False):
        if start + len(records) >= 1048576 or len(columns) > 16384:
            raise ValueError("Tabella oltre il numero di righe/colonne supportato da Excel.")
        sheet.set_row(start, 34)
        for col, key in enumerate(columns):
            string(sheet, start, col, key, formats["header"])
            max_length = max([len(key)] + [len(str(r.get(key, ""))) for r in records[:200]])
            sheet.set_column(col, col, min(48, max(16, max_length + 2)))
        for row, record in enumerate(records, start + 1):
            for col, key in enumerate(columns):
                cell(sheet, row, col, record.get(key), key, raw)
        sheet.autofilter(start, 0, start + len(records), len(columns) - 1)

    try:
        for name, source in (("Spedizioni", "shipments.csv"), ("Colli", "packages.csv"), ("Tariffe", "tariffs.csv")):
            origin = result.data.inputs.table(source)
            table(sheets[name], origin.columns, origin.records(), raw=True)
        quality = quality_rows(result)
        table(sheets["Qualita_dati"], ("livello", "codice", "file", "riga", "shipment_id", "causa_primaria", "campo", "motivo"), quality)
        sheets["Qualita_dati"].set_column(7, 7, 95, formats["wrap"])
        for row, record in enumerate(quality, 1):
            sheets["Qualita_dati"].set_row(row, 44 if len(record["motivo"]) > 90 else 28)

        proposals = proposal_rows(result)
        table(sheets["Proposte"], PROPOSAL_COLUMNS, proposals)
        # Full hashes/traces remain accessible in cells and the formula bar.
        sheets["Proposte"].set_column(0, 0, 82)
        sheets["Proposte"].set_column(23, 23, 54)
        sheets["Proposte"].set_column(25, 25, 70)

        kpi = summary(result)
        labels = {
            "imported": "Spedizioni importate", "comparable": "Spedizioni confrontabili", "coverage_pct": "Copertura (%)",
            "orders": "Ordini distinti confrontabili", "groups": "Gruppi finali C2", "packages": "Colli fisici confrontabili (invariati)",
            "excluded_data": "Escluse per dati", "excluded_scope": "Escluse fuori perimetro", "excluded_baseline": "Escluse per baseline non confrontabile",
            "actual_weight_kg": "Peso reale (kg)", "saving_cents": "Risparmio totale (centesimi)",
            "service_saving_cents": "Cambio servizio (centesimi)", "consolidation_saving_cents": "Consolidamento aggiuntivo (centesimi)", "saving_pct": "Risparmio (%)",
        }
        for scenario in ("c0", "c1", "c2"):
            for suffix, label in (("cents", "costo (centesimi)"), ("eur", "costo (EUR)"), ("per_shipment_eur", "EUR per spedizione/gruppo"),
                                  ("per_order_eur", "EUR per ordine"), ("shipments_per_order", "spedizioni/gruppi per ordine"), ("billable_weight_kg", "peso tassabile (kg)")):
                labels[scenario + "_" + suffix] = scenario.upper() + " " + label
        records = [{"indicatore": labels.get(key, key), "valore": value} for key, value in kpi.items()]
        table(sheets["KPI"], ("indicatore", "valore"), records)
        sheets["KPI"].set_column(0, 0, 50)
        sheets["KPI"].set_column(1, 1, 28)
        for index, (key, value) in enumerate(kpi.items(), 1):
            if key.endswith("_eur") and value is not None:
                sheets["KPI"].write_number(index, 1, excel_number(value), formats["eur"])
        expense = spend_rows(result)
        # Separate adjacent table, keeping each worksheet to one useful filter.
        for col, label in enumerate(("scenario", "servizio", "zona", "costo_EUR", "costo_centesimi"), 3):
            string(sheets["KPI"], 0, col, label, formats["header"])
            sheets["KPI"].set_column(col, col, 22)
        for row, record in enumerate(expense, 1):
            for col, (key, value) in enumerate(record.items(), 3):
                cell(sheets["KPI"], row, col, value, key)

        comparison = sheets["Confronto"]
        comparison.set_column(0, 0, 34)
        comparison.set_column(1, 6, 24)
        comparison.set_row(0, 34)
        for col, label in enumerate(("Scenario", "Costo EUR", "Centesimi esatti", "Spedizioni / gruppi", "Ordini confrontabili", "EUR per spedizione / gruppo", "EUR per ordine")):
            string(comparison, 0, col, label, formats["header"])
        detail = comparison_rows(result)
        table(comparison, COMPARISON_COLUMNS, detail, start=15)
        comparison.freeze_panes(16, 1)
        comparison.set_column(0, 0, 34)
        comparison.set_column(1, 2, 24)
        comparison.set_column(3, 4, 24)
        comparison.set_column(5, 6, 29)
        comparison.set_column(10, 10, 82)
        for index, scenario in enumerate(("c0", "c1", "c2"), 1):
            excel_row = index + 1
            string(comparison, index, 0, scenario.upper())
            if kpi["comparable"]:
                formula = f"=SUM({'F' if scenario == 'c0' else 'G'}17:{'F' if scenario == 'c0' else 'G'}{16 + len(detail)})" if scenario != "c2" else f"=SUM('Proposte'!Q2:Q{1 + len(proposals)})"
                comparison.write_formula(index, 1, formula, formats["eur"], excel_number(kpi[scenario + "_eur"]))
                cell(comparison, index, 2, kpi[scenario + "_cents"])
            else:
                string(comparison, index, 1, "Non calcolabile")
                string(comparison, index, 2, "n.d.")
            cell(comparison, index, 3, kpi["groups"] if scenario == "c2" else kpi["comparable"])
            cell(comparison, index, 4, kpi["orders"])
            for col, denominator, suffix in ((5, "D", "per_shipment_eur"), (6, "E", "per_order_eur")):
                comparison.write_formula(index, col, f'=IF({denominator}{excel_row}>0,B{excel_row}/{denominator}{excel_row},"n.d.")',
                                         formats["eur"], excel_number(kpi[scenario + "_" + suffix]))
        formula_rows = ((6, "Cambio servizio C0-C1", '=IF(COUNT(B2:B3)=2,B2-B3,"n.d.")', kpi["service_saving_cents"]),
                        (7, "Consolidamento C1-C2", '=IF(COUNT(B3:B4)=2,B3-B4,"n.d.")', kpi["consolidation_saving_cents"]),
                        (8, "Risparmio totale C0-C2", '=IF(COUNT(B2:B4)=3,B2-B4,"n.d.")', kpi["saving_cents"]),
                        (9, "Somma componenti", '=IF(COUNT(B7:B8)=2,SUM(B7:B8),"n.d.")', kpi["saving_cents"]))
        for row, label, formula, cents in formula_rows:
            string(comparison, row, 0, label, formats["title"])
            comparison.write_formula(row, 1, formula, formats["eur"], excel_number(euros(cents)) if cents is not None else "n.d.")
        string(comparison, 10, 0, "Risparmio / C0", formats["title"])
        comparison.write_formula(10, 1, '=IF(AND(ISNUMBER(B2),B2>0),B9/B2,"n.d.")', formats["pct"], excel_number(kpi["saving_pct"] / Decimal(100)) if kpi["saving_pct"] is not None else "n.d.")
        string(comparison, 12, 0, "Costi solo sulla popolazione confrontabile. C2 conta gruppi, con tutti i colli originali.")
        string(comparison, 13, 0, "Dettaglio C0/C1 sotto; il costo C2 compare una sola volta per gruppo in Proposte.")
        if kpi["comparable"]:
            chart = workbook.add_chart({"type": "column"})
            chart.add_series({"name": "Costo EUR", "categories": "='Confronto'!$A$2:$A$4", "values": "='Confronto'!$B$2:$B$4", "fill": {"color": "#3B7C8A"}, "data_labels": {"value": True, "num_format": '#,##0.00'}})
            chart.set_title({"name": "Costi sulla popolazione confrontabile"})
            chart.set_y_axis({"name": "EUR", "num_format": "#,##0"})
            chart.set_legend({"none": True})
            chart.set_size({"width": 600, "height": 275})
            comparison.insert_chart("I1", chart)

        assumptions = assumption_rows(result)
        table(sheets["Ipotesi"], ("voce", "descrizione"), assumptions)
        sheets["Ipotesi"].set_column(0, 0, 32)
        sheets["Ipotesi"].set_column(1, 1, 112, formats["wrap"])
        for row, record in enumerate(assumptions, 1):
            string(sheets["Ipotesi"], row, 1, record["descrizione"], formats["wrap"])
            sheets["Ipotesi"].set_row(row, 48 if len(record["descrizione"]) > 200 else 34)
        workbook.close()
        return output.getvalue()
    except Exception:
        workbook.close()
        raise
