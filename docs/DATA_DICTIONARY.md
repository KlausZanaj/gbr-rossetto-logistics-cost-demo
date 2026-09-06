# Contratto dei dati 0.1.0

Tre CSV, UTF-8 con BOM iniziale facoltativo, separatore virgola, punto decimale,
quoting standard (virgolette interne raddoppiate). LF e CRLF accettati.
Le sole righe fisicamente vuote sono ignorate. Nessuna importazione XLSX o
autodetection di esportazioni Excel con punto e virgola/virgola decimale.
Tutte le intestazioni elencate sono richieste, esattamente come scritte.
Colonne extra segnalate e conservate integralmente nei dati di origine esportati.

Gli identificativi restano testo, inclusi zeri iniziali, `N/A` e `null`.
Non sono ammessi ID vuoti, spazi iniziali/finali o caratteri di controllo;
nessuna correzione silenziosa. Decimali: segno facoltativo, cifre ASCII,
punto con almeno una cifra dopo il punto. Vietati esponenti, NaN, Infinity,
spazi e separatori delle migliaia. Tutte le misure sono finite e > 0.

## shipments.csv

| Campo | Significato e vincolo |
|---|---|
| shipment_id | ID primario univoco della spedizione originaria |
| order_id | Un ordine per spedizione; un ordine può avere più spedizioni. Non tariffabile autonomamente |
| customer_id | Cliente sintetico |
| destination_id | Sede precisa; deve identificare lo stesso cliente e zona in tutto il dataset |
| zone | Zona tariffaria testuale |
| ready_at | Istante ISO 8601 con T e offset HH:MM o Z; non successivo a dispatch_at |
| dispatch_at | Partenza fissa, stessa sintassi; normalizzata come istante UTC e valutata in Europe/Rome |
| promised_delivery_date | YYYY-MM-DD, fine giornata locale; non precedente al giorno locale di partenza |
| current_service_id | Servizio del piano originale |
| handling_class | standard, bulky, installation, special; solo standard nel confronto |
| consolidation_allowed | Esattamente true o false |

Gli istanti accettano minuti o secondi, frazioni fino a sei cifre (microsecondi).
Date/ore impossibili o offset invalidi vengono rifiutati, non normalizzati.

## packages.csv

| Campo | Significato e vincolo |
|---|---|
| package_id | ID primario univoco del collo fisico |
| shipment_id | Spedizione esistente, collegamento obbligatorio |
| actual_weight_kg | Peso reale in kg, Decimal > 0 |
| length_cm | Lunghezza in cm, Decimal > 0 |
| width_cm | Larghezza in cm, Decimal > 0 |
| height_cm | Altezza in cm, Decimal > 0 |

Ogni spedizione deve avere almeno un collo. Il consolidamento mantiene gli
stessi package_id, misure e pesi, esattamente una volta.

## tariffs.csv

| Campo | Significato e vincolo |
|---|---|
| tariff_id | ID primario univoco |
| service_id | Servizio sintetico |
| zone | Zona tariffaria |
| valid_from, valid_to | YYYY-MM-DD inclusive, inizio <= fine; nessuna sovrapposizione per servizio+zona, anche al confine |
| currency | Esattamente EUR |
| fixed_fee_eur | Quota per spedizione/gruppo >= 0, massimo 2 decimali |
| per_kg_eur | Quota per kg tassabile >= 0, massimo 4 decimali |
| volumetric_divisor_cm3_per_kg | Divisore volumetrico > 0 |
| billing_increment_kg | Incremento di arrotondamento del singolo collo > 0 |
| fuel_pct | Percentuale da 0 a 100 inclusi, massimo 4 decimali |
| max_package_weight_kg | Massimo peso reale di ogni collo > 0 |
| max_package_longest_side_cm | Massimo lato lungo di ogni collo > 0 |
| max_shipment_actual_weight_kg | Massima somma dei pesi reali > 0 |
| max_packages | Intero >= 1 |
| transit_business_days | Intero >= 0; zero = stesso giorno |
| cutoff_local_time | HH:MM Europe/Rome; confine incluso |

Importi IVA esclusa. Fuel applicato all'intera base sintetica. Nessun listino
reale, scaglione, supplemento, assicurazione, sconto o costo implicito.

## Qualità e conteggi

Blocco totale: file mancante/illeggibile, codifica o quoting invalido,
intestazioni mancanti/vuote/duplicate, numero campi errato, ID primario
mancante/duplicato, collo orfano, tariffa invalida/sovrapposta, sede incoerente.
I record bloccanti conservano file, riga quando disponibile, campo e motivo.

Gli altri errori di valore escludono soltanto la spedizione e i suoi colli.
Una spedizione senza colli è esclusa. Gestione non standard: fuori perimetro.
Baseline non tariffabile o non ammissibile: BASELINE_NOT_COMPARABLE, anche
se un'alternativa sarebbe fattibile. Mai sostituire costi mancanti con zero.
Una sola causa primaria per spedizione, in ordine: INVALID_DATA,
OUT_OF_SCOPE, BASELINE_NOT_COMPARABLE. Conservare anche i motivi aggiuntivi.
Un dataset senza righe con intestazioni corrette è valido; tariffe vuote
sono valide ma non consentono un confronto delle spedizioni esistenti.
