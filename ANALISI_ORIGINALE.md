# DrawER: analisi del sorgente e percorso di rifattorizzazione

## Materiale esaminato e punto di ingresso

Sono stati letti tutti i dodici file forniti in `/home/mattia/Scrivania/DrawER`: `index.html`, `style.css`, `script.js` e i nove moduli in `js/`. I file originali non sono stati modificati.

Il punto di ingresso effettivo è `index.html:57`, che carica **solo `js/main.js`** come modulo. Il file `script.js` contiene una versione monolitica precedente, con alcune funzioni più complete, ma non viene eseguito dalla pagina fornita. Distinguere queste due implementazioni evita di attribuire alla versione attiva funzioni presenti soltanto nel codice inutilizzato.

## Funzioni realmente disponibili

La versione attiva rappresenta entità rettangolari, relazioni a rombo, attributi con indicatore di chiave primaria, gerarchie ISA e collegamenti ortogonali. Consente trascinamento, selezione multipla con Ctrl o rettangolo, aggancio alla griglia da 20 pixel, cancellazione, tema chiaro/scuro, cronologia fino a 50 stati, salvataggio/caricamento JSON `.erdraw` ed esportazione PNG. Le ISA espongono le quattro combinazioni parziale/totale e disgiunta/sovrapposta (`js/modal.js:37`).

Non esiste ancora un modello relazionale: i collegamenti sono oggetti grafici senza cardinalità, ruoli o vincoli; gli attributi hanno nome e flag PK ma nessun tipo SQL, nullabilità o unicità. Non è implementata la generazione SQL.

## Problemi rilevanti

1. **SVG non implementato.** `js/io.js:107–129` produce intestazione, sfondo e stile, senza disegnare oggetti o collegamenti. Il pulsante esporta quindi un'immagine vuota.
2. **Strumento multivalore inattivo.** `js/main.js` imposta la modalità `multivalue`, ma `js/events.js:61–82` non ha un ramo che crei l'oggetto. La classe esiste e gli oggetti importati possono essere visualizzati; la creazione non funziona nella versione attiva.
3. **Regressioni rispetto al monolite.** La versione attiva non registra doppio clic per rinominare, modificare PK o creare testo libero, non gestisce ridimensionamento delle figure e non implementa il trascinamento della vista. Queste funzioni esistono in `script.js:350–504`.
4. **Riferimenti orfani alla cancellazione.** `js/events.js:21–28` elimina gli oggetti selezionati e i relativi link, ma lascia attributi e ISA che puntano a un genitore cancellato. Il monolite eseguiva invece una cascata diretta (`script.js:506`).
5. **Spostamento dei figli incoerente.** Nella versione attiva gli attributi non seguono automaticamente lo spostamento dell'entità; solo le ISA implementano `updatePosition`. Gli attributi nascono inoltre nella posizione interna del clic (`js/classes.js`, costruttore `Attribute`), mentre il monolite li spostava fuori dal perimetro e impediva di trascinarli dentro il genitore.
6. **Ripristino ISA incompleto.** `js/io.js:42–50` ricostruisce una ISA ma non ripristina l'`endPoint` salvato. La posizione terminale viene quindi ricreata con la geometria predefinita.
7. **Caricamento poco difensivo.** Il formato non ha versione, ID stabili, validazione delle proprietà, controllo degli indici o verifica dei riferimenti. Un errore viene spesso scritto solo in console. Il caricamento non avvia una nuova cronologia e può lasciare riferimenti di selezione obsoleti.
8. **Esportazione PNG con limiti geometrici.** Il riquadro di ritaglio considera `x`, `y`, `w`, `h`, ma non le vere estensioni delle etichette degli attributi o dei terminali ISA: alcuni contenuti possono essere tagliati (`js/io.js:91–102`).
9. **Collegamenti privi di semantica.** È possibile collegare arbitrariamente oggetti incompatibili, duplicare archi e creare auto-collegamenti senza ruoli. Il percorso a L/Z non evita ostacoli (`js/pathfinding.js`), nonostante il nome della funzione.
10. **Canvas fisso.** `index.html:35` imposta un'area di 2000×1500; non esistono zoom, adattamento del diagramma alla finestra o navigazione adatta a schemi ampi.

## Formato originale `.erdraw`

Il documento è un JSON senza numero di versione, con due array (`js/io.js:7–24`):

```json
{
  "objects": [
    {"x": 100, "y": 100, "name": "Cliente", "type": "entity", "w": 120, "h": 60},
    {"name": "id", "type": "attribute", "x": 80, "y": 60, "isPK": true, "parentIdx": 0},
    {"type": "isa", "parentIdx": 0, "label": "(p,d)", "stemHeight": 60,
     "x": 160, "y": 160, "endPoint": {"x": 160, "y": 220}}
  ],
  "links": [{"srcIdx": 0, "tgtIdx": 2}]
}
```

Le proprietà possibili sono:

| Tipo | Proprietà specifiche | Semantica |
| --- | --- | --- |
| `entity` | `name`, `x`, `y`, `w`, `h` | Entità |
| `relation` | `name`, `x`, `y`, `w`, `h` | Relazione grafica, nessuna cardinalità |
| `multivalue` | `name`, `x`, `y`, `w`, `h` | Ovale autonomo; il formato non impone un proprietario |
| `text` | `text`, eventualmente `name`, `x`, `y`, `w`, `h` | Nota libera |
| `attribute` | `name`, `isPK`, `parentIdx`, `x`, `y` | Attributo associato per indice a un altro oggetto |
| `isa` | `parentIdx`, `label`, `stemHeight`, `angle`, eventualmente `endPoint`, `x`, `y`, talvolta `w`, `h` | Gerarchia con geometria differente tra le due implementazioni |
| link | `srcIdx`, `tgtIdx` | Indici negli oggetti, senza ID o metadati |

Il monolite serializza le stesse due liste, ma memorizza la geometria ISA tramite `angle` e `stemHeight`; la versione modulare usa soprattutto `endPoint`. L'importatore nuovo deve accettare entrambe le varianti, convertire gli indici in ID stabili, verificare riferimenti e valori numerici, preservare nomi e coordinate e comunicare eventuali informazioni semantiche mancanti. Le cardinalità originali non possono essere recuperate perché non sono mai state salvate. Anche tipi, nullabilità e vincoli richiedono impostazioni esplicite nella nuova applicazione.

## Matrice di parità e obiettivi della nuova architettura

La colonna desktop indica l'obiettivo progettuale della riscrittura; le funzioni effettivamente consegnate e le relative istruzioni sono descritte nel README.

| Funzione | Versione attiva `js/*` | Monolite `script.js` | Obiettivo desktop Python/Qt |
| --- | --- | --- | --- |
| Entità e relazioni Chen | Sì | Sì | Preservare, con modello semantico separato |
| Attributi e PK | Sì, proprietà minime | Sì, anche modifica | Tipi, nullabilità, unicità e chiavi composte |
| Multivalori | Classe e pulsante; creazione assente | Creazione e attributi figli | Creazione e rappresentazione esplicite; conversione SQL solo dove definita |
| ISA | Quattro categorie e terminale mobile | Quattro categorie, rotazione e lunghezza | Preservare categorie e riferimenti; dichiarare limiti di traduzione SQL |
| Note libere | Solo classe/import | Doppio clic sullo sfondo | Strumento dedicato |
| Rinomina e modifica | Assenti negli eventi attivi | Doppio clic | Ispettore e dialoghi coerenti |
| Ridimensionamento | Assente per le figure | Presente | Dimensioni modificabili e testo leggibile |
| Selezione e spostamento multipli | Sì | Sì | Preservare con cascata geometrica corretta |
| Cancellazione dei figli | Assente | Cascata diretta | Cascata su tutti i riferimenti |
| Cronologia | Fino a 50 stati | Assente | Annulla/ripeti per operazioni complete |
| Navigazione | Canvas fisso, nessuno zoom | Pan destro, nessuno zoom | Zoom, pan e adatta alla vista |
| Tema | Chiaro/scuro | Chiaro/scuro | Temi coerenti anche nei dialoghi |
| Salvataggio `.erdraw` | JSON non versionato | JSON non versionato | JSON versionato e scrittura sicura |
| Importazione precedente | Fragile | Fragile | Importazione validata di entrambe le varianti |
| PNG | Presente, ritaglio approssimato | Presente | Area completa, etichette comprese |
| SVG | File vuoto | Pulsante senza implementazione | Esportazione vettoriale reale |
| Cardinalità 1:1, 1:N, N:M | Assenti | Assenti | Limiti min/max espliciti sui ruoli |
| SQL | Assente | Assente | DDL preliminare e avvisi sulle scelte non deducibili |
| Validazione didattica | Assente | Assente | Errori e suggerimenti contestuali |
| Distribuzione eseguibile | Browser | Browser | Pacchetto desktop riproducibile per piattaforma |

## Percorso architetturale consigliato

La riscrittura in **Python con Qt/PySide6** mantiene il modello di interazione grafica ma sostituisce il canvas manuale con una scena di oggetti selezionabili. Il modello dati deve essere indipendente dalla GUI e usare ID stabili: l'interfaccia visualizza lo stato, i servizi eseguono validazione, persistenza e generazione SQL. La cronologia registra operazioni atomiche o istantanee complete e i moduli grafici non diventano la fonte primaria della semantica.

L'approccio consente di verificare conversioni e formato senza avviare una finestra, creare esempi universitari riproducibili e aggiungere in seguito altri esportatori o dialetti. Un semplice involucro desktop intorno alla pagina attuale conserverebbe le regressioni elencate e richiederebbe comunque di sviluppare separatamente semantica ER, cardinalità e conversione SQL.

La migrazione è opportunamente divisa in: inventario e recupero dei comportamenti utili delle due versioni; definizione del formato versionato e importatore; scena Qt e ispettore; vincoli e traduzione relazionale; esportazione; test di dati, DDL e interazione; confezionamento per ciascun sistema operativo. I sorgenti originali restano un riferimento immutato.

## Limiti da dichiarare per l'uso professionale

- Il DDL derivato da un diagramma concettuale è **preliminare**. Scelte su chiavi surrogate, gerarchie, attributi composti/multivalore, relazioni n-arie, totalità e vincoli interrelazionali richiedono una politica esplicita o un controllo umano. I costrutti non tradotti devono produrre avvisi, mai sparire silenziosamente.
- Minimi di partecipazione sul lato inverso di una FK e partecipazione totale di tutti gli oggetti a una relazione non sono generalmente imposti da sole PK/FK/UNIQUE. I vincoli effettivamente generati e quelli soltanto documentati devono essere distinti.
- Un esportatore non equivale a uno strumento di migrazione: non implica connessioni a database, introspezione, alterazioni incrementali, sincronizzazione o gestione dei dati esistenti.
- Compatibilità SQL, nomi riservati, cicli di FK, identificatori, tipi e ordinamento DDL richiedono test per ogni dialetto dichiarato. Il superamento dei test su un motore non certifica gli altri.
- Le gerarchie ISA e le altre estensioni didattiche devono restare visibili anche quando la conversione automatica è limitata; l'importazione legacy non può inventare cardinalità o tipi mancanti.
- La distribuzione multipiattaforma richiede una compilazione e verifica su ciascun sistema target. Un eseguibile Linux non è un eseguibile Windows; firma, notarizzazione, installer e aggiornamenti automatici sono attività separate.
- Prima di redistribuire Qt/PySide6 e il programma confezionato occorre verificare le condizioni delle licenze delle dipendenze e conservare gli avvisi pertinenti. Non è stata ricavata una licenza del codice originale dai soli file forniti.
- L'uso aziendale su schemi estesi richiede ulteriori verifiche di prestazioni e usabilità con dataset reali, oltre ai test funzionali. La riscrittura non implica collaborazione simultanea, gestione utenti, audit o certificazione formale dello schema.
