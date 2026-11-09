# Architettura di DrawER Studio

## Scelta tecnica e percorso realizzato

L'applicazione usa **Python 3.11+ e PySide6/Qt**, con QtWidgets per finestre e controlli e QGraphicsScene/QGraphicsView per il diagramma. La dipendenza è PySide6-Essentials==6.12.0; un browser incorporato non è necessario. La separazione fra oggetti, scena e viste segue il modello documentato da [Qt Graphics View](https://doc.qt.io/qt-6/graphicsview.html).

La riscrittura conserva il lavoro sul foglio ER, recupera funzioni disponibili soltanto nel vecchio monolite e completa quelle mancanti nei moduli attivi. Modello e trasformazione SQL sono indipendenti dalla GUI, quindi verificabili senza Qt.

La fase implementata comprende inventario dei sorgenti, modello versionato con importatore, editor e cronologia, persistenza, validazione, esportazione e strumenti di confezionamento. I sorgenti originali sono rimasti riferimenti immutati. Le evidenze e la matrice di parità sono in [ANALISI_ORIGINALE.md](ANALISI_ORIGINALE.md).

## Moduli e responsabilità

| File | Responsabilità |
| --- | --- |
| main.py, drawer/__main__.py | Punti di ingresso |
| drawer/app.py | Argomenti, QApplication, esempio e smoke-test |
| drawer/model.py | Node, Link, Document, formato v2 e importazione legacy |
| drawer/storage.py | Lettura JSON limitata e salvataggio atomico |
| drawer/validation.py | Diagnostica semantica con gravità e riferimento all'elemento |
| drawer/sql.py | Tipi ammessi e trasformazione ER in DDL SQLite/PostgreSQL |
| drawer/history.py | Istantanee JSON per annulla/ripeti |
| drawer/scene.py | Figure, etichette, selezione, spostamento, zoom e navigazione |
| drawer/routing.py | Percorsi ortogonali e porte vincolate |
| drawer/geometry.py | Pieghe manuali e adattamento dei percorsi agli estremi |
| drawer/connections.py | Archi editabili, maniglie e freccia ISA |
| drawer/controls.py | Freccette di creazione e controlli di attacco/piega |
| drawer/window.py | Comandi, coordinamento documento, pannelli e recupero |
| drawer/dialogs.py | Proprietà, relazione guidata, SQL e guida |
| drawer/richtext.py | Editor delle note e rendering QTextDocument condiviso |
| drawer/note_html.py | Formattazione HTML consentita, indipendente da Qt |
| drawer/exports.py | Rendering PNG, SVG e PDF |
| drawer/theme.py | Palette e stile |
| tools/build.py | Build PyInstaller per il sistema corrente |
| examples/universita.erdraw | Esempio modificabile |
| tests/ | Verifiche di dominio e interfaccia |

Il flusso di modifica è **gesto/comando → aggiornamento di Document → commit nella cronologia → aggiornamento di scena e pannelli**. La scena conserva riferimenti agli oggetti del documento e aggiorna le coordinate durante il trascinamento; il commit registra il gesto completo.

## Modello e formato

Document contiene titolo, nodi e collegamenti. Node e Link hanno ID stabili: i riferimenti restano validi indipendentemente dall'ordine degli array.

I nodi rappresentano entità, relazioni, attributi semplici, multivalori, ISA e note. Gli attributi hanno tipo SQL, PK, nullabilità, unicità e stato derivato. Le ISA distinguono totale/parziale e disgiunta/sovrapposta. Coordinate, dimensioni e note fanno parte del documento.

Le note disegnate conservano il testo semplice in `name` per ricerca e compatibilità,
e la formattazione facoltativa in `text_html`. Il campo aggiuntivo è opzionale nel
formato v2: i vecchi progetti si aprono senza conversioni manuali. Il modello resta
indipendente da Qt; la rappresentazione HTML ammessa non include risorse esterne.

Attributi e ISA usano **parent_id** per il proprietario o supertipo. I link usano **source** e **target** per gli estremi, con cardinalità di origine/destinazione e ruolo. La connessione grafica di appartenenza di un attributo deriva dal proprietario e non richiede un link duplicato.

Su un arco entità–relazione conta la cardinalità dal lato entità. Sui link ISA le cardinalità non si applicano. Una relazione ricorsiva usa un rombo e due collegamenti alla stessa entità, con ruoli distinti.

~~~json
{
  "format": "drawer-desktop",
  "schema_version": 2,
  "title": "Nuovo diagramma",
  "nodes": [],
  "links": []
}
~~~

Document.from_dict verifica versione, campi, tipi, numeri finiti, ID, riferimenti e cicli di appartenenza. La lettura rifiuta chiavi duplicate e valori non standard come NaN. I limiti sono 10.000 nodi, 30.000 link e 20 MiB per file.

Uno schema concettuale incompleto può essere salvato: validità strutturale del file e completezza richiesta dall'esportatore SQL sono verifiche distinte.

## Migrazione dei progetti web

Il vecchio formato usa objects e links con indici parentIdx, srcIdx e tgtIdx. L'importatore ricostruisce ID, adatta geometrie e gestisce entrambe le rappresentazioni ISA dei sorgenti.

Cardinalità, tipi, nullabilità e unicità non erano memorizzati: i valori assegnati inizialmente sono segnaposto da revisionare e generano avvisi. La conversione non può ricostruire vincoli mai salvati.

Il vecchio multivalue era un ovale aggregato autonomo. L'importatore conserva questa distinzione: l'oggetto resta orfano e richiede una scelta esplicita del proprietario nelle proprietà. Gli eventuali vecchi link grafici sono preservati e vanno eliminati se ridondanti rispetto alla nuova appartenenza. Attributi figli di aggregati importati restano rappresentati, ma bloccano l'SQL finché non vengono ristrutturati in entità e relazioni esplicite.

## Validazione e trasformazione SQL

Issue contiene gravità, messaggio e ID quando disponibile. La validazione rileva nomi duplicati, PK mancanti, proprietari incompatibili, partecipazioni incomplete, ruoli ricorsivi ambigui e collegamenti non traducibili.

Il generatore ripete la validazione e rifiuta gli errori. Quota i nomi SQL, normalizza i tipi attraverso una lista e una grammatica limitate e segnala le collisioni dei nomi generati. PostgreSQL applica anche il limite di 63 byte agli identificatori. Il servizio restituisce testo senza aprire connessioni.

| Costrutto ER | Trasformazione |
| --- | --- |
| Entità | Tabella degli attributi semplici non derivati |
| Attributi PK | Chiave primaria, anche composta |
| N:M | Tabella associativa con PK delle due FK e attributi della relazione |
| 1:N | FK nella tabella del partecipante con massimo 1 nella coppia Chen |
| 1:1 | FK con UNIQUE; preferenza al partecipante obbligatorio, poi scelta deterministica |
| Ricorsiva | Ruoli distinti per generare nomi delle FK |
| Multivalore semplice | Tabella con chiave del proprietario e valore, PK composta |
| Derivato | Escluso dal DDL, con nota |
| ISA | Table-per-type, PK ereditata e FK al padre |

La convenzione va letta per partecipazione: **Docente (0,N) — Insegna — Corso (1,1)** produce una FK obbligatoria in Corso. Il docente può partecipare a molte occorrenze, il corso esattamente a una.

Per 1:N e 1:1, gli attributi della relazione seguono la FK e ricevono nomi qualificati. Nelle relazioni facoltative, il DDL conserva la coerenza fra assenza della FK e assenza degli attributi. Un CHECK sulle FK composte opzionali impedisce valori parzialmente NULL.

SQLite riceve PRAGMA foreign_keys=ON e FK nelle definizioni. PostgreSQL riceve ALTER TABLE dopo tutte le creazioni, consentendo dipendenze reciproche. Le FK sono differibili e il DDL è racchiuso in una transazione.

La traduzione dei tipi riflette il dialetto: UUID e DATE diventano TEXT in SQLite, BOOLEAN diventa INTEGER. Precisione e controlli specifici sui valori devono essere affinati rispetto al database reale.

### Vincoli documentati e casi rifiutati

NOT NULL impone il minimo sul lato che ospita la FK quando appropriato. I minimi sul lato referenziato e nelle N:M richiedono verifiche globali: il generatore li riporta nelle note senza dichiararli garantiti.

La ISA table-per-type garantisce il riferimento al padre; totalità e disgiunzione richiedono trigger o logica applicativa. Una PK autonoma incompatibile nel figlio provoca un errore. Cicli ed ereditarietà multipla non vengono tradotti automaticamente.

L'SQL è bloccato per relazioni con un numero di partecipazioni diverso da due, aggregati multivalore annidati, multivalori di relazioni e modelli ambigui. Gli attributi semplici degli aggregati multivalore sono supportati: diventano colonne
della tabella dell'aggregato. Se manca una chiave locale si aggiunge un indice di
occorrenza per proprietario. Aggregati annidati e identificatori esterni richiedono
ulteriori estensioni del modello.

Il DDL è preliminare e descrive un nuovo schema. Reverse engineering, migrazioni incrementali, sincronizzazione e amministrazione DB sono funzionalità separate.

## Interazione, cronologia e rendering

Gli oggetti Qt gestiscono hit testing, trascinamento e doppio clic. Gli attributi seguono il proprietario quando non selezionati autonomamente. Copia e cancellazione calcolano la chiusura dei figli; la cancellazione rimuove anche i collegamenti coinvolti.

Dalla 1.0.2, il clic sinistro seleziona; il trascinamento su un oggetto lo sposta,
mentre il trascinamento sullo sfondo naviga. Il destro mantiene selezione singola
e rettangolare. Il pan non modifica il documento. L'esempio rimane sotto Aiuto.
Le porte cardinali sono vincoli persistenti: gli estremi delle entità sono a metà
lato e quelli dei rombi sulle punte. Le pieghe sono polilinee ortogonali persistenti.
Il commit registra la geometria dopo l'aggiornamento della scena, per conservare
nella cronologia anche l'adattamento dei percorsi quando si spostano i nodi.

Le note formattate usano un [QTextDocument](https://doc.qt.io/qtforpython-6/PySide6/QtGui/QTextDocument.html)
sia nella scena sia nell'esportazione; l'editor applica formati a selezioni o al
testo successivo. Il testo viene confinato al riquadro della nota.

La cronologia conserva fino a 150 istantanee e scarta il ramo di ripristino dopo una modifica nuova. I dialoghi lavorano su copie e applicano il risultato solo alla conferma. Aprire o creare un documento inizia una nuova cronologia.

Il routing valuta porte e percorsi ortogonali, penalizzando gli attraversamenti di ostacoli. È un'euristica locale; diagrammi densi possono richiedere correzioni manuali. Il layout automatico usa una griglia semplice.

PNG, SVG e PDF condividono il renderer della scena. Durante l'export selezione e griglia vengono nascoste; il riquadro comprende le etichette. PNG usa scala 2× e limiti di dimensione per contenere la memoria; SVG è vettoriale e PDF usa una pagina delle dimensioni del diagramma.

Il salvataggio scrive un temporaneo nella cartella di destinazione, esegue flush/fsync e sostituisce il file finale solo dopo il completamento. Il recupero automatico periodico usa lo stesso servizio.

## Distribuzione ed estensioni

tools/build.py esegue PyInstaller, include esempio e avvisi e crea un pacchetto onedir, con opzione onefile. Interprete e librerie sono inclusi. La [documentazione PyInstaller](https://pyinstaller.org/en/stable/operating-mode.html) specifica che l'output dipende dal sistema di build: ogni OS target richiede confezionamento e verifica propri, senza cross-compilazione.

Le priorità successive per una distribuzione professionale sono:

1. Test su tutti i sistemi target e su versioni PostgreSQL reali.
2. Prove con studenti, progettisti e schemi ampi, misurando routing e costo della cronologia.
3. Politiche esplicite per indici, vincoli di dominio e costrutti ER avanzati, accompagnate da esempi e test.
4. Installer, firma, eventuale notarizzazione e processo di aggiornamento.
5. Servizi separati per introspezione/migrazioni o collaborazione cloud, se richiesti.

Per aggiungere un dialetto, estendere normalizzazione dei tipi e rendering DDL con test eseguibili, preservando la separazione dalle decisioni concettuali. Un nuovo costrutto ER richiede aggiornamenti coerenti a modello, versione/migrazione del formato, validazione, scena ed esportazione.

La distribuzione deve conservare gli avvisi applicabili alle dipendenze. Le opzioni Community e Commercial sono descritte da [Qt for Python](https://doc.qt.io/qtforpython-6/commercial/index.html). Il packaging non determina da solo gli adempimenti di licenza; non è stata attribuita una licenza ai sorgenti originali in assenza di indicazioni del titolare.

## Proprietà grafiche della versione 1.0.2

Link conserva `source_port`, `target_port` (top/right/bottom/left oppure auto) e
`route_points`, con i vertici della polilinea manuale. Per gli archi di appartenenza,
Node conserva `parent_port`, `child_port` e `connection_points`. I campi sono
opzionali per importare i progetti precedenti. Il modello valida limiti, coordinate
finite e ortogonalità; il renderer usa la stessa geometria per schermo ed export.

La ISA resta un nodo di diramazione nel modello, per mantenere compatibilità e
semantica SQL, ma viene disegnata come un collegamento speciale: giunzione dei figli,
freccia triangolare all'estremo del padre e sigla del vincolo lungo lo stelo. Il
triangolo non è più una figura autonoma con il testo ISA.

I controlli interattivi non fanno parte del documento e non compaiono negli export.
L'identità pubblica è DrawER Studio; il vecchio identificatore di formato e le chiavi
delle preferenze restano compatibili con i file e le impostazioni precedenti.
