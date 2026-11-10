# Database backup and restore

Two scripts, `backend/scripts/backup_db.sh` and `backend/scripts/restore_db.sh`,
wrap `pg_dump`/`pg_restore` directly — no additional backup infrastructure
(no Redis, no managed backup service) is introduced for this.

## Backup

```
./scripts/backup_db.sh [database_name] [output_dir]
# defaults: database_name=onholland_accounting, output_dir=./backups
```

Produces a timestamped, compressed, custom-format `pg_dump` file. Verify
any dump's integrity without touching a database at all:

```
pg_restore --list <dump_file>
```

## Restore

```
./scripts/restore_db.sh <dump_file> [database_name] [--force]
# default database_name: onholland_accounting_restore (NOT the live dev/prod name)
```

**Safety design:** the script refuses to restore into a database that
already has tables, unless `--force` is explicitly passed. Restoring a
backup is a destructive overwrite of whatever is already in the target
database — the default target name is deliberately a different database
from the live one, and the script will not silently overwrite an
existing database even if you point it at one by name.

**Never run `restore_db.sh --force` against the live development or
production database name.** Restore testing and disaster-recovery drills
must always target a disposable database created for that purpose, then
dropped afterward.

## Verified procedure (tested 2026-11-03)

This was actually run end-to-end against this project's dev database,
restoring into a disposable database that was dropped immediately after
verification — never against `onholland_accounting` destructively:

1. `./scripts/backup_db.sh onholland_accounting <scratch_dir>` — produced
   a valid dump (`pg_restore --list` confirmed 458 TOC entries).
2. `./scripts/restore_db.sh <dump_file> onholland_accounting_restore_test`
   — restored into a brand-new, previously nonexistent database.
3. Compared row counts between the source and restored database across
   `companies`, `employees`, `payslips`, `loonheffingen_declarations`, and
   `financial_years` — all matched exactly.
4. Re-ran the same restore command against the now-populated disposable
   database without `--force` — confirmed it was refused (exit code 1),
   proving the overwrite guard actually works, not just reads as safe.
5. `dropdb onholland_accounting_restore_test` and removed the scratch dump
   file — no artifact of this test was left behind, and the live dev
   database was never written to by any step above.

## Re-verified (Phase 12, 2026-11-03)

Repeated the full procedure above against the current schema (now
including Phase 12's `password_reset_tokens` table and the new
`users`/`bank_accounts` columns): backup, restore into a fresh disposable
database (`onholland_phase12_restore_test`), compared row counts across
`users`, `companies`, `password_reset_tokens` — all matched exactly.
Dropped the disposable database and removed the scratch dump file
afterward. The live dev database was never touched destructively.

## RPO / RTO

- **RPO target: 24 hours** (daily backup cadence) — **not yet achieved
  in practice**, since no automated backup schedule is wired up (see
  below). Today's actual RPO is "however long since someone last ran
  `backup_db.sh` by hand" — this is a target, not a verified result.
- **RTO target: under 30 minutes** for a single-database restore via
  `restore_db.sh` — the verified restore above (a database with a
  handful of rows) completed in well under a minute; a realistic
  production-sized database's restore time was not measured and would
  need its own benchmark before this target could be called verified
  rather than estimated.

## What this does not cover

- Point-in-time recovery / continuous WAL archiving is not configured —
  this is full logical dump/restore only, suitable for periodic backups,
  not sub-minute recovery points.
- There is no automated backup schedule (cron, managed service) wired up
  yet — running `backup_db.sh` is a manual or externally-scheduled action.
  This is the main reason the RPO target above isn't yet a verified result.
- Backups are not encrypted at rest by this tooling — `pg_dump`'s output
  file should be encrypted (e.g. `gpg`/cloud-provider server-side
  encryption) by whatever process stores it long-term; not implemented
  here.
- Restoring does not re-apply Alembic migrations — a restored dump already
  contains the schema as of the backup; run `alembic upgrade head`
  afterward if migrations have advanced since the backup was taken.
