#!/bin/sh
# Restore a backup made by deploy/backup.sh:  ./deploy/restore.sh backups/skill_cortex_<timestamp>.sql.gz
# Stops the app (not the database) while restoring, then starts it again.
set -eu

backup="${1:?Usage: deploy/restore.sh <backup.sql.gz>}"
cd "$(dirname "$0")/.."
ENV_FILE="${ENV_FILE:-.env.production}"
compose() { docker compose --env-file "$ENV_FILE" -f docker-compose.prod.yml "$@"; }

printf "Restore %s over the current database? Type 'restore' to continue: " "$backup"
read -r answer
[ "$answer" = "restore" ] || { echo "Aborted."; exit 1; }

compose stop backend scheduler
gunzip -c "$backup" | compose exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -q -U "$POSTGRES_USER" "$POSTGRES_DB"'
compose start backend scheduler
echo "Restored $backup."
