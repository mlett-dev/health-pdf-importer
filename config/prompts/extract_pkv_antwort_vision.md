Du liest ein PDF als Bildseiten und extrahierst strukturierte Daten aus einer Pkv-Antwort einer privaten Krankenversicherung.

Antworte ausschliesslich als valides JSON nach diesem Schema:

```json
{
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
- `evidence` ist eine kurze wortwoertliche sichtbare Textstelle aus dem Dokument.
- `page` ist die 1-basierte Seitennummer der Evidence.
- `document_type.value` ist immer `pkv_antwort`.
- `patient_first_name` ist der Vorname der **behandelten Person**: das Feld "Patient", wenn im Dokument vorhanden. "Versicherte(r)" / "Versicherungsnehmer(in)" bezeichnet den Beitragszahler - oft ein Elternteil - und ist haeufig ein anderer Mensch als der Patient. Diesen Namen nur dann verwenden, wenn das Dokument keine eigene Patientenangabe enthaelt.
- `doctor_name` ist der Name des Behandlers, falls erwaehnt.
- `erstattungsbetrag_eur` ist der von Pkv erstattete Betrag.
- `bescheids_datum` ist das Datum der Pkv-Antwort/des Bescheids, nicht das Behandlungsdatum.
- `aufwendungsbetrag_eur` ist der urspruengliche Rechnungsbetrag oder eingereichte Aufwendungsbetrag.
- `rechnungsnummer` ist die Rechnungsnummer, falls erwaehnt.
- `betreffender_termin` ist das Leistungsdatum/Behandlungsdatum. Format: `YYYY-MM-DD`.
- Datumswerte haben Format `YYYY-MM-DD`.

Wichtig:

- Trenne urspruenglichen Rechnungsbetrag (`aufwendungsbetrag_eur`) und Erstattungsbetrag (`erstattungsbetrag_eur`).
- Wenn die Antwort eine Ablehnung ist, setze `erstattungsbetrag_eur` auf `null` und fuege eine Warnung hinzu.
- `patient_first_name` und `erstattungsbetrag_eur` sind fuer automatische Verarbeitung erforderlich.
