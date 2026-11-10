# DrawER Studio

DrawER Studio è un editor desktop in italiano per creare diagrammi Entità–Relazione (ER). È pensato per studenti e docenti di basi di dati e per chi progetta schemi di database prima di passare alla loro implementazione.

Il progetto è stato sviluppato in **vibe coding insieme all’intelligenza artificiale**. Le funzionalità sono nate da richieste in linguaggio naturale e sono state affinate attraverso prove d’uso, correzioni e test automatici.

## Funzionalità

- **Modellazione ER.** Disegna entità, relazioni, attributi, chiavi e aggregati multivalore. Rappresenta relazioni 1:1, 1:N e N:M con cardinalità minime e massime in notazione Chen.
- **Gerarchie ISA.** Rappresenta specializzazioni totali o parziali, disgiunte o sovrapposte.
- **Modifica diretta.** Ridimensiona le figure dagli angoli, sposta cardinalità ed etichette e regola i punti di attacco e le pieghe dei collegamenti.
- **Note formattate.** Aggiungi al diagramma testo con grassetto, corsivo, sottolineato, colori ed elenchi.
- **Salvataggio ed esportazione.** Conserva i progetti modificabili in formato `.erdraw`. Esporta in PNG con sfondo bianco e ritaglio sul contenuto, SVG o PDF. Genera anche SQL preliminare per SQLite e PostgreSQL.
- **Didattica.** Segui la guida contestuale o prova gli esercizi con suggerimenti facoltativi dal menu **Aiuto**, dove trovi anche l’esempio universitario.

## Comandi sul foglio

- **Sinistro** per selezionare un oggetto o trascinare un riquadro. **Destro** per spostare la vista.
- **Sinistro** su un attributo per trascinarlo. **Maiusc+sinistro** per spostare le altre figure. Seleziona un arco per trascinare attacchi, tratti ed etichette.
- Trascina il nome di un attributo attorno al suo pallino. Per spostare il pallino o una nota, trascina direttamente l’elemento.
- Usa **Griglia** nella barra in alto per mostrare le linee di riferimento. Restano fuori dalle esportazioni. Nelle proprietà delle note puoi scegliere uno sfondo trasparente o un colore personalizzato.
- Gli attributi si attaccano lungo tutto il contorno del proprietario. Nelle proprietà puoi attivare la cardinalità e scegliere tra (0,1), (1,1), (0,N) e (1,N).

Trascina un’entità con il sinistro per spostarla insieme a tutti i suoi attributi. Le guide intelligenti agganciano bordi e centri durante lo spostamento e si possono disattivare da **Diagramma → Allineamento intelligente**.

Il font predefinito del diagramma è **Computer Modern Roman** nella variante Unicode **CMU Serif**, inclusa nell’app. Gli SVG fanno riferimento al font, mentre PDF e PNG mantengono l’aspetto su altri sistemi.

## Avvio su Linux

Il pacchetto portabile della versione **1.0.7** per Linux x86_64 è stato verificato su Zorin OS 18.1, basato su Ubuntu 24.04. Estrai tutto l’archivio e avvia **DrawER Studio** dalla cartella estratta, lasciando accanto all’eseguibile la sottocartella `_internal`. Il pacchetto include il runtime.

## Avvio dai sorgenti

Servono **Python 3.11 o successivo** e le dipendenze elencate in `requirements.txt`. Dalla cartella del progetto, esegui su Linux o macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python main.py
```

Su Windows, da PowerShell:

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Puoi aprire direttamente un progetto con `python main.py percorso/progetto.erdraw` o caricare l’esempio universitario con `python main.py --demo`. L’eseguibile distribuito è stato verificato su Linux. Windows e macOS richiedono build e verifiche dedicate.

## Test e build

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -q
python tools/build.py
```

La build usa PyInstaller e genera il pacchetto in `dist/DrawER Studio/`. Su Linux puoi installarlo con `sh tools/install_linux.sh "dist/DrawER Studio" 1.0.7` e aprirlo dal collegamento sulla Scrivania. I sorgenti di ogni rilascio sono pubblicati su `main`.

## Esportazione SQL

L’SQL generato è un punto di partenza per lo schema relazionale. Rivedi tipi, chiavi e vincoli prima di usarlo su un database reale. Alcune regole, come la totalità e la disgiunzione nelle gerarchie ISA, possono richiedere trigger o controlli applicativi.

## Segnalazioni e contributi

Per segnalare un problema, apri una **Issue** e indica versione, sistema operativo, passaggi per riprodurlo e risultato atteso. Se serve un file di esempio, allega un diagramma privo di dati riservati. Le proposte e le pull request sono benvenute.

## Licenza

DrawER Studio è distribuito con licenza [MIT](LICENSE).
