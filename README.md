# Health PDF Importer

Local-first importer for private healthcare invoice PDFs, public insurance
responses, and private insurance submission documents into Anytype.

The project is designed for documents that may contain sensitive health data.
By default, processing stays on your machine: PDF text extraction, OCR fallback,
local LLM inference through llama.cpp, and optional Anytype updates through local
MCP servers.

## Features

- **Healthcare invoices**: Extract patient, provider, date, topic, and amount;
  create or update Anytype objects with PDF attachments.
- **Public insurance responses**: Match responses to existing invoices and
  update reimbursement status and amounts.
- **Private insurance submissions**: Upload documents, track submission state,
  and optionally create IMAP email drafts.
- **Combined private insurance statements**: A statement settling several
  treatments is attached to every matching invoice, each with its own
  reimbursement, but only when the rows add up to the printed totals and every
  row matches exactly one invoice; otherwise the whole statement goes to review.
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

## Results so far (personal workflow)

| What | Detail |
|---|---|
| Development set | 20 real healthcare documents (invoices, public-insurance responses, private-insurance submissions) |
| How it was built | Iterated against this set, fixing prompts, the Pydantic schema, and confidence thresholds as failure modes came up |
| Current state | Handles the recurring document types in day-to-day personal use. Unfamiliar or low-confidence cases go to manual review |
| Hands-on effort | Reduced from about 30 min to about 1 min per document |
| Unattended pipeline time | About 3 min per document end to end |
| Local model | `qwen3.8:27b` on llama.cpp (Vulkan), text and vision; until November 2026 `qwen3.6:35b-a3b-q8_0` via Ollama |
| Privacy default | No external LLM or OCR APIs by default. Everything runs locally |

## Installation

### Requirements

- Python >= 3.12
- A local [llama.cpp](https://github.com/ggml-org/llama.cpp) server with an
  OpenAI-compatible API (see [Local LLM](#local-llm-llamacpp))
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

`doctor` checks runtime dependencies such as the LLM server, PDF tooling, and state DB
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

## Local LLM (llama.cpp)

The importer talks to a local [llama.cpp](https://github.com/ggml-org/llama.cpp)
server (`llama-server`, optionally behind
[llama-swap](https://github.com/mostlygeek/llama-swap) to serve several models)
through its OpenAI-compatible `/v1/chat/completions` API. Thinking is switched
off per request with `chat_template_kwargs.enable_thinking`, a llama.cpp
extension, so Ollama's OpenAI-compatible endpoint is not a drop-in replacement.
The settings keep the historical section name `ollama:`:

- `base_url`: the server, e.g. `http://127.0.0.1:8080` (llama-server's default)
- `text_model`, `vision_model`: the model IDs the server lists under
  `/v1/models`; the vision model needs its multimodal projector (`--mmproj`)

`doctor` checks that both models are served. In dry-run mode, LLM calls are
skipped or mocked for initial fixture testing.

**AMD GPUs (ROCm/HIP) and hybrid Qwen models.** The HIP backend can carry the
state of hybrid Gated-DeltaNet models (qwen3.5/3.6/3.8) from one request into
the next, so an answer may quote an earlier, unrelated prompt
([ollama#18528](https://github.com/ollama/ollama/issues/18528),
[llama.cpp#29092](https://github.com/ggml-org/llama.cpp/issues/29092)). On such
hardware, use a llama.cpp build with the Vulkan backend and give the importer
its own server instance. The importer refuses answers that contain tool-call
markup (it never sends tools) and reports them as
`OllamaContaminatedResponseError`. To check a backend, run the upstream probe
`rc3/leak_probe2.py` from
[gdn-hip-leak-repro](https://github.com/jgoellermaximus/gdn-hip-leak-repro)
against a HIP build (should report a leak, the positive control) and against
the Vulkan build you use (should not).

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
| `doctor` reports the LLM server as unreachable or a model as not served | llama-server is not running, uses another URL, or lists the model under another ID | Start the server, adjust `ollama.base_url`, or set the model ID shown under `/v1/models`. |
| A PDF lands in `review/` instead of `done/` | Low confidence, missing fields, or ambiguous patient/provider | Inspect the sidecar JSON and run `show <file-id>`. |
| `run-once --no-dry-run` fails on Anytype | MCP is not running, identifiers are wrong, or `ANYTYPE_API_KEY` is missing | Check `doctor` output and Anytype MCP status. |
| Sidecar contains no extracted fields | PDF has no selectable text and OCR fallback is disabled or broken | Check `pdf.min_text_chars` and OCR dependencies. |
| Every document lands in `review/` with "0 candidates" | Property keys were renamed in Anytype; the sidecar shows `ANYTYPE_PROPERTY_KEYS_MISSING` | Compare the keys with Anytype's property list and update `config/app.yaml`. |
| Duplicate file is skipped | The SHA-256 hash already exists in `state.sqlite` | Expected behavior; use `retry <file-id>` to process again. |

## Operations and Service Deployment

For systemd deployment, backups, retention rules, and the dry-run to production
checklist, see [`docs/operations.md`](docs/operations.md).

Systemd unit files live in `deploy/systemd/`. Detailed setup instructions are
in [`docs/systemd.md`](docs/systemd.md).

## License

Licensed under the MIT License.
