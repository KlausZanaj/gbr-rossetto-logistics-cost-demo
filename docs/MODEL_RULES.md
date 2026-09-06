# Regole del modello 0.1.0

Prototipo indipendente per portfolio. Dati e tariffe sintetici. Nessuna integrazione aziendale verificata.

## Popolazione e calendario

C0, C1 e C2 usano esattamente le stesse spedizioni standard, valide e con
baseline tariffabile e ammissibile. Gli esclusi restano nel report con ID,
motivi e causa primaria. Le conclusioni non rappresentano la spesa totale
aziendale. Nessun costo né risparmio calcolabile se la popolazione è vuota;
dataset vuoto: «Nessuna spedizione». Percentuali senza denominatore: n.d.

ModelConfig è immutabile: Europe/Rome, lunedì-venerdì, insieme esplicito
nonworking_dates (vuoto di default), ROUND_HALF_UP al centesimo.
Il calendario ignora i festivi non inseriti: non è un calendario italiano
completo. Le regole usano gli istanti dei dati, mai la data corrente.

La tariffa è quella della zona valida nel giorno locale di partenza. Merce
pronta, partenza lavorativa entro il cut-off incluso, limiti reali di peso
per collo e per spedizione, lato lungo e numero colli sono obbligatori.
L'arrivo aggiunge giorni lavorativi saltando weekend e date esplicite.
Zero giorni significa stesso giorno. Arrivo <= promessa di ogni membro.
Non si sposta la partenza oltre cut-off, né si modificano le promesse.
La data prevista è una valutazione del modello, non una garanzia del vettore.

## Tariffazione

Per ciascun collo con Decimal:

```
volume = lunghezza * larghezza * altezza
volumetrico = volume / divisore
non_arrotondato = max(peso_reale, volumetrico)
tassabile = ceil(non_arrotondato / incremento) * incremento
```

Si usa ROUND_CEILING sul numero di incrementi. Si sommano i tassabili dei
singoli colli: non si applica max ai totali. Quindi:

```
componente_peso = EUR_per_kg * somma_tassabile
base = quota_fissa + componente_peso
totale = ROUND_HALF_UP(base * (1 + fuel_pct / 100), 0.01)
```

Il fuel non è arrotondato separatamente. Precisione Decimal locale derivata
da cifre e scale degli operandi, con margine per divisioni e prodotti; il
contesto globale resta invariato. Ogni quotazione conserva tariff_id,
traccia per collo, pesi, quota fissa, componente peso, base, fuel, totale
in EUR e centesimi interi. Nessun float nel motore.

## Scenari e determinismo

C0 ricalcola il servizio originale. C1 sceglie il servizio ammissibile più
economico per ogni spedizione. A parità mantiene l'originale ammissibile,
poi ordina service_id e tariff_id. consolidation_allowed=false consente
il cambio servizio ma vieta l'unione in C2.

C2 parte dai singoli C1. Chiave: customer_id, destination_id, zone,
dispatch_at come istante (offset diversi equivalenti). Solo standard
consolidabili e confrontabili. Per ogni coppia della chiave si valuta
l'unione con tutti i colli e la promessa più restrittiva. Si sceglie il
guadagno positivo maggiore, almeno 0.01 EUR. Pareggi: tuple dei membri
ordinati della coppia, poi servizio e tariffa. Per i gruppi uniti il
pareggio di servizio usa service_id/tariff_id, senza servizio originale
privilegiato. Si sostituiscono i due gruppi e si rivalutano le coppie della
chiave. Guadagno nullo: NO_SAVING, nessuna unione. Vincolo violato:
NOT_FEASIBLE con ragioni esplicite. Non si enumerano partizioni globali.
È un'euristica deterministica, senza garanzia di ottimo globale.

proposal_id = prefisso kz-proposal-v1- + SHA-256 completo del JSON canonico
della lista ordinata dei membri preceduta dal dominio/versione.
Il riordino delle righe non cambia gruppi, ID o importi. Ogni spedizione
compare una sola volta in C2, tutti i colli sono conservati, C2 <= C1 <= C0.

## Indicatori

Copertura = confrontabili/importate. Ordini distinti: stessi ordini della
popolazione confrontabile in tutti gli scenari. EUR per spedizione:
C0/n e C1/n; C2/numero gruppi finali, denominatore diverso. EUR per ordine:
costo/numero ordini confrontabili. Spedizioni o gruppi per ordine:
numero unità dello scenario/numero ordini confrontabili.

Risparmio totale = C0-C2; cambio servizio = C0-C1; ulteriore consolidamento
= C1-C2. Le due componenti sommano al totale. Percentuale = (C0-C2)/C0*100
solo se C0>0. Un piano gratuito confrontabile ha costi zero e percentuale
n.d., distinto dall'assenza di popolazione.

Il numero di spedizioni amministrative può diminuire, quello dei colli no.
Peso reale e tassabile sono distinti; il tassabile può cambiare con il
divisore/incremento del servizio. Spesa per servizio e zona in C0 e C2.
Nessun OTIF, puntualità reale, produttività, annualizzazione o saturazione.

## Export e limiti

Proposte ha una riga per gruppo finale, inclusi i singoli invariati. Il
costo C2 non è replicato su ogni spedizione originaria. Origini conservate
come stringhe per preservare ID, date ISO, decimali ed eventuali formule
testuali. Solo formule interne controllate nel foglio Confronto.
Le formule includono risultati cached calcolati dal programma; XlsxWriter
non le ricalcola. Excel usa numeri binari, non Decimal. La conversione
finale numerica è confinata all'export (e al grafico di presentazione UI);
mai riutilizzata dal motore. I centesimi esatti restano disponibili.

Gli input e la configurazione sono firmati per contenuto con SHA-256.
L'XLSX conserva la configurazione effettivamente usata e gli hash dei tre
input. Il contenuto è deterministico; non si richiede ZIP XLSX identico
byte per byte. Gli upload restano in memoria della singola sessione.
