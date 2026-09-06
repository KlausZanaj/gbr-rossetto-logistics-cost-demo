# Demo di cinque minuti

Messaggio iniziale: «Ho costruito un prototipo indipendente per trasformare
tre export sintetici in un confronto dei costi verificabile. Non usa dati
interni e non è integrato con un gestionale aziendale.»

## 0:00–1:00 · Caricamento e copertura

Avviare dalla cartella del progetto:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Aprire l'indirizzo locale mostrato dal terminale, normalmente
http://127.0.0.1:8501. Usare Sample incluso, demo, calendario vuoto e
premere **Analizza e confronta**. Il demo importa 200 spedizioni e 350 colli.
Confrontabili: 174 (87%), su 99 ordini; 4 escluse per dati, 6 fuori perimetro,
16 con baseline non confrontabile. I 304 colli della popolazione economica
sono mantenuti in C2. Gli altri colli restano nei dati di origine.

Mostrare un motivo di esclusione: «Una dimensione mancante impedisce di
calcolare il peso volumetrico; non la considero una spedizione gratuita.»
Ricordare che il calendario è lunedì-venerdì e ignora i festivi non inseriti.

## 1:00–2:00 · Costi e caso conveniente

Demo, configurazione predefinita:

| Voce | Valore |
|---|---:|
| C0 originale | 2.729,66 EUR |
| C1 scelta servizio | 1.813,09 EUR |
| C2 consolidamento | 1.413,01 EUR |
| Cambio servizio C0-C1 | 916,57 EUR |
| Ulteriore consolidamento C1-C2 | 400,08 EUR |
| Totale C0-C2 | 1.316,65 EUR (48,23%) |
| Spedizioni C0/C1 → gruppi C2 | 174 → 77 |

Il risultato deriva dal sample, senza percentuale obiettivo. Non è una
stima della spesa aziendale, né un risparmio annualizzabile.

Selezionare **CONSOLIDATION_SAVING**: i risultati precedenti scompaiono.
Premere il pulsante. Due colli da 12 e 8 kg, stessa sede e partenza:
C0=20,00, C1=20,00, C2=14,00 EUR. Una quota fissa da 6 EUR viene evitata,
due spedizioni diventano un gruppo, **i due colli rimangono due**.
Aprire la traccia del calcolo e spiegare il massimo fra peso reale e
volumetrico per ciascun collo. VOLUMETRIC_WEIGHT mostra 2 kg reali,
19,2 volumetrici, 20 tassabili e 14,00 EUR.

## 2:00–3:00 · Caso rifiutato e prudenza

Selezionare **DEADLINE_GUARD**, analizzare e aprire le alternative per una
spedizione. LENTO è più economico ma viene scartato come NOT_FEASIBLE:
richiede due giorni, mentre la promessa ne permette uno. Non si cambia
la partenza per rendere il servizio fattibile.

**NO_SAVING**: nella verifica della coppia compare NO_SAVING, nessuna unione
a guadagno zero. **INCOMPATIBLE** dimostra sede diversa, consenso false e
gestione bulky. **SERVICE_CHANGE** separa 10 EUR di cambio servizio e
6 EUR aggiuntivi di consolidamento: totale 16, senza doppio conteggio.

## 3:00–4:00 · Excel verificabile

Tornare al demo e scaricare **kz-logistics-report.xlsx**. Otto fogli:
Spedizioni, Colli, Tariffe, Qualita_dati, KPI, Confronto, Proposte, Ipotesi.
In Confronto i costi sommano il dettaglio e le differenze sono formule.
C2 è presente una volta per gruppo in Proposte. Origini conservate come
testo e centesimi esatti disponibili. Le formule hanno risultati cached
calcolati dal programma; XlsxWriter non esegue un ricalcolo Excel.

Controlli manuali da eseguire in Microsoft Excel prima del colloquio:

1. Aprire l'XLSX senza messaggi di riparazione. Controllare il grafico, le
   otto schede, le intestazioni, i filtri e le righe bloccate.
2. In Confronto verificare B2:B4, B7:B11 e la barra della formula. Dopo un
   ricalcolo completo (Ctrl+Alt+F9), gli importi devono restare quelli sopra.
3. In Spedizioni controllare gli ID testuali; nel golden, shipment_id
   `0001` conserva gli zeri. Nessun input che inizi con `=` deve eseguirsi.
4. In Proposte confrontare la somma C2_EUR e C2_centesimi con Confronto.
   Non sommare C0/C1/C2 come se fossero tre voci dello stesso piano.
5. La modifica di origini nell'XLSX non rilancia l'ottimizzazione. Per un
   nuovo piano correggere i CSV e ricaricarli nell'app.

Ripasso pratico:

- **Filtri:** usare Qualita_dati per causa primaria e Proposte per zona.
- **Pivot manuale:** selezionare Proposte da A1 alla riga finale, Inserisci
  → Tabella pivot; righe zona e servizio_C2, valori somma C2_EUR, somma
  colli, conteggio proposal_id. Non contare i colli come spedizioni.
- **SOMMA.PIÙ.SE:** su una copia di lavoro, `=SOMMA.PIÙ.SE(Proposte!Q2:Q78;Proposte!F2:F78;"NORD")`
  somma C2 del demo per zona. Adeguare l'ultima riga al dataset e non
  includere le righe di intestazione.
- **CERCA.X:** `=CERCA.X(A2;Proposte!A2:A78;Proposte!K2:K78;"Non trovato")`
  cerca il servizio C2 quando A2 contiene un proposal_id. Formula da
  inserire in una scheda di lavoro, non nelle tabelle di origine.

Le formule mostrate qui usano i nomi italiani per Excel italiano. Le
formule memorizzate nell'XLSX usano nomi inglesi e virgole.

## 4:00–5:00 · Futuro pilota

«Il prossimo passo è concordare con IT un estratto di sola lettura,
mappare testate e colli, verificare i totali e validare le regole tariffarie
con la logistica. Ho documentato un possibile percorso ACS/ODBC, senza
presentarlo come un collegamento già realizzato.»

## Stato e verifica del caricamento

Cambiare dataset, modalità, contenuto dei file o calendario deve eliminare
metriche, proposta selezionata e download, fino a un nuovo clic su Analizza.
Per provare il caricamento scegliere Carica tre CSV e selezionare insieme
i tre file di data/sample/CONSOLIDATION_SAVING. Non serve rete.
Provare una selezione incompleta: nessun vecchio risultato deve apparire.
I filtri visivi e la selezione di dettaglio non rieseguono il motore.

## Schermate della demo

Il repository include tre schermate reali dell'app con dati sintetici:

- `docs/screenshots/demo-overview.png`: caricamento, copertura e riepilogo;
- `docs/screenshots/cost-comparison.png`: confronto C0/C1/C2, grafico e proposte;
- `docs/screenshots/proposal-detail.png`: servizio scelto e alternative respinte.

Prima di una presentazione, confrontare sempre i valori visibili con quelli
riportati in questa guida e con il controllo automatico del sample.

## Arresto

Nel terminale che esegue Streamlit premere Ctrl+C. Lo script
`scripts/check_http.py` verifica automaticamente avvio, HTTP e rilascio
della porta, senza sostenere che HTTP 200 provi il flusso utente completo.
