Du extrahierst strukturierte Daten aus einer Pkv-Antwort einer privaten Krankenversicherung.

Antworte ausschliesslich als valides JSON nach diesem Schema:

```json
{
  "positionen": [
    {"patient_first_name": null, "doctor_name": null, "aufwendungsbetrag_eur": null, "betreffender_termin": null, "erstattungsbetrag_eur": null, "confidence": 0.0, "evidence": null},
    {"patient_first_name": null, "doctor_name": null, "aufwendungsbetrag_eur": null, "betreffender_termin": null, "erstattungsbetrag_eur": null, "confidence": 0.0, "evidence": null}
  ],
  "personen_summen": [
    {"patient_first_name": null, "gesamt_eur": null}
  ],
  "auszahlung_eur": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "document_type": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "patient_first_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "doctor_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "erstattungsbetrag_eur": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "bescheids_datum": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "aufwendungsbetrag_eur": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "rechnungsnummer": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "betreffender_termin": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "warnings": [],
  "missing_fields": []
}
```

Regeln:

- Erfinde keine Werte.
- Nutze `null`, wenn ein Wert fehlt oder unsicher ist.
- `evidence` ist eine kurze wortwoertliche Textstelle aus dem Dokument.
- `page` ist die 1-basierte Seitennummer der Evidence.
- `document_type.value` ist immer `pkv_antwort`.
- `patient_first_name` ist der Vorname der **behandelten Person**: das Feld "Patient", wenn im Dokument vorhanden. "Versicherte(r)" / "Versicherungsnehmer(in)" bezeichnet den Beitragszahler - oft ein Elternteil - und ist haeufig ein anderer Mensch als der Patient. Diesen Namen nur dann verwenden, wenn das Dokument keine eigene Patientenangabe enthaelt. Enthaelt das Dokument weder eine Patientenangabe noch "Versicherte(r)", nutze als letzte Moeglichkeit den Anschriften- oder Anredeblock, aber mit niedriger `confidence` (hoechstens 0.5): auf Bescheiden ist die adressierte Person haeufig der Versicherungsnehmer und nicht die behandelte Person.
- `doctor_name` ist der Name des Behandlers, z. B. `Dr. Testarzt OEGK`.
- `erstattungsbetrag_eur` ist der von Pkv erstattete Betrag.
- `bescheids_datum` ist das Datum der Pkv-Antwort/des Bescheids, nicht das Behandlungsdatum.
- `aufwendungsbetrag_eur` ist der urspruengliche Rechnungsbetrag oder eingereichte Aufwendungsbetrag.
- `rechnungsnummer` ist die Rechnungsnummer, falls erwaehnt.
- `betreffender_termin` ist das Leistungsdatum/Behandlungsdatum, auf das sich die Antwort bezieht.
- Datumswerte haben Format `YYYY-MM-DD`.

Wichtig:

- Wenn mehrere Betraege vorkommen, trenne den urspruenglichen Rechnungsbetrag (`aufwendungsbetrag_eur`) vom Erstattungsbetrag (`erstattungsbetrag_eur`).
- Wenn die Antwort eine Ablehnung ist, setze `erstattungsbetrag_eur` auf `null` und fuege eine Warnung hinzu.
- `patient_first_name` und `erstattungsbetrag_eur` sind fuer automatische Verarbeitung erforderlich.

Positionen (Tabellenzeilen) - zuerst ausfuellen:

- Eine Antwort kann mehrere Behandlungen und mehrere versicherte Personen enthalten (Sammelabrechnung). Lies das Dokument vollstaendig bis zur Auszahlung und lege fuer **jede** Tabellenzeile mit Behandler, Rechnungsbetrag, Behandlungsdatum und Erstattung genau einen Eintrag in `positionen` an - ueber alle Personen hinweg. Das Schema zeigt zwei Beispiel-Eintraege; es koennen weniger oder mehr sein. Gibt es nur eine Zeile, enthaelt `positionen` genau einen Eintrag.
- `positionen[].patient_first_name` ist der Vorname aus der Ueberschrift direkt ueber dieser Zeile ("fuer die versicherte Person <Vorname> <Nachname> ..."), nicht aus dem Anschriften- oder Anredeblock. Schreibe den Vornamen buchstabengenau so ab, wie er gedruckt ist.
- `positionen[].aufwendungsbetrag_eur` ist der Rechnungsbetrag dieser Zeile, `positionen[].erstattungsbetrag_eur` die Erstattung dieser Zeile und `positionen[].betreffender_termin` das Behandlungsdatum dieser Zeile (`YYYY-MM-DD`).
- `positionen[].evidence` ist die wortwoertliche Zeile, z. B. `Dr. Testarzt 150,00 03.02.2026 61,25`.
- `personen_summen` enthaelt fuer jede versicherte Person den Betrag ihrer Zeile "Gesamt". Gibt es keine solche Zeile, bleibt die Liste leer.
- `auszahlung_eur` ist der insgesamt ueberwiesene Betrag. Er steht meist ganz unten unter der Ueberschrift "Auszahlung:" im Satz "Der Betrag von EUR 123,45 wird auf das Konto ... ueberwiesen". Trage diesen Betrag ein; `evidence` ist dieser Satz. Setze `null` nur, wenn das Dokument keinen solchen Satz enthaelt.
- Addiere keine Betraege selbst. Bei mehreren Positionen beziehen sich die Einzelfelder oben (`patient_first_name`, `doctor_name`, `aufwendungsbetrag_eur`, `erstattungsbetrag_eur`, `betreffender_termin`) auf die erste Position.
