# DrawER Studio — roadmap proposta per la v1.1

Obiettivo: rendere più rapido il lavoro sul diagramma e più comprensibile il
passaggio dal modello concettuale allo schema relazionale. DrawER resta un editor
ER locale, utile sia nelle esercitazioni sia nella progettazione professionale.

Questa è una proposta di sviluppo: le funzioni elencate non sono ancora
implementate. **P0** indica il nucleo prioritario, **P1** gli ampliamenti
consigliati, **P2** una funzione rinviabile se aumenta troppo la dimensione del
rilascio. L'impegno **S/M/L** è relativo: piccolo, medio, grande; non è una stima
di calendario.

## Base di partenza: v1.0.3

Le tre richieste emerse dal testing appartengono alla v1.0.1 e precedono questa
roadmap:

1. Navigazione con trascinamento sinistro e selezione con il destro, conservando
   lo spostamento degli oggetti selezionati.
2. Note nel diagramma con testo formattato e formattazione conservata nei file
   e nelle esportazioni.
3. Esempio universitario accessibile da **Aiuto → Esempi**, fuori dal pannello di
   lavoro abituale.

La v1.0 contiene già cardinalità, chiavi composte, multivalori, ISA, cronologia,
ricerca, recupero automatico, layout semplice ed esportazioni JSON, PNG, SVG,
PDF e SQL SQLite/PostgreSQL. La v1.1 estende queste capacità.

La v1.0.2 ha inoltre introdotto selezione sinistra, attacchi e pieghe manuali,
freccette di collegamento, ISA a freccia, aggregati multivalore e Ctrl+X.
La v1.0.3 ha introdotto ridimensionamento dagli angoli, etichette spostabili,
guida didattica contestuale ed esercizi in Aiuto.
Il dettaglio è in [CHANGELOG.md](CHANGELOG.md).

## Le sette implementazioni consigliate

| # | Priorità / impegno | Implementazione e beneficio | Criterio di accettazione |
| --- | --- | --- | --- |
| 1 | **P0 · M** | **Guide di allineamento sul foglio.** Mostrare riferimenti temporanei per allineare gli elementi vicini durante lo spostamento o il ridimensionamento. | Le guide appaiono quando si avvicinano bordi o centri e scompaiono al termine del gesto. La geometria risultante si conserva nel progetto e nelle esportazioni. |
| 2 | **P0 · L** | **Distribuzione dei collegamenti paralleli.** Aggiungere strumenti per separare i percorsi sovrapposti e ridurre gli incroci nei diagrammi fitti. | I percorsi restano ortogonali. Le regolazioni di attacchi, pieghe ed etichette si conservano con annulla/ripeti, riapertura ed esportazione. |
| 3 | **P0 · M** | **Gestione più solida dei progetti.** Elenco file recenti, copie di recupero distinte per documento e protezione dalle sovrascritture quando il file cambia fuori dall'app. Evita confusione lavorando su più schemi o istanze. | Due progetti aperti in istanze diverse non condividono la copia di recupero. Il ripristino identifica il documento corretto. Una modifica esterna viene rilevata prima della sovrascrittura. |
| 4 | **P1 · L** | **Anteprima dello schema relazionale derivato.** Vista di tabelle, PK, FK e tabelle ponte accanto al diagramma; scelta esplicita del lato della FK nelle 1:1 quando entrambe le traduzioni sono valide. Rende verificabili le scelte prima dell'SQL. | Selezionare una tabella evidenzia l'elemento ER che l'ha generata. La scelta 1:1 viene salvata; anteprima e SQL usano la stessa trasformazione. La vista derivata non modifica automaticamente il diagramma concettuale. |
| 5 | **P1 · M** | **Validazione SQL più precisa per dialetto.** Regole visibili su tipi, identificatori e vincoli non imposti; verifica automatica anche su un PostgreSQL reale di test. Aumenta l'affidabilità dello schema preliminare. | Gli schemi campione vengono creati ed esercitati su SQLite e PostgreSQL. Tipi non supportati e nomi invalidi vengono segnalati sull'elemento interessato. Ogni vincolo non generato compare nel rapporto di esportazione. |
| 6 | **P1 · M** | **Approfondimenti e riscontro didattico.** Spiegare le cardinalità a partire dai collegamenti selezionati, separare i suggerimenti dagli errori SQL e aggiungere un riscontro sugli esercizi. | Selezionare una partecipazione mostra come leggerne la cardinalità. Il riscontro facoltativo confronta lo schema con gli obiettivi dell'esercizio. |
| 7 | **P2 · M** | **Minimappa per schemi estesi.** Vista compatta facoltativa, con riquadro dell'area visibile e clic per raggiungere una zona lontana. Completa ricerca e zoom già presenti. | Pan, zoom e spostamenti aggiornano il riquadro senza modificare il documento. La minimappa può essere nascosta e non compare nelle esportazioni. Un diagramma campione di 100 entità rimane navigabile. |

## Ordine di realizzazione

### Milestone 1 — Editor e tutela del lavoro

Realizzare **1 e 3**, consolidando prima le interazioni della v1.0.1. Introdurre
le nuove proprietà persistenti con migrazione e test dei file esistenti. Uscita:
progetti vecchi e nuovi si riaprono senza perdita di contenuto, compresi testi
formattati, e recuperi di documenti diversi restano separati.

### Milestone 2 — Controllo dei collegamenti

Realizzare **2** e misurare diagrammi piccoli e densi prima/dopo il cambiamento.
Uscita: percorso automatico, correzione manuale, movimento dei nodi e cronologia
convivono; i collegamenti esportati corrispondono a quelli visualizzati.

### Milestone 3 — Dal concettuale al relazionale

Realizzare **4 e 5** usando un'unica rappresentazione intermedia per anteprima
e SQL. Uscita: casi 1:1, 1:N, N:M, riflessivi, chiavi composte e ISA verificati
su entrambi i database; ogni scelta o limite è riconoscibile prima dell'export.

### Milestone 4 — Didattica e rilascio

Realizzare **6**; aggiungere **7** se resta compatibile con la dimensione del
rilascio. Provare i flussi con studenti e progettisti e correggere i punti
ambigui. Verificare navigazione da tastiera, focus, contrasto e ridimensionamento
su schermi ad alta densità. Confezionare e testare l'app sui sistemi dichiarati
supportati; pubblicare una matrice di compatibilità anziché presumere che una
build Linux valga anche per Windows o macOS.

## Cosa tenere oltre la v1.1

- **Costrutti ER avanzati:** attributi composti, entità deboli, identificatori
  esterni, relazioni ternarie e ulteriori strategie ISA. Richiedono decisioni
  coerenti su notazione, modello, validazione e traduzione.
- **Progettazione fisica più ampia:** indici configurabili, vincoli di dominio e
  UNIQUE composti, dialetto MySQL/MariaDB e politiche dei nomi. Conviene fondarli
  sulla rappresentazione relazionale introdotta nella v1.1.
- **Reverse engineering e migrazioni:** importazione di DDL o metadati e
  confronto tra versioni di uno schema, come funzioni di progettazione separate.
- **Collaborazione e distribuzione:** confronto tra revisioni, condivisione,
  aggiornamenti automatici e installer firmati, dopo aver definito piattaforme
  e modalità di distribuzione effettivamente richieste.

Il taglio consigliato per la v1.1 comprende **1–6**. La minimappa è il primo
elemento rinviabile; i costrutti ER avanzati meritano un rilascio dedicato.
