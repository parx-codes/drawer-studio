-- DDL preliminare generato da DrawER Studio. Rivedere le scelte prima dell'uso in produzione.
-- Cardinalità (min,max) = partecipazione dell'entità alla relazione.
-- I nomi sono preservati e quotati; nessuna connessione al database viene aperta.
-- ISA Specializzazione: supertipo Persona, sottotipi Lavoratore, Studente; totale, sovrapposta. Totalità e disgiunzione non sono imposte dal DDL: aggiungere logica applicativa o trigger.
-- Aggregato multivalore Persona.Recapiti: _indice identifica l'occorrenza per proprietario; valorizzarlo in inserimento. L'unicità dell'intera tupla di valori richiede una regola di dominio aggiuntiva.
-- Aggregato multivalore Recapiti → tabella Persona_Recapiti con attributi componenti e FK al proprietario.
-- SQLite usa affinità dinamiche: lunghezze VARCHAR, precisioni NUMERIC e domini BOOLEAN/data non sono imposti automaticamente.

PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE "Persona" (
    "id_persona" INTEGER NOT NULL,
    PRIMARY KEY ("id_persona")
);

CREATE TABLE "Lavoratore" (
    "id_persona" INTEGER NOT NULL,
    PRIMARY KEY ("id_persona"),
    FOREIGN KEY ("id_persona") REFERENCES "Persona" ("id_persona") DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE "Studente" (
    "id_persona" INTEGER NOT NULL,
    "matricola" INTEGER,
    PRIMARY KEY ("id_persona"),
    FOREIGN KEY ("id_persona") REFERENCES "Persona" ("id_persona") DEFERRABLE INITIALLY DEFERRED
);

CREATE TABLE "Persona_Recapiti" (
    "Persona_id_persona" INTEGER NOT NULL,
    "_indice" INTEGER NOT NULL,
    "tipo" VARCHAR(255),
    "valore" VARCHAR(255),
    PRIMARY KEY ("Persona_id_persona", "_indice"),
    FOREIGN KEY ("Persona_id_persona") REFERENCES "Persona" ("id_persona") DEFERRABLE INITIALLY DEFERRED
);

COMMIT;
