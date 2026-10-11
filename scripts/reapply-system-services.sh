#!/bin/bash
# Reaplica os unit files do sistema (apos ajuste no sandbox). Rode com sudo:
#   sudo bash scripts/reapply-system-services.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "ERRO: rode com sudo"; exit 1; }
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

install -m 0644 "$SCRIPT_DIR/system-blog-mae.service"        /etc/systemd/system/blog-mae.service
install -m 0644 "$SCRIPT_DIR/system-blog-mae-tunnel.service" /etc/systemd/system/blog-mae-tunnel.service
systemctl daemon-reload
systemctl restart blog-mae.service blog-mae-tunnel.service
sleep 4
echo "=== status ==="
systemctl is-active blog-mae.service blog-mae-tunnel.service

echo "=== prova de isolamento ==="
echo "segredo" > /home/eduardodlima/PROVA_SANDBOX.txt
systemd-run --pipe --quiet --property=User=eduardodlima \
  --property=TemporaryFileSystem=/home:ro \
  --property=BindPaths=/home/eduardodlima/projetos/blog_mae \
  /bin/cat /home/eduardodlima/PROVA_SANDBOX.txt 2>&1 \
  && echo "!! ATENCAO: leu o arquivo (isolamento NAO aplicou)" \
  || echo "OK: sandbox bloqueou a leitura do /home"
rm -f /home/eduardodlima/PROVA_SANDBOX.txt

echo "=== site local ==="
curl -s -o /dev/null -w "  http://localhost:8000/ -> %{http_code}\n" http://localhost:8000/ || true
