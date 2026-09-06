# KZ Logistics Cost Lab

KZ Logistics Cost Lab trasforma tre export CSV sintetici di distribuzione B2B
in un confronto verificabile dei costi di spedizione. Ricalcola il piano
originale, sceglie servizi ammissibili e propone consolidamenti prudenti senza
modificare partenze, promesse o colli fisici.

> Questa è una demo indipendente preparata da Klaus Zanaj per un colloquio con GBR Rossetto. Non è un prodotto ufficiale dell’azienda, non utilizza dati o tariffe reali e non è collegata ai suoi sistemi informatici.

> Prototipo indipendente per portfolio. Dati e tariffe sintetici. Nessuna integrazione aziendale verificata.

Versione 0.1.0. Interfaccia e guida operativa in italiano. Il demo funziona
localmente senza account esterni e non richiede rete dopo l'installazione.

## Anteprima dell'applicazione

![Panoramica di KZ Logistics Cost Lab](docs/screenshots/demo-overview.png)

La panoramica mostra copertura del confronto, costi C0/C1/C2 e risparmio sul
sample incluso. Sono disponibili anche due viste di dettaglio:

- [Confronto C0/C1/C2 e risparmio](docs/screenshots/cost-comparison.png), con
  indicatori, grafico e proposte operative;
- [Dettaglio di una proposta](docs/screenshots/proposal-detail.png), con la
  selezione spiegabile del servizio e il rifiuto delle alternative che non
  rispettano scadenze o altri vincoli.

Le schermate usano esclusivamente dati e tariffe sintetici.

## Risultato del sample principale

Configurazione predefinita, calendario lunedì-venerdì senza festività aggiunte:

| Indicatore | Risultato |
|---|---:|
| Spedizioni importate | 200 |
| Colli importati | 350 |
| Spedizioni confrontabili | 174 (87,00%) |
| Ordini confrontabili | 99 |
| Escluse: dati / perimetro / baseline | 4 / 6 / 16 |
| C0 · piano originale | 2.729,66 EUR |
| C1 · scelta servizio | 1.813,09 EUR |
| C2 · consolidamento | 1.413,01 EUR |
| Cambio servizio C0-C1 | 916,57 EUR |
| Ulteriore consolidamento C1-C2 | 400,08 EUR |
| Risparmio C0-C2 | 1.316,65 EUR (48,23%) |
| Spedizioni C0/C1 → gruppi C2 | 174 → 77 |
| Colli nella popolazione confrontabile | 304, conservati |

I costi riguardano soltanto la popolazione confrontabile e non rappresentano
la spesa totale di un'azienda. Il sample dimostra il metodo; non è calibrato
su una percentuale obiettivo.

## Golden case

`CONSOLIDATION_SAVING` contiene due spedizioni nella stessa sede e partenza,
con colli da 12 kg e 8 kg. Con quota fissa 6,00 EUR, 0,4000 EUR/kg e nessun
fuel:

```text
C0 = 20,00 EUR
C1 = 20,00 EUR
C2 = 14,00 EUR
Risparmio = 6,00 EUR
2 spedizioni → 1 gruppo; 2 colli → 2 colli
```

Gli altri microcasi coprono scadenza, peso volumetrico, dimensione mancante,
assenza di risparmio, incompatibilità e scomposizione cambio servizio / consolidamento.

## Avvio su Windows

Da PowerShell, dopo essersi spostati nella cartella del progetto:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Il browser apre normalmente `http://127.0.0.1:8501`. Scegliere il sample o
caricare esattamente `shipments.csv`, `packages.csv` e `tariffs.csv`, quindi
premere **Analizza e confronta**. Ogni file può occupare al massimo 10 MiB.
Gli upload restano in memoria della sessione.

## Installazione riproducibile

Python 3.13. Creare una nuova `.venv` nella cartella del progetto; non
riutilizzare ambienti di altri progetti. Con i pacchetti disponibili dalla
propria sorgente configurata:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

`requirements-lock.txt` contiene le versioni effettivamente risolte, senza
URL privati, percorsi locali o riferimenti editable assoluti. La demo non
effettua accessi di rete.

## Verifiche

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe -m compileall -q app.py src tests scripts
.\.venv\Scripts\python.exe -m kz_logistics_cost_lab.sample_data --check
.\.venv\Scripts\python.exe scripts\verify_demo.py
.\.venv\Scripts\python.exe scripts\check_http.py
git diff --check
```

`verify_demo.py` crea un XLSX dimostrativo ignorato da Git in
`outputs/kz-logistics-report.xlsx` e riconcilia i valori cached delle formule
con il motore. `check_http.py` avvia Streamlit su una porta libera, controlla
pagina e health endpoint, arresta il processo e verifica il rilascio della
porta. HTTP 200 dimostra l'avvio del server, non l'intero flusso utente.

Il sample si controlla senza riscritture. La rigenerazione è un comando
esplicito e va usata solo quando si modifica intenzionalmente il generatore:

```powershell
.\.venv\Scripts\python.exe -m kz_logistics_cost_lab.sample_data --generate
```

## C0, C1 e C2

- **C0**: costo del servizio originale ricalcolato con il tariffario sintetico.
- **C1**: servizio ammissibile meno costoso per ogni spedizione; a parità si
  conserva l'originale ammissibile.
- **C2**: consolidamento deterministico a coppie e servizio meno costoso per
  il gruppo finale. È un'euristica, senza garanzia di ottimo globale.

I tre scenari usano la stessa popolazione economica. Una baseline assente o
non ammissibile esclude la spedizione da tutti e tre; non le attribuisce costo
zero. Il motore usa `Decimal`, arrotonda il peso tassabile di ogni collo verso
l'alto all'incremento tariffario e arrotonda il totale monetario una sola
volta al centesimo con `ROUND_HALF_UP`.

## Struttura

```text
app.py                              ingresso Streamlit
src/kz_logistics_cost_lab/
  domain.py                         modelli immutabili e risultati
  io.py, validation.py              contratto CSV e qualità dati
  calendar.py, pricing.py           calendario e tariffazione Decimal
  optimization.py                   C0/C1/C2 e consolidamento
  reporting.py, excel.py            indicatori, tabelle e XLSX in memoria
  state.py, ui.py                    firma input, stato sessione e interfaccia
  sample_data.py                    generatore e controllo sample
data/sample/                         demo da 200 spedizioni e sette microcasi
tests/                               test per comportamento
docs/                                dizionario, regole, IBM i e guida demo
scripts/                             verifiche riproducibili e packaging
```

L'XLSX contiene `Spedizioni`, `Colli`, `Tariffe`, `Qualita_dati`, `KPI`,
`Confronto`, `Proposte` e `Ipotesi`. Gli input restano testo, incluse stringhe
simili a formule. Le sole formule sono create dal programma in `Confronto` e
includono il risultato cached corretto: XlsxWriter non le ricalcola. Per la
verifica manuale e il ripasso di filtri, pivot, `SOMMA.PIÙ.SE` e `CERCA.X`,
vedere [docs/DEMO_GUIDE.md](docs/DEMO_GUIDE.md).

## Limiti

Il modello copre soltanto `handling_class=standard`, EUR IVA esclusa e le
componenti esplicite del tariffario. Il calendario ignora i festivi non
inseriti e la data di arrivo è una previsione del modello, non una garanzia.
Non calcola puntualità reale, OTIF, produttività di magazzino, risparmio
annuale o saturazione camion. I CSV non sono un formato universale AS400;
[docs/IBM_I_INTEGRATION.md](docs/IBM_I_INTEGRATION.md) descrive un futuro
pilota ACS/ODBC da concordare con IT, senza implementazione live.

La suite automatica include AppTest e controlli XML/ZIP sull'XLSX. La pagina
è stata verificata anche in un browser locale e tutti gli otto fogli sono
stati renderizzati e ispezionati. Non è stata eseguita una prova manuale in
Microsoft Excel: i passaggi precisi sono nella guida demo.

## English summary

KZ Logistics Cost Lab is an independent offline portfolio prototype that
turns three synthetic B2B distribution CSV exports into a traceable shipping
cost comparison. It validates data conservatively, recalculates the original
plan (C0), chooses the least-cost feasible service per shipment (C1), and
applies deterministic pairwise consolidation (C2) without changing dispatch
times, delivery promises, or physical packages. It exports a reviewed Excel
workbook with source rows, exclusions, KPIs, proposals, assumptions, input
hashes, controlled formulas, and cached results. No real company data,
carrier tariffs, IBM i integration, or external account is used.

MIT License. Nessun remote o workflow di pubblicazione è configurato dal progetto.
