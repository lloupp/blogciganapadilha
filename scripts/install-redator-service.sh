#!/bin/bash
# Instala/atualiza o servico do agente de postagens. Rode com sudo:
#   sudo bash scripts/install-redator-service.sh
set -euo pipefail
[ "$(id -u)" -eq 0 ] || { echo "ERRO: rode com sudo"; exit 1; }
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
RUN_USER="eduardodlima"

# A chave do opencode-go fica no ~/.bashrc do usuario, que servicos nao leem.
# Copia para um arquivo so do root, carregado pelo systemd ao iniciar o servico.
echo ">> Chave do opencode-go -> /etc/blog-mae/redator.env"
LINHA="$(grep -E '^[[:space:]]*export[[:space:]]+OPENCODE_API_KEY=' "/home/$RUN_USER/.bashrc" | tail -1 || true)"
VALOR="${LINHA#*=}"; VALOR="${VALOR%\"}"; VALOR="${VALOR#\"}"; VALOR="${VALOR%\'}"; VALOR="${VALOR#\'}"
if [ -z "$VALOR" ]; then
  echo "ERRO: nao achei 'export OPENCODE_API_KEY=' em /home/$RUN_USER/.bashrc"; exit 1
fi
install -d -m 0755 /etc/blog-mae
umask 077
printf 'OPENCODE_API_KEY=%s\n' "$VALOR" > /etc/blog-mae/redator.env
chmod 600 /etc/blog-mae/redator.env
unset VALOR LINHA

install -m 0644 "$SCRIPT_DIR/system-blog-mae-redator.service" /etc/systemd/system/blog-mae-redator.service
systemctl daemon-reload
systemctl enable blog-mae-redator.service
systemctl restart blog-mae-redator.service
sleep 3
echo "=== status ==="
systemctl is-active blog-mae-redator.service
echo "=== teste do opencode dentro do isolamento ==="
systemd-run --pipe --quiet --wait \
  --property=User=eduardodlima --property=Environment=HOME=/home/eduardodlima \
  --property=EnvironmentFile=/etc/blog-mae/redator.env \
  --property=TemporaryFileSystem=/home:ro \
  --property=BindReadOnlyPaths=/home/eduardodlima/.opencode \
  --property=BindReadOnlyPaths=/home/eduardodlima/.config/opencode \
  --property=BindPaths=/home/eduardodlima/.local/share/opencode \
  --property=BindPaths=/home/eduardodlima/.local/state/opencode \
  --property=BindPaths=/home/eduardodlima/.cache/opencode \
  /bin/sh -c '/home/eduardodlima/.opencode/bin/opencode models | grep -q "^opencode-go/beam-free$"' \
  && echo "OK: opencode e a conta opencode-go acessiveis no isolamento" \
  || echo "!! opencode NAO rodou no isolamento"
journalctl -u blog-mae-redator.service -n 5 --no-pager
