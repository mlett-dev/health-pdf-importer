# Health PDF Importer

Local-first importer for private healthcare invoice PDFs, public insurance
responses, and private insurance submission documents into Anytype.

The project is designed for documents that may contain sensitive health data.
By default, processing stays on your machine: PDF text extraction, OCR fallback,
local LLM inference through Ollama, and optional Anytype updates through local
MCP servers.

## Features

- **Healthcare invoices**: Extract patient, provider, date, topic, and amount;
  create or update Anytype objects with PDF attachments.
- **Public insurance responses**: Match responses to existing invoices and
  update reimbursement status and amounts.
- **Private insurance submissions**: Upload documents, track submission state,
  and optionally create IMAP email drafts.
- **Privacy-first defaults**: No external LLM or OCR APIs by default; full-text
  logging is opt-in and disabled.
- **Review workflow**: Low-confidence or ambiguous results are routed to a
  review folder for manual inspection.

## Quickstart (Dry Run)

The fastest way to try the importer is a local dry run against the built-in
fixture PDFs. This does not require Anytype credentials, model downloads, or
personal data.

```bash
# 1. Install dependencies and the package in editable mode
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"

# 2. Use the example configuration (dry_run is true by default)
cp config/app.example.yaml config/app.yaml

# 3. Validate the configuration
health-importer config-check

# 4. Run a single fixture PDF in dry-run mode
health-importer run-once tests/fixtures/pdfs/minimal.pdf

# 5. Inspect the result
health-importer status
```

The example config uses placeholder values for Anytype identifiers. In dry-run
mode the importer warns about placeholders but can still process fixture PDFs,
write sidecars, and route files to `done/` or `review/`.

> **Warning**
> Productive mode writes to your Anytype workspace and may process sensitive
> documents. Read the [operations checklist](docs/operations.md#production-use)
> before using `--no-dry-run`.

## Installation

### Requirements

- Python >= 3.12
- [Ollama](https://ollama.com/) running locally, by default at
  `http://127.0.0.1:11434`
- Optional for productive mode: Anytype Desktop with MCP enabled
- Optional for email drafts: an IMAP account

### Setup

```bash
cd health-pdf-importer
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp config/app.example.yaml config/app.yaml

health-importer doctor
health-importer config-check
```

`doctor` checks runtime dependencies such as Ollama, PDF tooling, and state DB
write access. `config-check` validates the YAML structure and warns about
productive settings.

## CLI Overview

```bash
# Diagnostics
health-importer config-check
health-importer doctor

# Single-file processing
health-importer run-once /path/to/invoice.pdf
health-importer run-once /path/to/invoice.pdf --no-dry-run

# Batch processing
health-importer scan-inbox
health-importer watch

# Review and retry
health-importer review-list
health-importer retry <file-id>
health-importer show <file-id>
health-importer status

# Maintenance
health-importer cleanup --older-than-hours 24

# Evaluation against fixture data
health-importer goldstandard --pdf-dir tests/fixtures/pdfs \
  --expected-dir tests/fixtures/expected_json

# Email drafts, if configured
health-importer email-drafts
health-importer email-send <draft-id>
health-importer email-send-all --yes
```

## Privacy Model

By default the importer operates in a data-minimized mode:

- Extracted full text is not persisted (`privacy.store_extracted_text: false`).
- Full-text debug sidecars are disabled
  (`privacy.store_full_text_debug: false`).
- External services are blocked (`privacy.allow_external_services: false`).
- Sidecars contain structured metadata, confidence scores, and error codes.
- Logs contain file IDs, hashes, status changes, and durations, not complete
  document contents, raw prompts, or raw model responses.

See [`docs/privacy_logging.md`](docs/privacy_logging.md) for the logging matrix
and sidecar rules.

## Anytype Setup

Productive imports create or update objects in an Anytype space. You need:

1. Anytype space, collection, and custom type identifiers.
2. The Anytype MCP server running locally.
3. `ANYTYPE_API_KEY` set in the process environment or `.env`.
4. Matching property IDs configured in `config/app.yaml`.

Use [`config/app.example.yaml`](config/app.example.yaml) as the template.
Never commit your real `config/app.yaml`; it is ignored by `.gitignore`.

## Ollama Models

The example configuration defaults to:

- `text_model`: `qwen3.6:35b-a3b-q8_0`
- `vision_model`: `qwen3.6:35b-a3b-q8_0`

You can change these in `config/app.yaml`. The importer assumes a local Ollama
instance at `http://127.0.0.1:11434`. In dry-run mode, LLM calls are skipped or
mocked for initial fixture testing.

## Tests and CI

```bash
.venv/bin/python -m pytest
.venv/bin/ruff check .
.venv/bin/pyright
.venv/bin/python -m compileall src
```

CI runs `ruff check` and `pytest` on every push.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `config-check` warns about placeholders | Anytype IDs still use `<your-...>` values | Expected in dry-run mode. Replace them before productive use. |
| `doctor` reports Ollama as unreachable | Ollama is not running or uses another URL | Start Ollama or adjust `ollama.base_url`. |
| A PDF lands in `review/` instead of `done/` | Low confidence, missing fields, or ambiguous patient/provider | Inspect the sidecar JSON and run `show <file-id>`. |
| `run-once --no-dry-run` fails on Anytype | MCP is not running, identifiers are wrong, or `ANYTYPE_API_KEY` is missing | Check `doctor` output and Anytype MCP status. |
| Sidecar contains no extracted fields | PDF has no selectable text and OCR fallback is disabled or broken | Check `pdf.min_text_chars` and OCR dependencies. |
| Duplicate file is skipped | The SHA-256 hash already exists in `state.sqlite` | Expected behavior; use `retry <file-id>` to process again. |

## Operations and Service Deployment

For systemd deployment, backups, retention rules, and the dry-run to production
checklist, see [`docs/operations.md`](docs/operations.md).

Systemd unit files live in `deploy/systemd/`. Detailed setup instructions are
in [`docs/systemd.md`](docs/systemd.md).

## License

Licensed under the MIT License.
