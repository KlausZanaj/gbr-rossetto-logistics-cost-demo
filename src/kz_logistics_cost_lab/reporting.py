"""Shared tables and indicators for the UI and Excel; no Streamlit imports."""
from collections import Counter, defaultdict
from dataclasses import asdict
from decimal import Decimal, localcontext
import json

from .domain import AnalysisResult, D
from .optimization import config_payload
from .pricing import precision_for


def euros(cents: int) -> Decimal:
    # String construction preserves every digit regardless of ambient context.
    return D(str(cents) + "e-2")


def ratio(numerator, denominator):
    if not denominator or numerator is None:
        return None
    with localcontext() as context:
        context.prec = precision_for(D(numerator), D(denominator))
        return D(numerator) / D(denominator)


def decimal_sum(values):
    values = tuple(values)
    with localcontext() as context:
        context.prec = precision_for(*values)
        return sum(values, D(0))


def json_text(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def summary(result: AnalysisResult) -> dict:
    imported = len(result.data.inputs.table("shipments.csv").rows) if any(t.name == "shipments.csv" for t in result.data.inputs.tables) else 0
    count = len(result.choices)
    orders = len({c.shipment.order_id for c in result.choices})
    c0 = sum(c.baseline.trace.total_cents for c in result.choices) if count else None
    c1 = sum(c.selected.trace.total_cents for c in result.choices) if count else None
    c2 = sum(g.selected.trace.total_cents for g in result.groups) if count else None
    primary = Counter(e.primary_cause for e in result.exclusions)
    result_dict = {"imported": imported, "comparable": count, "coverage_pct": ratio(count * 100, imported), "orders": orders,
                   "excluded_data": primary["INVALID_DATA"], "excluded_scope": primary["OUT_OF_SCOPE"], "excluded_baseline": primary["BASELINE_NOT_COMPARABLE"],
                   "groups": len(result.groups), "packages": sum(len(c.baseline.trace.packages) for c in result.choices),
                   "actual_weight_kg": decimal_sum(c.baseline.trace.total_actual_weight_kg for c in result.choices) if count else None,
                   "c0_cents": c0, "c1_cents": c1, "c2_cents": c2,
                   "service_saving_cents": c0 - c1 if count else None,
                   "consolidation_saving_cents": c1 - c2 if count else None,
                   "saving_cents": c0 - c2 if count else None,
                   "saving_pct": ratio((c0 - c2) * 100, c0) if count else None}
    for scenario, cents, units, traces in (
        ("c0", c0, count, tuple(c.baseline.trace for c in result.choices)),
        ("c1", c1, count, tuple(c.selected.trace for c in result.choices)),
        ("c2", c2, len(result.groups), tuple(g.selected.trace for g in result.groups))):
        result_dict[scenario + "_eur"] = euros(cents) if cents is not None else None
        result_dict[scenario + "_per_shipment_eur"] = ratio(euros(cents), units) if cents is not None else None
        result_dict[scenario + "_per_order_eur"] = ratio(euros(cents), orders) if cents is not None else None
        result_dict[scenario + "_shipments_per_order"] = ratio(units, orders) if count else None
        result_dict[scenario + "_billable_weight_kg"] = decimal_sum(t.total_billable_weight_kg for t in traces) if count else None
    return result_dict


def proposal_rows(result: AnalysisResult) -> list[dict]:
    lookup = {c.shipment.shipment_id: c for c in result.choices}
    rows = []
    for group in result.groups:
        choices = [lookup[sid] for sid in group.members]
        first = choices[0].shipment
        c0 = sum(c.baseline.trace.total_cents for c in choices)
        c1 = sum(c.selected.trace.total_cents for c in choices)
        trace = group.selected.trace
        c2 = trace.total_cents
        reason = "Consolidamento conveniente, vincoli rispettati" if len(group.members) > 1 else ("Cambio servizio conveniente" if c2 < c0 else "Piano invariato")
        rows.append({"proposal_id": group.proposal_id, "shipment_id_membri": json_text(group.members),
                     "order_id_membri": json_text(sorted({c.shipment.order_id for c in choices})), "cliente": first.customer_id,
                     "destinazione": first.destination_id, "zona": first.zone, "partenza": first.dispatch_at.astimezone(result.config.timezone).isoformat(),
                     "colli": len(trace.packages), "peso_reale_kg": trace.total_actual_weight_kg,
                     "peso_tassabile_kg": trace.total_billable_weight_kg, "servizio_C2": group.selected.service_id, "tariff_id_C2": group.selected.tariff_id,
                     "arrivo_previsto": group.selected.expected_delivery_date.isoformat(),
                     "promessa_minima": min(c.shipment.promised_delivery_date for c in choices).isoformat(),
                     "C0_EUR": euros(c0), "C1_EUR": euros(c1), "C2_EUR": euros(c2),
                     "cambio_servizio_EUR": euros(c0 - c1), "consolidamento_EUR": euros(c1 - c2), "risparmio_EUR": euros(c0 - c2),
                     "C0_centesimi": c0, "C1_centesimi": c1, "C2_centesimi": c2,
                     "motivazione": reason, "package_id_membri": json_text([p.package_id for p in trace.packages]),
                     "traccia_C2": json_text(asdict(trace))})
    return rows


PROPOSAL_COLUMNS = ("proposal_id", "shipment_id_membri", "order_id_membri", "cliente", "destinazione", "zona", "partenza", "colli", "peso_reale_kg", "peso_tassabile_kg", "servizio_C2", "tariff_id_C2", "arrivo_previsto", "promessa_minima", "C0_EUR", "C1_EUR", "C2_EUR", "cambio_servizio_EUR", "consolidamento_EUR", "risparmio_EUR", "C0_centesimi", "C1_centesimi", "C2_centesimi", "motivazione", "package_id_membri", "traccia_C2")
COMPARISON_COLUMNS = ("shipment_id", "order_id", "zona", "servizio_C0", "servizio_C1", "C0_EUR", "C1_EUR", "cambio_servizio_EUR", "C0_centesimi", "C1_centesimi", "proposal_id", "arrivo_C0", "arrivo_C1", "traccia_C0", "traccia_C1")


def comparison_rows(result: AnalysisResult) -> list[dict]:
    proposal_by_member = {sid: g.proposal_id for g in result.groups for sid in g.members}
    return [{"shipment_id": c.shipment.shipment_id, "order_id": c.shipment.order_id, "zona": c.shipment.zone,
             "servizio_C0": c.baseline.service_id, "servizio_C1": c.selected.service_id,
             "C0_EUR": c.baseline.cost, "C1_EUR": c.selected.cost,
             "cambio_servizio_EUR": euros(c.baseline.trace.total_cents - c.selected.trace.total_cents),
             "C0_centesimi": c.baseline.trace.total_cents, "C1_centesimi": c.selected.trace.total_cents,
             "proposal_id": proposal_by_member[c.shipment.shipment_id], "arrivo_C0": c.baseline.expected_delivery_date.isoformat(),
             "arrivo_C1": c.selected.expected_delivery_date.isoformat(), "traccia_C0": json_text(asdict(c.baseline.trace)),
             "traccia_C1": json_text(asdict(c.selected.trace))} for c in result.choices]


def spend_rows(result: AnalysisResult) -> list[dict]:
    spend = defaultdict(int)
    lookup = {c.shipment.shipment_id: c.shipment for c in result.choices}
    for choice in result.choices:
        spend["C0", choice.baseline.service_id, choice.shipment.zone] += choice.baseline.trace.total_cents
    for group in result.groups:
        spend["C2", group.selected.service_id, lookup[group.members[0]].zone] += group.selected.trace.total_cents
    return [{"scenario": scenario, "servizio": service, "zona": zone, "costo_EUR": euros(cents), "costo_centesimi": cents}
            for (scenario, service, zone), cents in sorted(spend.items())]


def quality_rows(result: AnalysisResult) -> list[dict]:
    primary = {e.shipment_id: e.primary_cause for e in result.exclusions}
    return [{"livello": i.severity, "codice": i.code, "file": i.file, "riga": i.row,
             "shipment_id": i.shipment_id, "causa_primaria": primary.get(i.shipment_id, ""), "campo": i.field, "motivo": i.message} for i in result.issues]


def assumption_rows(result: AnalysisResult) -> list[dict]:
    pairs = [
        ("Modello", "KZ Logistics Cost Lab 0.1.0"),
        ("Natura", "Prototipo indipendente per portfolio. Dati e tariffe sintetici. Nessuna integrazione aziendale verificata."),
        ("Popolazione", "Solo standard validi con baseline tariffabile e ammissibile. Conclusioni non rappresentative della spesa totale aziendale."),
        ("Calendario", "Lunedì-venerdì, Europe/Rome. Festivi ignorati se non inseriti: non è il calendario italiano completo."),
        ("Date non lavorative", ", ".join(sorted(d.isoformat() for d in result.config.nonworking_dates)) or "Nessuna data aggiuntiva"),
        ("Consegna", "Arrivo previsto dal modello, non garanzia vettore o puntualità consuntiva. Partenze e promesse originali fisse."),
        ("IVA e componenti", "EUR IVA esclusa. Fuel sull'intera base. Nessuno scaglione, supplemento, sconto o assicurazione implicito."),
        ("Arrotondamenti", "Peso: incremento per collo verso l'alto. Totale monetario arrotondato una volta al centesimo con ROUND_HALF_UP."),
        ("Perimetro escluso", "Dati invalidi, bulky, installation, special, baseline non tariffabile/ammissibile. Priorità: dati, perimetro, baseline."),
        ("C0", "Costo originale ricalcolato, stessa popolazione economica di C1 e C2."),
        ("C1", "Servizio ammissibile più economico per ogni spedizione; pareggio favorevole all'originale."),
        ("C2", "Euristica a coppie con massimo guadagno positivo; non garantisce ottimo globale. Colli fisici invariati."),
        ("Risparmio", "Totale C0-C2 = cambio servizio C0-C1 + ulteriore consolidamento C1-C2. Percentuale solo se C0>0."),
        ("Copertura", "Spedizioni confrontabili / spedizioni importate; ogni esclusa contata una volta."),
        ("EUR per spedizione", "C0 e C1: costo / spedizioni confrontabili. C2: costo / gruppi finali; denominatore cambia."),
        ("Ordini", "Ordini distinti confrontabili, medesimo denominatore nei tre scenari. EUR/ordine = costo/ordini; unità/ordine = spedizioni o gruppi/ordini."),
        ("Pesi", "Reale = somma pesi fisici. Tassabile = somma max(reale, volumetrico) arrotondato per collo; dipende dal servizio."),
        ("Assenza dati", "Nessuna popolazione confrontabile: costi e risparmi Non calcolabile. Denominatori nulli: n.d."),
        ("Excel", "Valori numerici finali in aritmetica binaria Excel, non Decimal. Centesimi esatti disponibili. Formule interne con risultati cached dal programma, non ricalcolati da XlsxWriter."),
        ("Origini", "Celle di origine come testo, incluse eventuali formule e URL. Colonne extra conservate, ignorate dal motore."),
        ("Uso del report", "I costi sono risultati del motore. Modificare le origini nell'XLSX non riesegue l'ottimizzazione: reimportare i CSV nell'app."),
        ("Indicatori non disponibili", "OTIF, puntualità reale, produttività, risparmio annuale, saturazione camion."),
        ("Configurazione effettiva", json_text(config_payload(result.config))),
        ("Firma analisi SHA-256", result.signature),
        ("Documentazione formule", "https://xlsxwriter.readthedocs.io/working_with_formulas.html"),
        ("Documentazione fuso", "https://docs.python.org/3/library/zoneinfo.html"),
    ]
    pairs.extend(("SHA-256 " + name, digest) for name, digest in result.data.inputs.hashes)
    return [{"voce": key, "descrizione": value} for key, value in pairs]
