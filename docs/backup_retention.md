# Backup and Cleanup Strategy

Last reviewed: 2026-05-28

This document describes what should be backed up, how long local artifacts
should be retained, and how temporary files are cleaned up.

## Backup Scope

The following local data should be included in backups:

- `done/`: successfully processed PDFs kept as a local copy.
- `review/`: ambiguous cases and review artifacts.
- `error/`: failed cases for analysis and retry.
- `state.sqlite`: idempotency, file IDs, Anytype IDs, and audit events.
- `config/app.yaml`: production paths, models, and Anytype target settings.

`processing/` is not a durable archive. It may appear in backups, but it should
not be treated as the source of truth for restore decisions.

## Retention

Suggested minimum retention:

- `done/`: as required by your own recordkeeping policy.
- `review/`: until manual resolution, then move to `done/` or `error/`.
- `error/`: keep long enough for manual analysis and retry.
- `state.sqlite`: as long as local PDFs exist.
- Temporary OCR and vision artifacts: 24 hours.

The local `done/` copy remains available after a successful Anytype upload.
Anytype should not be the only storage location unless you intentionally change
that policy.

## Cleanup

Temporary files include:

- Vision render directories named `*_vision_pages/`.
- OCR intermediate PDFs named `*_ocr.pdf`.
- Incomplete downloads named `*.tmp` or `*.part`.

`cleanup_temporary_artifacts(root, older_than_hours=24)` removes these
artifacts below a workflow root when they are older than the retention
threshold. It does not delete original PDFs from `done/`, `review/`, or
`error/`.

The cleanup command can be run as:

```bash
health-importer --config /etc/health-pdf-importer/app.yaml cleanup --older-than-hours 24
```

A monthly archive structure is not enabled by default. If a local archive grows
large, a `done/YYYY/MM/` storage layout can be introduced later without changing
state DB IDs or hash-based idempotency.

## Restore

1. Stop the service: `systemctl stop health-pdf-importer.service`.
2. Restore workflow folders and `state.sqlite` from the same backup point.
3. Set ownership and permissions for the service user.
4. Run `health-importer doctor`.
5. Run `health-importer status` and `health-importer review-list`.
6. Start the service: `systemctl start health-pdf-importer.service`.

If `state.sqlite` is missing, files may be detected again, but idempotency
metadata and Anytype IDs are unavailable. Start in dry-run mode and review the
results manually.
