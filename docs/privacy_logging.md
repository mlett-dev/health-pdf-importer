# Privacy and Logging Rules

Last reviewed: 2026-05-28

These rules apply to import, OCR, LLM, Anytype, and review workflows.

## Principle

PDFs, OCR text, model responses, and extracted invoice data may contain
sensitive health information. The default mode must therefore be local,
data-minimized, and free of full-text output.

The code may log deterministic status, hash, and error metadata. It must not log
complete document contents unless an explicit trace mode is enabled by
configuration.

## Logging Levels

| Level | Purpose | Allowed content | Disallowed content |
|---|---|---|---|
| `INFO` | Normal operation and audit overview | File ID, normalized filename, SHA-256, status changes, target folder, Anytype object ID, error code | Complete PDF or OCR text, raw LLM prompts, raw LLM responses, complete invoice details |
| `DEBUG` | Troubleshooting without health full text | Durations, paths, parser and OCR quality metrics, field names with confidence scores, page count, text length | Complete page contents, complete OCR or PDF text, complete vision descriptions |
| `TRACE` | Manually enabled deep analysis | Short text excerpts, raw model responses, prompt and response dumps, debug sidecars | Must never be enabled automatically or used as the example default |

`TRACE` is not a normal production mode. It must be enabled explicitly and
should be clearly visible in CLI output and logs.

## Standard Log Fields

Standard logs may contain:

- `event`
- `file_id`
- `sha256`
- `original_filename`
- `current_path`
- `status`
- `attempt_count`
- `error_code`
- `anytype_object_id`
- `duration_ms`
- `text_char_count`
- `ocr_used`
- `review_reason`

Standard logs must not contain:

- complete PDF text
- complete OCR text
- complete vision descriptions
- raw LLM prompts or raw LLM responses
- complete extracted JSON payloads with free-text medical content

## Sidecar Files

Sidecar JSON files are allowed in default mode only when data-minimized.

| Folder | Default sidecar allowed | Content |
|---|---:|---|
| `processing/` | yes | Technical processing status, hash, page count, text quality, confidence values, error codes |
| `review/` | yes | Extracted structured fields, confidence values, review reasons, no complete OCR text |
| `done/` | yes | Final import metadata, Anytype object ID, filename, hash, written property keys |
| `error/` | yes | Error code, exception class, shortened error message, retry hints |
| `archive/` | yes | Final metadata only, if local archiving is enabled |

Full-text sidecars are disabled by default. They may be written only when
`privacy.store_full_text_debug` is explicitly `true` and `logging.level` is at
least `TRACE`.

## Local Storage and Archiving

Original PDFs remain in the local workflow until import completes. After a
successful Anytype upload:

- The default target is `done/`.
- An additional durable copy in `archive/` is optional and disabled by default.
- If archiving is enabled, it must be visible in configuration.

Extracted full text is not stored persistently by default:

- `privacy.store_extracted_text = false`
- `privacy.store_full_text_debug = false`
- If full text is stored, the target folder must remain local and must not be
  automatically synced or uploaded externally.

## Access and Backups

Workflow folders should be local and should not live inside automatically synced
cloud folders. Production folders should use restrictive file permissions, for
example readable and writable only by the service user.

Backups are useful for original PDFs and Anytype data, but the importer must not
silently introduce external backup behavior:

- No built-in cloud backup integration.
- No external telemetry.
- No automatic forwarding to external OCR or LLM services.
- Backup behavior is operated and documented outside the importer.

## Safe Defaults

Configuration files should keep these defaults unless a user explicitly opts in:

```yaml
logging:
  level: INFO
  trace_full_text: false

privacy:
  store_extracted_text: false
  store_full_text_debug: false
  write_sidecar_json: true
  allow_external_services: false
```

These defaults are security-relevant. Tests should continue to verify that
full-text logging and external services remain disabled without explicit
configuration.
