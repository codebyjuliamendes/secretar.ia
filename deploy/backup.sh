#!/usr/bin/env sh
# Backup diário do banco, com rotação. Rode pelo cron do servidor:
#   0 3 * * * cd /opt/secretaria && sh deploy/backup.sh >> /var/log/secretaria-backup.log 2>&1
#
# Guarda os últimos KEEP dias em ./backups. Envie uma cópia para fora do servidor (S3, Backblaze, Drive):
# backup que mora no mesmo disco não protege contra perder o disco.
set -eu

KEEP=${KEEP:-14}
DIR=$(dirname "$0")/../backups
STAMP=$(date +%Y-%m-%d_%H%M)
FILE="secretaria_${STAMP}.sql.gz"

mkdir -p "$DIR"
docker compose -f docker-compose.prod.yml exec -T postgres \
	pg_dump -U "${POSTGRES_USER:-postgres}" -d "${POSTGRES_DB:-secretaria}" --no-owner |
	gzip >"$DIR/$FILE"

SIZE=$(wc -c <"$DIR/$FILE")
if [ "$SIZE" -lt 10000 ]; then
	echo "ERRO: backup $FILE saiu com $SIZE bytes; verifique o banco." >&2
	exit 1
fi

find "$DIR" -name 'secretaria_*.sql.gz' -mtime +"$KEEP" -delete
echo "ok $FILE ($SIZE bytes)"

# Restaurar (teste isto pelo menos uma vez, em outro banco):
#   gunzip -c backups/secretaria_AAAA-MM-DD_HHMM.sql.gz | \
#     docker compose -f docker-compose.prod.yml exec -T postgres psql -U postgres -d secretaria_restore
