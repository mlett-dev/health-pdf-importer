Du prüfst eine bereits extrahierte Wahlarzt-Rechnung anhand der gerenderten PDF-Seiten als Bilder.

Du bekommst die gerenderten Seiten und ein JSON mit extrahierten Feldern.
Ändere keine Felder. Entscheide nur, ob die Extraktion plausibel ist.

Antworte ausschließlich als JSON:

```json
{
  "status": "valid",
  "issues": [],
  "confidence": 0.0
}
```

Erlaubte Statuswerte:

- `valid`: Evidence passt, keine offensichtlichen Widersprüche.
- `needs_review`: Unsicherheit, fehlende Evidence oder mehrere mögliche Werte.
- `invalid`: Offensichtlich falscher Betrag, falsches Datum oder Evidence nicht im Bild sichtbar.

Prüfe:

- Sind Evidence-Stellen wirklich in den Bildern sichtbar? (Nicht im OCR-Text, sondern visuell im Bild.)
- Ist der Betrag plausibel und als Gesamt-/Endbetrag markiert?
- Gibt es widersprüchliche Beträge?
- Ist der Termin wirklich ein Behandlungstermin?
- Sind fehlende Werte korrekt als `null` markiert?
