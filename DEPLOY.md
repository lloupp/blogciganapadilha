# 🌐 Rodando o blog localmente com o domínio próprio

Guia para servir `blogciganapadilha.com.br` a partir do seu computador (sem VPS),
usando Cloudflare Tunnel + Chatwoot Cloud.

## Visão geral

```
Internet → Cloudflare (DNS + TLS) → Cloudflare Tunnel (cloudflared) → Django/Gunicorn (localhost:8000)
```

O `cloudflared` abre uma conexão de saída do seu PC até a Cloudflare — não é
necessário abrir portas no roteador nem ter IP público fixo. O site só fica
no ar enquanto o processo `cloudflared` e o servidor Django estiverem rodando
na sua máquina.

## 1. Migrar o DNS para a Cloudflare

1. Criar conta em https://dash.cloudflare.com e adicionar o domínio
   `blogciganapadilha.com.br` (plano gratuito).
2. A Cloudflare mostra dois nameservers (ex: `xxx.ns.cloudflare.com`).
3. No painel do registrador (Hostinger → Domínios → `blogciganapadilha.com.br`
   → Nameservers), trocar para os nameservers da Cloudflare.
4. Aguardar propagação (a Cloudflare avisa por e-mail quando o domínio está ativo).

## 2. Instalar e configurar o `cloudflared`

```bash
# instalar (ver instruções específicas do seu SO em developers.cloudflare.com/cloudflared)
cloudflared tunnel login
cloudflared tunnel create blog-cigana
cloudflared tunnel route dns blog-cigana blogciganapadilha.com.br
cloudflared tunnel route dns blog-cigana www.blogciganapadilha.com.br
```

Criar `~/.cloudflared/config.yml`:

```yaml
tunnel: blog-cigana
credentials-file: /caminho/para/<TUNNEL_ID>.json

ingress:
  - hostname: blogciganapadilha.com.br
    service: http://localhost:8000
  - hostname: www.blogciganapadilha.com.br
    service: http://localhost:8000
  - service: http_status:404
```

Rodar o túnel:

```bash
cloudflared tunnel run blog-cigana
```

## 3. Configurar o `.env` local

O arquivo `.env` não é versionado (está no `.gitignore`). Criar um novo na raiz
do projeto com, no mínimo:

```
SECRET_KEY=<gerar uma chave nova, não reaproveitar a da VPS>
DEBUG=False
ALLOWED_HOSTS=localhost,127.0.0.1,blogciganapadilha.com.br,www.blogciganapadilha.com.br
CSRF_TRUSTED_ORIGINS=https://blogciganapadilha.com.br,https://www.blogciganapadilha.com.br
SECURE_SSL_REDIRECT=False
GOOGLE_ANALYTICS_ID=<seu ID GA4, se usar>
CHATWOOT_TOKEN=<website token da conta Chatwoot Cloud>
```

**`SECURE_SSL_REDIRECT=False` é importante aqui**: a TLS é terminada pela
Cloudflare antes de chegar no `cloudflared`, que entrega HTTP puro pro
Gunicorn em `localhost`. Sem isso, o `SECURE_PROXY_SSL_HEADER` configurado em
`blog_mae/settings.py` não recebe o header esperado e o Django pode entrar em
loop de redirect.

## 4. Chatwoot Cloud

Não é necessário self-host. Basta:

1. Criar conta em https://app.chatwoot.com e cadastrar o blog como canal
   "Website".
2. Copiar o **website token** gerado e colocar em `CHATWOOT_TOKEN` no `.env`.
3. `CHATWOOT_URL` já tem como padrão `https://app.chatwoot.com` — não precisa
   declarar no `.env` a menos que queira sobrescrever.

## 5. Rodar o servidor

```bash
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn blog_mae.wsgi:application --bind 127.0.0.1:8000
```

Em outro terminal, deixar o `cloudflared tunnel run blog-cigana` rodando.

## 6. Disponibilidade

O site só responde enquanto o Gunicorn **e** o `cloudflared` estiverem
rodando na sua máquina. Fechar o notebook, desligar ou perder a internet
tira o blog e o chat do ar até você ligar de novo — foi a troca aceita ao
sair da VPS (sempre online) para rodar local.

## Checklist de segurança antes de expor pro público

- [ ] `DEBUG=False` no `.env` (nunca rodar exposto com `DEBUG=True`)
- [ ] `SECRET_KEY` nova, gerada localmente — não reutilizar a da VPS antiga
- [ ] Senha do usuário `admin` trocada (a padrão `admin123` do README é só
      para desenvolvimento local, nunca deixar em produção)
- [ ] `ALLOWED_HOSTS` e `CSRF_TRUSTED_ORIGINS` restritos aos domínios reais
      (não usar `*`)
- [ ] Cloudflare com modo "Full (strict)" ou "Full" de SSL/TLS ativado
- [ ] `django-axes` ativo (já vem configurado em `blog_mae/settings.py`) para
      limitar tentativas de login no `/admin/`
- [ ] Backups periódicos de `db.sqlite3` e `media/` (rodando local, você é
      responsável pelo backup — a VPS não fazia isso magicamente, mas agora
      é ainda mais fácil esquecer)
