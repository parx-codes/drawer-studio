# Novità di DrawER Studio

## 1.0.8

- Il trascinamento sinistro sposta le relazioni insieme ai loro attributi.

## 1.0.7

- Trascinamento diretto delle entità insieme a tutti i loro attributi.
- Guide intelligenti per allineare bordi e centri durante lo spostamento.
- Computer Modern Roman (CMU Serif) incluso come font predefinito del diagramma.

## 1.0.6

- Il nome dell’attributo si trascina attorno al pallino.
- Il pulsante **Griglia** mostra o nasconde le linee di riferimento sul foglio.
- Le note si spostano trascinandole con il sinistro e possono avere uno sfondo
  trasparente o un colore personalizzato.

## 1.0.5

- Attributi semplici e multivalori si spostano trascinandoli con il sinistro.

## 1.0.4

- Il sinistro seleziona un oggetto o un’area. Il destro sposta la vista.
  Maiusc+sinistro sposta le figure.
- Gli attributi si attaccano liberamente sul contorno del proprietario.
  Le cardinalità facoltative appaiono sull’arco e si salvano nel progetto.
- Gli attributi ripetibili delle entità diventano tabelle separate nell’SQL.
- Nuove maniglie sui tratti. Le proprietà del collegamento permettono di
  scegliere i lati di attacco e di ripristinare il percorso automatico.

## 1.0.3

- Il titolo predefinito si aggiorna al nome del file quando salvi un progetto.
- I dialoghi di collegamento mostrano solo le cardinalità che puoi impostare.
  Le freccette appaiono quando passi il cursore su un oggetto.
- Puoi ridimensionare entità, relazioni, multivalori e note trascinando un
  angolo. Cardinalità, ruoli e sigle ISA si spostano trascinando il testo.
- Gli elementi incollati mantengono il nome originale.
- I PNG hanno sfondo bianco e sono ritagliati ai bordi del diagramma.
- Al primo avvio appare una guida didattica che puoi saltare o riaprire da
  **Aiuto**. Lo stesso menu offre tre esercizi con suggerimenti facoltativi.

## 1.0.2 — DrawER Studio

- Il clic sinistro seleziona gli oggetti e permette di spostarli; lo sfondo resta
  trascinabile per navigare. Destro e selezione rettangolare restano disponibili.
- I collegamenti mostrano maniglie per scegliere il centro dei quattro lati
  delle entità o una punta del rombo e per spostare le pieghe in modo ortogonale.
  Attacchi e percorsi vengono salvati, copiati e ripristinati dalla cronologia.
- L'aggancio dei centri e i comandi di allineamento eliminano gli scalini quando
  entità e relazioni sono allineate. Le nuove figure condividono l'altezza standard.
- Le freccette semitrasparenti permettono di creare collegamenti direttamente
  sul foglio. I controlli dell'editor non vengono inclusi nelle esportazioni.
- ISA è rappresentata come collegamento speciale con diramazione ai figli,
  triangolo verso il padre e sigle (t,s), (t,d), (p,s), (p,d). Il tipo si sceglie
  da un elenco nelle proprietà.
- Gli attributi possono appartenere ai multivalori. Gli aggregati semplici sono
  tradotti in tabelle con componenti, FK al proprietario e chiave locale/indice.
- Ctrl+X taglia nodi e collegamenti, mantenendo nomi, figli e riferimenti quando
  vengono incollati nello stesso progetto.
- Il nome dell'applicazione e dell'eseguibile è **DrawER Studio**. Il marchio
  mostra Studio in grigio; versione e informazioni sono nella finestra Informazioni.

## 1.0.1 — navigazione e note

- Navigazione del foglio con trascinamento sinistro. Il tasto destro seleziona
  gli oggetti; trascinandolo si seleziona un'area. Ctrl+destro aggiunge o rimuove
  elementi dalla selezione. Gli oggetti già selezionati si spostano con il sinistro.
- Le note nel diagramma supportano grassetto, corsivo, sottolineato, barrato,
  carattere, dimensione, colore, allineamento ed elenchi. La formattazione si
  conserva nel progetto e nelle esportazioni PNG, SVG e PDF.
- L'esempio universitario si trova in **Aiuto → Esempi**. Il pannello di lavoro e
  i suggerimenti iniziali sono dedicati al progetto corrente.
- Gli attributi importati fuori griglia mantengono la propria distanza relativa
  quando viene spostata l'entità proprietaria.
- Numero di versione visibile nel titolo della finestra e archivi di distribuzione
  con versione nel nome. Gli archivi precedenti restano disponibili.

I progetti precedenti restano leggibili. Per aprire progetti con note formattate
serve DrawER Desktop 1.0.1 o successivo.

## 1.0.0 — prima versione desktop

Editor ER nativo, cardinalità, attributi e chiavi composte, ISA, importazione dei
progetti web, validazione, cronologia, esportazioni grafiche e DDL preliminare
SQLite/PostgreSQL. L'analisi della web app è in `ANALISI_ORIGINALE.md`.
