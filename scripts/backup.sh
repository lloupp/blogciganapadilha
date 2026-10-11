#!/bin/bash
set -euo pipefail

PROJECT_DIR="/home/eduardodlima/projetos/blog_mae"
BACKUP_ROOT="/home/eduardodlima/backups/blog_mae"
DATE=$(date +%F)
DEST="$BACKUP_ROOT/$DATE"
RETENTION_DAYS=14

mkdir -p "$DEST"

"$PROJECT_DIR/venv/bin/python" -c "
import sqlite3
src = sqlite3.connect('$PROJECT_DIR/db.sqlite3')
dst = sqlite3.connect('$DEST/db.sqlite3')
src.backup(dst)
dst.close()
src.close()
"

tar czf "$DEST/media.tar.gz" -C "$PROJECT_DIR" media

find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d -mtime "+$RETENTION_DAYS" -exec rm -rf {} \;

echo "Backup concluído em $DEST"
