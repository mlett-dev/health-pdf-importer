# Operations Guide

Last reviewed: 2026-05-28

This guide describes local dry-run usage, the transition to production,
service deployment, and the workflow directory layout.

## Directory Layout

The default configuration uses local subdirectories below a workflow root. The
example below uses `data/`:

```text
data/
  inbox/       # New PDFs added by the watcher or manually
  processing/  # Temporary processing files and OCR artifacts
  done/        # Successfully processed PDFs with final sidecars
  review/      # Ambiguous cases for manual review
  error/       # Failed cases for analysis and retry
  state.sqlite # Idempotency, file IDs, Anytype IDs, and audit events
```

These paths can be changed under `folders:` in `config/app.yaml`. For service
deployments, use a dedicated path such as `/data/health-import/`.

## Local Dry Run

Dry run is the safest mode for testing. It simulates the workflow without
writing to Anytype.

1. **Copy the configuration**

   ```bash
   cp config/app.example.yaml config/app.yaml
   ```

   The example configuration intentionally contains placeholders for Anytype
   identifiers and sets `anytype.dry_run: true`.

2. **Validate the configuration**

   ```bash
   health-importer config-check
   ```

   Placeholder warnings are expected in dry-run mode.

3. **Check runtime dependencies**

   ```bash
   health-importer doctor
   ```

   This checks Ollama reachability, PDF tooling, and write access to the
   configured folders.

4. **Process a fixture PDF**

   ```bash
   health-importer run-once tests/fixtures/pdfs/minimal.pdf
   ```

   The PDF is copied, analyzed, and routed to `done/` or `review/`. A sidecar
   JSON file is written with extraction metadata.

5. **Inspect the result**

   ```bash
   health-importer status
   health-importer show <file-id>
   ```

6. **Run fixture evaluation**

   ```bash
   health-importer goldstandard --pdf-dir tests/fixtures/pdfs \
     --expected-dir tests/fixtures/expected_json
   ```

## Production Use

> **Warning**
> Production commands write to Anytype and may process sensitive health
> documents. Review every item in this checklist before using `--no-dry-run`.

### Checklist

- [ ] `config/app.yaml` exists and is never committed.
- [ ] `anytype.dry_run` is set to `false`.
- [ ] `anytype.space_id` contains a real space ID, not a placeholder.
- [ ] `anytype.collection_id` contains a real collection ID.
- [ ] Required Anytype property IDs are configured.
- [ ] `ANYTYPE_API_KEY` is set in the process environment or `.env`.
- [ ] The Anytype MCP server is running and reachable.
- [ ] `privacy.allow_external_services` is explicitly set to `true` only if
      non-local Ollama URLs or email providers are intentionally used.
- [ ] `email.enabled` is `true` only if IMAP draft creation is intended.
- [ ] `config-check` completes without blocking errors.
- [ ] `doctor` reports required dependencies as available.
- [ ] The first `run-once --no-dry-run` used a non-sensitive test PDF.

### Production Commands

```bash
health-importer run-once /path/to/invoice.pdf --no-dry-run
health-importer scan-inbox --no-dry-run
health-importer watch --no-dry-run
```

## systemd Service

For long-running service deployment, see [`docs/systemd.md`](systemd.md).
Important points:

- Use a dedicated system user, for example `health-pdf-importer`.
- Store configuration under `/etc/health-pdf-importer/app.yaml`.
- Read logs through `journalctl`.
- Use `Restart=on-failure` for automatic restarts.

## Backup and Retention

See [`docs/backup_retention.md`](backup_retention.md) for:

- Which folders and files should be backed up.
- Suggested retention periods.
- Restore steps after data loss.
- Cleanup of temporary OCR and vision artifacts.

## Logs and Sidecars

### Logs

The importer logs to stdout at `INFO` level by default. When run as a service,
systemd captures logs in journald.

```bash
journalctl -u health-pdf-importer.service -f
health-importer run-once example.pdf 2>&1 | tee import.log
```

Allowed log fields include `event`, `file_id`, `sha256`, `status`,
`duration_ms`, `error_code`, and `anytype_object_id`. Logs must not contain
complete PDF text, OCR text, raw prompts, or raw model responses.

### Sidecars

Sidecar JSON files are written next to PDFs in `processing/`, `review/`,
`done/`, or `error/`. Depending on the folder, they contain:

- Technical processing status, hashes, page counts, and text quality.
- Extracted structured fields with confidence scores.
- Final import metadata, such as Anytype object ID and output filename.
- Error codes and shortened error messages.

Full-text sidecars are disabled by default. They require explicit opt-in through
`privacy.store_full_text_debug` and `logging.level = TRACE`.

## Ollama and Local Services

The importer uses locally running Ollama models for extraction and
classification. The example configuration uses:

```yaml
ollama:
  base_url: http://127.0.0.1:11434
  text_model: qwen3.6:35b-a3b-q8_0
  vision_model: qwen3.6:35b-a3b-q8_0
  timeout_seconds: 300
```

In dry-run fixture tests, LLM calls are skipped or replaced with fake clients,
so no model download is required for initial testing.

## Troubleshooting

| Problem | Diagnosis | Fix |
|---|---|---|
| Watcher does not start | Run `doctor` | Check Ollama, folders, and permissions. |
| Files stay in `inbox/` | Try `scan-inbox` manually | Increase `--wait-seconds` or check file locks. |
| `state.sqlite` grows quickly | Review old entries | Back up the DB, then consider SQLite vacuuming. |
| Anytype updates are slow | Check MCP status | Restart Anytype Desktop and verify the base URL. |
| Email draft is not created | Run `email-drafts` | Check `email.enabled` and IMAP settings. |

## Related Documentation

- [`privacy_logging.md`](privacy_logging.md): Privacy rules and logging levels.
- [`systemd.md`](systemd.md): systemd unit, user, and directories.
- [`backup_retention.md`](backup_retention.md): Backup scope and cleanup.
