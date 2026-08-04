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
MERCADOPAGO_ACCESS_TOKEN=<access token da conta Mercado Pago>
MERCADOPAGO_PUBLIC_KEY=<public key da conta Mercado Pago>
WHATSAPP_NUMERO=<numero da cigana, so digitos com DDI, ex.: 5551999999999>
```

`WHATSAPP_NUMERO` é obrigatório para o botão "Falar com a Cigana no WhatsApp"
aparecer depois do pagamento aprovado — sem ele o cliente paga mas não recebe
o link de contato.

Enquanto `MERCADOPAGO_ACCESS_TOKEN` estiver vazio, a página de consultas
(`/consultas/`) avisa que o pagamento ainda não está disponível em vez de
quebrar — dá pra subir o site sem isso configurado e ativar depois.

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

## 5. Consultas online (Mercado Pago)

O fluxo em `/consultas/` funciona assim: o cliente escolhe um tipo de
consulta cadastrado no admin (Admin → Tipos de Consulta), preenche nome/e-mail/
WhatsApp e é redirecionado para o Checkout Pro do Mercado Pago (página
hospedada por eles — cartão e Pix; boleto fica desabilitado de propósito,
porque levaria dias para compensar). Depois de pago, o Mercado Pago
chama de volta a `notification_url` (`/consultas/webhook/mercadopago/`), o
Django confirma o pagamento consultando a API do Mercado Pago diretamente
(nunca confia no que chega na notificação em si) e marca a consulta como
paga no admin. Com o pagamento aprovado, a página de sucesso (e a página de
acompanhamento `/consultas/status/<referencia>/`) libera o botão de WhatsApp
para o cliente combinar o horário — o contato em si continua manual.

Passos:

1. Criar/entrar na conta em https://www.mercadopago.com.br, ir em
   "Seu negócio" → "Configurações" → "Credenciais" e pegar o **Access Token**
   e a **Public Key** (comece pelas credenciais de teste/sandbox antes de ir
   pra produção).
2. Colocar em `MERCADOPAGO_ACCESS_TOKEN` / `MERCADOPAGO_PUBLIC_KEY` no `.env`.
3. Cadastrar os tipos de consulta em Admin → Tipos de Consulta (nome, preço,
   duração, ícone).
4. Como a `notification_url` é montada a partir do domínio da própria
   requisição, ela só funciona depois que o Cloudflare Tunnel estiver de pé
   e servindo `blogciganapadilha.com.br` — teste o fluxo completo (pagar com
   um cartão de teste do Mercado Pago) só depois disso.
5. Trocar para as credenciais de produção quando estiver tudo validado.

### Roteiro de teste de ponta a ponta (credenciais de teste)

Antes de divulgar (ou depois de mexer no fluxo), rode este roteiro completo:

1. Garanta que o `.env` está com as credenciais de **teste** do Mercado Pago
   (`MERCADOPAGO_ACCESS_TOKEN` / `MERCADOPAGO_PUBLIC_KEY`) e reinicie o
   serviço: `sudo systemctl restart blog-mae`. Os units instalados chamam-se
   `blog-mae.service` e `blog-mae-tunnel.service` (os arquivos em `scripts/`
   têm o prefixo `system-`, mas são instalados sem ele).
2. Confirme o túnel ativo (`systemctl status blog-mae-tunnel`) e o
   site acessível em `https://blogciganapadilha.com.br`.
3. **Aprovado**: em `/consultas/`, escolha um tipo, preencha o formulário
   (WhatsApp com máscara, ex. `(51) 99999-9999`) e pague com um cartão de
   teste (ex.: Visa `4235 6477 2802 5682`, validade futura, CVV `123`,
   CPF `123.456.789-09`) usando o titular `APRO`. Deve voltar para a página
   de sucesso com o botão de WhatsApp; no admin, a consulta fica "Pago" com
   `mp_payment_id` preenchido e o WhatsApp normalizado (ex.:
   `5551999999999`). Os logs ficam em `journalctl -u blog-mae -f`.
4. **Recusado**: repita com titular `OTHE`. Deve cair na página de erro com
   o link "acompanhar minha consulta"; a página de status não mostra o
   botão de WhatsApp; abrir manualmente
   `/consultas/sucesso/?external_reference=<referencia>` deve redirecionar
   para a página de status **sem** liberar o botão.
5. **Pendente**: use o titular `CONT` (pagamento em análise). Deve cair na
   página de pendente com o link de acompanhamento; a página de status
   atualiza sozinha até o webhook aprovar. Confira também que **boleto não
   aparece** entre os meios de pagamento oferecidos.
6. **Limite de tentativas**: envie o formulário 6 vezes seguidas — a partir
   da 6ª aparece a mensagem de "muitas tentativas".
7. Depois de validar, apague as consultas de teste no admin e, quando as
   credenciais produtivas estiverem ativas, troque as duas chaves no `.env`
   e reinicie o serviço.

## 6. Rodar o servidor

```bash
source venv/bin/activate
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn blog_mae.wsgi:application --bind 127.0.0.1:8000
```

Em outro terminal, deixar o `cloudflared tunnel run blog-cigana` rodando.

## 7. Disponibilidade

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
- [ ] Credenciais de **produção** do Mercado Pago (não as de teste) antes de
      divulgar o link de consultas pra clientes reais
