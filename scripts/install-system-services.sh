#!/bin/bash
# Migra os servicos do Blog da Mae para o systemd do SISTEMA (gerenciador root),
# onde o isolamento de /home (ProtectHome) realmente funciona. Rode com sudo:
#   sudo bash scripts/install-system-services.sh
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "ERRO: rode com sudo (sudo bash scripts/install-system-services.sh)"; exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="eduardodlima"
UID_NUM="$(id -u "$RUN_USER")"

echo ">> 1/5 Instalando unit files do sistema..."
install -m 0644 "$SCRIPT_DIR/system-blog-mae.service"        /etc/systemd/system/blog-mae.service
install -m 0644 "$SCRIPT_DIR/system-blog-mae-tunnel.service" /etc/systemd/system/blog-mae-tunnel.service

echo ">> 2/5 Desativando os servicos antigos de USUARIO (evita conflito na porta 8000)..."
sudo -u "$RUN_USER" XDG_RUNTIME_DIR="/run/user/$UID_NUM" \
  systemctl --user disable --now blog-mae.service blog-mae-tunnel.service 2>/dev/null || true

echo ">> 3/5 Recarregando systemd e ativando os servicos do sistema..."
systemctl daemon-reload
systemctl enable --now blog-mae.service blog-mae-tunnel.service

echo ">> 4/5 Aguardando subir..."
sleep 4
systemctl is-active blog-mae.service blog-mae-tunnel.service

echo ">> 5/5 Provando o isolamento (deve dar 'Permission denied' ou vazio):"
echo "segredo" > "/home/$RUN_USER/PROVA_SANDBOX.txt"
systemctl show blog-mae.service -p ProtectHome -p ReadWritePaths
echo "--- tentando ler arquivo do /home de dentro do sandbox ---"
systemd-run --pipe --quiet --property=User=$RUN_USER \
  --property=ProtectHome=tmpfs \
  --property=ReadWritePaths=/home/$RUN_USER/projetos/blog_mae \
  /bin/cat "/home/$RUN_USER/PROVA_SANDBOX.txt" 2>&1 && echo "!! ATENCAO: leu o arquivo (isolamento NAO aplicou)" || echo "OK: sandbox bloqueou a leitura do /home"
rm -f "/home/$RUN_USER/PROVA_SANDBOX.txt"

echo
echo "Pronto. Site local:"; curl -s -o /dev/null -w "  http://localhost:8000/ -> %{http_code}\n" http://localhost:8000/ || true
