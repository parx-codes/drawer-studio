# Verifica di DrawER Studio 1.0.6

Data: 10 novembre 2026. Ambiente: Zorin OS 18.1 (base Ubuntu 24.04), Linux x86_64,
glibc 2.39, Python 3.12.3 e PySide6/Qt 6.12.0.

## Risultati

- **186 test automatici superati**, inclusi dominio, dialoghi, rendering,
  navigazione, note, routing e nuovi flussi interattivi Studio.
- Verificato lo spostamento dei nomi degli attributi attorno al pallino,
  con persistenza e annullamento.
- La griglia cambia l’anteprima del foglio. PNG e SVG sono identici con griglia
  attiva e disattiva.
- Verificati trascinamento delle note, selezione del colore, trasparenza e
  persistenza delle impostazioni nel progetto.
- Verificato il trascinamento sinistro di attributi e multivalori, con aggiornamento
  dell’arco e annullamento dello spostamento.
- Verificati selezione rettangolare con il sinistro, navigazione con il destro,
  spostamento delle figure con Maiusc+sinistro e trascinamento dei tratti.
- Verificati attacchi liberi e cardinalità degli attributi dopo salvataggio,
  riapertura e incolla. Eseguito su SQLite il DDL di un attributo (1,N).
- Salvataggio e riapertura aggiornano il titolo predefinito al nome del file.
  Copia e incolla mantengono i nomi degli elementi.
- Le freccette compaiono al passaggio del cursore e il dialogo chiede soltanto
  le cardinalità applicabili.
- Trascinamento dagli angoli, annulla/ripeti e persistenza delle etichette di
  cardinalità, ruolo e ISA verificati con interazioni Qt.
- PNG verificato in tema scuro per sfondo bianco, opacità e ritaglio, anche
  quando un'etichetta viene spostata oltre il bordo delle figure.
- Verificati primo avvio, salto e riapertura della guida, apertura degli esercizi
  e mantenimento del diagramma corrente mentre si legge una traccia.
- Verificata la stabilità di 500 ricostruzioni della scena su 100 finestre.
- Maniglie di attacco provate su tutti i quattro lati/punte per entrambi gli
  estremi. Salvataggio, riapertura e annulla/ripeti conservano le scelte.
- Pieghe spostabili con estremi fissi e tratti ortogonali; allineamento dei centri
  senza scalini anche per vecchie figure di altezza diversa. Una sequenza di
  1.000 aggiornamenti non accumula vertici nel percorso manuale.
- Le freccette creano collegamenti senza attivare Collega. Esc e perdita di focus
  annullano i gesti incompleti senza alterare il documento.
- Quattro tipologie ISA verificate: sigle corrette, triangolo verso il padre e
  assenza di cardinalità sui rami. Le proprietà del ramo modificano la gerarchia.
- Attributi degli aggregati multivalore verificati sia nell'editor sia eseguendo
  il DDL SQLite, con chiavi locali riferite al proprietario.
- Ctrl+X provato da tastiera, con figli e archi esterni; incolla e annulla
  ripristinano il grafo. Incollare attributi in un altro progetto non crea
  riferimenti strutturali mancanti nella cronologia.
- Controlli e freccette dell'editor non compaiono nei file esportati.
- PNG, SVG e PDF verificati tramite rasterizzazione; testo formattato,
  salvataggi, copia e cronologia continuano a funzionare.
- Nome finestra DrawER Studio e versione in Aiuto → Informazioni verificati.
- La rinomina mantiene accessibile anche la copia di recupero della versione precedente.
- Interfaccia principale, nuovo marchio, ISA e aggregato controllati visivamente.
- Avvio ed esportazioni verificati dai sorgenti e dall'eseguibile Linux autonomo.

## Ripetere le verifiche

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python main.py --smoke-test --output-dir verification
python tools/build.py
"dist/DrawER Studio/DrawER Studio" --smoke-test --output-dir verification-binary
python tools/package_release.py
```

Il progetto `verification-studio/studio.erdraw` mostra una gerarchia totale
sovrapposta e un aggregato con due componenti. Le anteprime sono nella stessa
cartella. Le impronte SHA256 degli archivi sono in `release/`.

## Limiti della verifica

Le prove grafiche automatiche usano Qt offscreen. PostgreSQL è verificato nella
generazione del DDL, senza esecuzione su un server reale. Windows, macOS e altre
distribuzioni Linux richiedono build e prove dedicate.

L'SQL resta preliminare: totalità/disgiunzione ISA, alcuni minimi e l'unicità
semantica delle tuple aggregate richiedono regole applicative o trigger. Il
routing automatico è euristico; quello manuale permette una scelta esplicita dei
percorsi, che può anche richiedere correzioni in diagrammi congestionati.
