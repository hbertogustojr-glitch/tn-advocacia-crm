#!/bin/sh
set -eu

PROJECT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
BACKUP_DIR="$PROJECT_DIR/backups"
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

mkdir -p "$BACKUP_DIR"
cd "$PROJECT_DIR"

docker compose --env-file .env.production -f compose.production.yml exec -T mysql \
    sh -c 'exec mysqldump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction "$MYSQL_DATABASE"' \
    | gzip > "$BACKUP_DIR/legal-assistant-$TIMESTAMP.sql.gz"

find "$BACKUP_DIR" -type f -name 'legal-assistant-*.sql.gz' -mtime +14 -delete
