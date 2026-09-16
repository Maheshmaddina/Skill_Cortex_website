#!/bin/sh
# Compressed PostgreSQL backup of the production stack, keeping the last KEEP_DAYS days.
# Cron example (daily 02:30):  30 2 * * * cd /opt/skill-cortex && ./deploy/backup.sh >> backups/backup.log 2>&1
set -eu

cd "$(dirname "$0")/.."
ENV_FILE="${ENV_FILE:-.env.production}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_DAYS="${KEEP_DAYS:-14}"

mkdir -p "$BACKUP_DIR"
target="$BACKUP_DIR/skill_cortex_$(date -u +%Y%m%dT%H%M%SZ).sql.gz"

docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml exec -T db \
  sh -c 'pg_dump --clean --if-exists --no-owner -U "$POSTGRES_USER" "$POSTGRES_DB"' \
  | gzip > "$target.partial"
mv "$target.partial" "$target"

find "$BACKUP_DIR" -name 'skill_cortex_*.sql.gz' -mtime +"$KEEP_DAYS" -delete
echo "$(date -u +%FT%TZ) backup written: $target ($(du -h "$target" | cut -f1))"
