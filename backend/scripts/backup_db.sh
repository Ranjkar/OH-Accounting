#!/usr/bin/env bash
# Dumps the database named in DATABASE_URL (or $1) to a timestamped,
# compressed custom-format pg_dump file. Restore with restore_db.sh.
#
# Usage: ./scripts/backup_db.sh [database_name] [output_dir]
set -euo pipefail

DB_NAME="${1:-onholland_accounting}"
OUT_DIR="${2:-./backups}"
mkdir -p "$OUT_DIR"

TIMESTAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT_FILE="$OUT_DIR/${DB_NAME}_${TIMESTAMP}.dump"

pg_dump --format=custom --compress=9 --no-owner --dbname="$DB_NAME" --file="$OUT_FILE"

echo "Backup written to $OUT_FILE"
echo "Verify integrity with: pg_restore --list \"$OUT_FILE\""
