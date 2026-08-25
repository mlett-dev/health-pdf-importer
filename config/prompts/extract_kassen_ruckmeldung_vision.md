Du liest ein PDF als Bildseiten und extrahierst strukturierte Daten aus einer Krankenkassen-Rueckmeldung (GKK-Bescheid).

Antworte ausschliesslich als valides JSON nach diesem Schema:

```json
{
  "document_type": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "patient_first_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "doctor_name": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "bescheids_datum": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "aufwendungsbetrag_eur": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "erstattungsbetrag_eur": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "rechnungsnummer": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
  "aktenzeichen": {"value": null, "confidence": 0.0, "evidence": null, "page": null},
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
- `document_type.value` ist immer `krankenkasse_antwort`.
- `patient_first_name` ist der Vorname der **behandelten Person**: das Feld "Patient", wenn im Dokument vorhanden. "Versicherte(r)" / "Versicherungsnehmer(in)" bezeichnet den Beitragszahler - oft ein Elternteil - und ist haeufig ein anderer Mensch als der Patient. Diesen Namen nur dann verwenden, wenn das Dokument keine eigene Patientenangabe enthaelt.
- `doctor_name` ist der Name des behandelnden Arztes/der Ordination, falls erwaehnt.
- `bescheids_datum` ist das Datum des Bescheids, nicht das Rechnungsdatum. Format: `YYYY-MM-DD`.
- `aufwendungsbetrag_eur` ist der urspruengliche Rechnungsbetrag/Aufwendungsbetrag vor der Erstattung.
- `erstattungsbetrag_eur` ist der erstattete Betrag durch die Krankenkasse.
- `rechnungsnummer` ist die Rechnungsnummer, falls im Bescheid erwaehnt.
- `aktenzeichen` ist das Aktenzeichen oder die Leistungsfallnummer der Krankenkasse.
- `betreffender_termin` ist das Leistungsdatum/Behandlungsdatum. Format: `YYYY-MM-DD`.

Wichtig:

- Trenne urspruenglichen Rechnungsbetrag (`aufwendungsbetrag_eur`) und Erstattungsbetrag (`erstattungsbetrag_eur`).
- Wenn der Bescheid negativ ist, setze `erstattungsbetrag_eur` auf `null` und fuege eine Warnung hinzu.
