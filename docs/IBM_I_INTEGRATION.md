# Futuro percorso di integrazione IBM i

Questo progetto non si collega a IBM i/AS400. I CSV del prototipo sono un
contratto applicativo proposto, non un formato universale AS400. Non sono
state verificate credenziali, tabelle, driver, query o compatibilità su un
gestionale aziendale o su Db2 for i. Nessun dato reale è stato utilizzato.

## Un pilota da concordare con IT

1. Individuare responsabile dei dati, significato di spedizione, ordine,
   collo, sede di consegna, partenza e promessa. Stabilire quali campi
   esistono davvero e quali non sono rilevati.
2. Concordare l'export da IBM i Access Client Solutions Data Transfer,
   oppure un accesso ODBC autorizzato. Il connettore Power Query ODBC
   richiede una sorgente/driver configurati correttamente; la scelta del
   driver e del DSN è compito del pilota con IT.
3. Preparare viste dedicate al minimo insieme di campi. Concedere
   permessi **effettivamente di sola lettura** al profilo di servizio,
   anche sul database: una query SELECT o un'interfaccia denominata
   “read-only” non sostituisce i controlli di autorizzazione.
4. Mappare chiavi, codici e livelli di dettaglio. Verificare che la sede
   identifichi univocamente cliente e zona. Separare l'ordine dal costo
   della spedizione e dai suoi colli.
5. Esplicitare conversioni: CCSID/encoding verso UTF-8, zeri iniziali,
   date numeriche o testuali, zona oraria e offset, decimali e unità di
   misura. Non indovinare silenziosamente date ambigue o virgole decimali.
6. Esportare una fotografia coerente dei tre insiemi. Riconciliare numero
   testate, ordini distinti, colli, pesi e importi con i controlli del
   gestionale, incluse rettifiche e duplicazioni. Gestire accessi e
   cancellazione degli estratti con procedure aziendali.
7. Convalidare i listini e le regole con il responsabile logistico.
   L'MVP sintetico non comprende tutti i possibili supplementi o servizi.
   Confrontare un periodo delimitato prima di qualunque uso operativo.

## Esempio SQL illustrativo da adattare

Nomi di tabelle e colonne inventati. Query **non provata** su un gestionale
o su Db2 for i. Scopo: mostrare il livello corretto di aggregazione quando
una testata con un costo ha molti colli.

```sql
WITH package_totals AS (
    SELECT
        shipment_id,
        COUNT(*) AS package_count,
        SUM(actual_weight_kg) AS shipment_actual_weight_kg
    FROM DEMO_PACKAGES
    GROUP BY shipment_id
)
SELECT
    s.shipment_id,
    s.order_id,
    s.destination_id,
    s.header_freight_cost_eur,
    p.package_count,
    p.shipment_actual_weight_kg
FROM DEMO_SHIPMENTS AS s
LEFT JOIN package_totals AS p
    ON p.shipment_id = s.shipment_id;
```

Il risultato ha una riga per testata, a condizione che shipment_id sia
univoco in DEMO_SHIPMENTS. Il LEFT JOIN mantiene visibili le testate senza
colli. Due colli e un costo di testata di 10 EUR non devono diventare
20 EUR sommando un join diretto a dettaglio. Verificare la cardinalità
prima della somma; non usare SUM(DISTINCT costo) come rimedio, perché
spedizioni diverse possono avere lo stesso costo.

Per il motore del prototipo servono comunque i **colli singoli** in
packages.csv: il peso volumetrico si calcola per collo. La query aggregata
illustra un controllo dei totali, non sostituisce quel dettaglio e non
aggiunge header_freight_cost_eur al modello C0, che ricalcola le tariffe.

## Fonti tecniche ufficiali

- [IBM ACS Data Transfer](https://www.ibm.com/docs/en/i/7.6.0?topic=files-copying-data-using-i-access-client-solutions): trasferimento dati fra workstation e IBM i, anche verso CSV.
- [Microsoft Power Query ODBC](https://learn.microsoft.com/en-us/power-query/connectors/odbc): prerequisiti del driver/DSN e importazione.
- [Python zoneinfo](https://docs.python.org/3/library/zoneinfo.html): fusi IANA; il progetto include tzdata per Windows.

Questi riferimenti descrivono strumenti generali. Non costituiscono una
verifica dell'ambiente aziendale o una competenza AS400 dimostrata dal demo.
