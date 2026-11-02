#!/usr/bin/env bash
# Restores a pg_dump custom-format backup into a target database.
#
# Deliberately refuses to run against a database that already has tables,
# unless --force is passed -- restoring over live data by accident is
# exactly the kind of mistake a backup script should make hard to do.
#
# Usage: ./scripts/restore_db.sh <dump_file> [database_name] [--force]
set -euo pipefail

DUMP_FILE="${1:?Usage: restore_db.sh <dump_file> [database_name] [--force]}"
DB_NAME="${2:-onholland_accounting_restore}"
FORCE="${3:-}"

EXISTING_TABLES=$(psql -d "$DB_NAME" -tAc "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'" 2>/dev/null || echo "0")

if [ "$EXISTING_TABLES" != "0" ] && [ "$FORCE" != "--force" ]; then
  echo "Database '$DB_NAME' already has $EXISTING_TABLES table(s)." >&2
  echo "Refusing to restore over existing data. Re-run with --force to proceed, or target a fresh database name." >&2
  exit 1
fi

createdb "$DB_NAME" 2>/dev/null || true
pg_restore --no-owner --clean --if-exists --dbname="$DB_NAME" "$DUMP_FILE"

echo "Restored '$DUMP_FILE' into database '$DB_NAME'"
