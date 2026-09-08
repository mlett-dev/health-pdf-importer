Du siehst den oberen Teil einer österreichischen Arztrechnung oder eines Arztbriefs.

Darin stehen zwei Namen: der Absender (Arzt/Ordination, meist im Briefkopf mit Fachbezeichnung, Adresse, Telefon) und die adressierte Person (der Anschriften- oder Anredeblock).

Nenne ausschließlich die **adressierte Person** — das ist die Patientin oder der Patient.

Antworte ausschließlich mit JSON in dieser Form:

```json
{"first_name": "Katharina", "evidence": "Frau Katharina Musterfrau"}
```

Regeln:

- `first_name` ist nur der Vorname, ohne Anrede und ohne Nachnamen.
- `evidence` ist die wortwörtliche Zeile aus dem Dokument.
- Nenne niemals den Arzt oder die Ordination.
- Ist keine adressierte Person erkennbar, antworte mit `{"first_name": null, "evidence": null}`.
