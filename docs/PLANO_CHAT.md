# Plano — Chat de Consultas (inspirado no SorteCigana)

> Projeto: **Blog Cigana Padilha** (`blog_mae`)
> Objetivo: substituir o handoff por WhatsApp por um **chat dentro do site**, entre a cliente e a atendente, com duração controlada pela consulta já paga.
> Status: **Fases 1, 2 e 3 concluídas** (16/11/2026) · extensão de tempo **grátis na v1** (seção 15)

---

## 1. Contexto

Hoje o fluxo termina assim:

1. Cliente escolhe a consulta em `/consultas/`
2. Paga pelo Mercado Pago (Checkout Pro)
3. É levada para `/consultas/sucesso/` ou `/consultas/status/<uuid>/`
4. Recebe um botão **"Falar com a Cigana no WhatsApp"**

O SorteCigana retém a cliente no próprio site: cadastro, minutos comprados, chat com o consultor, status online/offline e histórico. É isso que vamos trazer — **sem** o modelo de créditos e **sem** obrigar cadastro.

### Decisões já fechadas

| Tema | Decisão |
|---|---|
| Cobrança | **Consulta fechada com duração** (30/40/60 min, conforme `TipoConsulta`) |
| Atendentes | **Uma atendente agora**, mas o modelo já suporta várias |
| Tempo real | **Polling** a cada 3 s (sem Redis, sem Channels, sem mudar o deploy) |
| Acesso da cliente | **Link único por consulta** (UUID), sem login |
| Início do relógio | Só quando a atendente clica em **"Iniciar atendimento"** |

---

## 2. Escopo

### Dentro da v1

- Chat texto cliente ↔ atendente, com histórico persistido
- Contador regressivo com o tempo pago; encerramento automático
- Fila de espera: cliente pode escrever antes da atendente iniciar
- Painel da atendente com conversas, não lidas e respostas
- Extensão manual de tempo (+10/+15/+30 min)
- Link do chat liberado somente com pagamento `aprovado`
- Status online/offline da atendente
- Admin para gerenciar atendentes e inspecionar conversas
- Testes automatizados do fluxo e das regras de tempo

### Fora da v1 (anotado para depois)

- WebSocket / mensagens instantâneas
- Envio de imagem, áudio ou vídeo
- Pacotes de minutos/créditos como no SorteCigana
- Notificação por e-mail/WhatsApp quando chega mensagem
- Múltiplos atendentes com fila e distribuição automática
- Avaliação da consulta ao final
- App mobile

---

## 3. Arquitetura

Tudo dentro do app Django `consultas` (já tem `Consulta`, `TipoConsulta`, Mercado Pago e templates). Sem dependência nova.

```
Cliente (polling 3 s)                Atendente (polling 4 s)
        │                                     │
        ├── GET  /consultas/chat/<uuid>/       ├── GET  /consultas/painel/
        ├── GET  .../mensagens/?apos=N         ├── GET  /consultas/painel/<pk>/
        └── POST .../enviar/                   ├── POST .../iniciar|encerrar|estender|enviar
                                               └── GET  .../mensagens/?apos=N
                          │
                    SQLite (WAL recomendado)
```

- **Servidor é a fonte da verdade** do tempo (`segundos_restantes`); o JS só faz contagem local entre polls.
- Respostas em JSON, sem DRF.
- `GET /mensagens/` faz no máximo dois `UPDATE` curtos (marcar como lido); aceitável no volume atual. Se crescer, separar endpoint de "ack".

---

## 4. Modelo de dados

### 4.1 `Atendente` (novo)

| Campo | Tipo | Regra |
|---|---|---|
| `usuario` | OneToOne(User, null, blank) | Login do painel (opcional; admin/staff também acessa) |
| `nome` | CharField(100) | Nome exibido no chat |
| `bio` | TextField(blank) | Aparece no cabeçalho do chat |
| `foto` | ImageField(upload_to='atendentes/') | Opcional |
| `online` | BooleanField(default=False) | Ligado/desligado no admin |
| `ativo` | BooleanField(default=True) | Fora do ar sem apagar |
| `criado_em` | DateTimeField(auto_now_add) | — |

> Migração de dados cria a atendente **"Cigana Padilha"** automaticamente, para o chat nunca abrir sem destinatária.

### 4.2 `Conversa` (novo)

| Campo | Tipo | Regra |
|---|---|---|
| `consulta` | OneToOne(Consulta, related_name='conversa') | 1 conversa por consulta paga |
| `atendente` | FK(Atendente, null, SET_NULL) | Definida ao iniciar (ou primeira ativa) |
| `status` | choices: `aguardando`, `ativa`, `encerrada`, `expirada` | default `aguardando` |
| `iniciada_em` | DateTimeField(null) | Preenchido em "Iniciar atendimento" |
| `segundos_concedidos` | PositiveIntegerField(default=0) | Tempo total liberado (base + extensões) |
| `encerrada_em` | DateTimeField(null) | — |
| `criada_em` / `atualizada_em` | DateTimeField | — |

Métodos:

```python
expira_em           -> iniciada_em + segundos_concedidos (ou None)
segundos_restantes  -> max(0, expira_em - agora)
iniciar(atendente)  -> status='ativa', iniciada_em=now, segundos=duracao*60, msg de sistema
estender(minutos)   -> +minutos*60; se já expirada, reabre por `minutos` (encerrada não reabre)
expirar_se_preciso()-> se ativa e now >= expira_em -> 'expirada' + msg de sistema
encerrar()          -> 'encerrada', encerrada_em=now + msg de sistema
pode_receber_mensagem -> consulta.status == 'aprovado' and status in ('aguardando','ativa') and not expirada
```

### 4.3 `Mensagem` (novo)

| Campo | Tipo | Regra |
|---|---|---|
| `conversa` | FK(Conversa, related_name='mensagens') | — |
| `autor` | choices: `cliente`, `atendente`, `sistema` | — |
| `texto` | TextField | 1–2000 caracteres, obrigatório, sem HTML |
| `lida` | BooleanField(default=False) | Lida pelo outro lado |
| `criada_em` | DateTimeField(auto_now_add) | Ordenação |

Índice `(conversa, id)` e `(conversa, lida)`.

---

## 5. Regras de negócio

1. **Acesso**: só consulta com `status='aprovado'`. Se pendente/recusada → redireciona para a página de status com aviso.
2. **Relógio**: começa no clique da atendente em **Iniciar atendimento**; mensagens anteriores ficam na fila.
3. **Duração**: `tipo_consulta.duracao_minutos` no início. Extensões somam a `segundos_concedidos`.
4. **Expiração**: verificada no servidor a cada request. Ao expirar, chat fica somente leitura e mostra "Tempo encerrado — contratar nova consulta".
5. **Encerramento**: manual pela atendente ou automático por tempo. Não reabre sozinho; extensão reabre.
6. **Uma conversa por consulta**: `get_or_create` a partir do UUID.
7. **Mensagens imutáveis**: sem edição/exclusão pela interface (só admin, se necessário).
8. **Limite de envio**: 20 mensagens/minuto por conversa; 1 mensagem por vez (evita duplo envio).
9. **Online/offline**: a atendente controla no admin; exibido à cliente, sem bloquear o envio.
10. **Privacidade**: link não é indexável (`noindex`), e não aparece em listagens. UUID é a credencial.

---

## 6. Fluxos

### 6.1 Cliente

1. Paga → página de sucesso mostra **"💬 Entrar no chat"** (primário) e WhatsApp como alternativa.
2. Abre `/consultas/chat/<uuid>/`:
   - cabeçalho com nome/foto/status da atendente
   - contador `⏳ 29:41` (cinza enquanto aguardando)
   - histórico em bolhas (cliente à direita, atendente à esquerda, sistema centralizado)
   - caixa de texto + botão Enviar
3. Se `aguardando`: aviso "A Cigana foi avisada e vai iniciar seu atendimento".
4. Se `ativa`: contador correndo; envio liberado.
5. Se `expirada`/`encerrada`: input desabilitado + CTA para nova consulta.

### 6.2 Atendente

1. Admin → **Atendentes** → marcar `online`.
2. `/consultas/painel/` (staff):
   - cards: aguardando (badge), ativas, encerradas recentes
   - cada linha: cliente, tipo, status, tempo restante, não lidas
3. Abre a conversa:
   - botão **Iniciar atendimento** (se aguardando)
   - histórico + caixa de resposta
   - **+10 / +15 / +30 min** e **Encerrar**
4. Polling de 4 s atualiza mensagens e não lidas.

### 6.3 Pagamento

- `sucesso()` e `status()` passam a expor `chat_url` quando `aprovado`.
- `_whatsapp_url()` continua igual; mensagem pode incluir o link do chat (opcional na Fase 4).

---

## 7. Endpoints

### Cliente (sem login; UUID como credencial)

| Método | URL | Função |
|---|---|---|
| GET | `/consultas/chat/<uuid:referencia>/` | Página do chat |
| GET | `/consultas/chat/<uuid:referencia>/mensagens/?apos=N` | JSON: mensagens novas, status, tempo, atendente |
| POST | `/consultas/chat/<uuid:referencia>/enviar/` | JSON `{texto}` → cria mensagem |

Resposta do polling:

```json
{
  "ok": true,
  "status": "ativa",
  "iniciada": true,
  "segundos_restantes": 1720,
  "expira_em": "2026-11-16T15:30:00-03:00",
  "atendente": {"nome": "Cigana Padilha", "foto": "/media/...", "online": true},
  "mensagens": [
    {"id": 12, "autor": "cliente", "texto": "...", "criada_em": "15:01", "lida": true}
  ],
  "ultimo_id": 12
}
```

### Painel (staff only)

| Método | URL | Função |
|---|---|---|
| GET | `/consultas/painel/` | Lista de conversas |
| GET | `/consultas/painel/<int:pk>/` | Página da conversa |
| GET | `/consultas/painel/<int:pk>/mensagens/?apos=N` | Polling |
| POST | `/consultas/painel/<int:pk>/iniciar/` | Inicia e liga o relógio |
| POST | `/consultas/painel/<int:pk>/encerrar/` | Encerra |
| POST | `/consultas/painel/<int:pk>/estender/` | `{minutos: 10}` |
| POST | `/consultas/painel/<int:pk>/enviar/` | `{texto}` |

Todas exigem `staff`. POST exige CSRF (`X-CSRFToken`).

---

## 8. Telas e arquivos

| Arquivo | Ação |
|---|---|
| `consultas/models.py` | `Atendente`, `Conversa`, `Mensagem` + índices/métodos |
| `consultas/migrations/0003_chat.py` | Schema + atendente padrão |
| `consultas/views.py` | Views do chat, polling e painel |
| `consultas/urls.py` | 10 rotas novas (ordem: painel antes do `<slug>` existente) |
| `consultas/forms.py` | Validação de texto (reuso simples) |
| `consultas/admin.py` | `Atendente` com toggle online; `Conversa` + inline de mensagens |
| `templates/consultas/chat.html` | Chat da cliente |
| `templates/consultas/painel.html` | Lista da atendente |
| `templates/consultas/painel_conversa.html` | Conversa da atendente |
| `templates/consultas/sucesso.html` | CTA primário para o chat |
| `templates/consultas/status.html` | CTA para o chat quando aprovado |
| `static/css/chat.css` | Bolhas, contador, responsivo, tokens atuais |
| `static/js/chat.js` | Polling, envio, contagem local, `textContent` (anti-XSS) |
| `static/js/painel_chat.js` | Polling e ações do painel |
| `consultas/tests.py` | Testes (seção 10) |

> `templates/base.html`: adicionar link **"Área da Cigana"** no rodapé apenas para `user.is_staff` (opcional).

---

## 9. Fases de execução

### Fase 1 — Dados e admin (≈2 h)

- [x] Criar `Atendente`, `Conversa`, `Mensagem`
- [x] Migração `0003_chat` + atendente padrão "Cigana Padilha"
- [x] Registrar no admin (online/offline, inline de mensagens, ações)
- [x] `makemigrations`/`migrate` e teste manual no admin (backup em `db.sqlite3.antes-chat`)

> Decisão aplicada: `estender()` **não** reabre conversa `encerrada` manualmente, só `expirada`.

**Aceite:** admin mostra atendente, conversa e mensagens; toggle online persiste.

### Fase 2 — Chat da cliente (≈4 h)

- [x] View `chat` com `get_or_create` e bloqueio por status de pagamento
- [x] `chat_mensagens` (polling) e `chat_enviar` (POST)
- [x] Template + `chat.css` + `chat.js` (o JS já serve ao painel: `data-papel="atendente"`)
- [x] Contador, estados aguardando/ativa/expirada, bolhas, auto-scroll, ✓/✓✓ de leitura
- [x] `noindex` (meta + `X-Robots-Tag`) e link com UUID

**Aceite:** cliente paga (simulado no admin) e conversa; recarregar mantém histórico; link de consulta pendente não abre.

### Fase 3 — Painel da atendente (≈4 h)

- [x] Lista com badges e tempo restante (atualiza a cada 15 s)
- [x] Detalhe, iniciar/encerrar/estender/enviar
- [x] Polling, não lidas, marcação de leitura (✓✓ nos dois lados)
- [x] Proteção `staff` (sem staff → login do admin)
- [x] Link "Área da Cigana" no rodapé, só para staff

**Aceite:** atendente inicia, responde, estende e encerra; cliente vê tudo no próximo poll.

### Fase 4 — Integração e acabamento (≈2 h)

- [ ] CTA "Entrar no chat" em `sucesso.html` e `status.html`
- [ ] WhatsApp como alternativa (sem remover)
- [ ] Revisão mobile (teclado, altura de viewport, safe-area)
- [ ] Textos e estados vazios

**Aceite:** pós-pagamento leva ao chat em 1 clique; WhatsApp continua disponível.

### Fase 5 — Testes, deploy e verificação (≈2 h)

- [ ] `python manage.py test consultas`
- [ ] `collectstatic`
- [ ] Reiniciar Gunicorn + Cloudflare Tunnel
- [ ] Teste real com uma consulta de R$ 50
- [ ] Ativar `PRAGMA journal_mode=WAL` no SQLite (recomendado)
- [ ] Backup do `db.sqlite3` antes do deploy

**Aceite:** fluxo completo em produção, celular + desktop.

---

## 10. Testes automatizados

1. Consulta `pendente` → `/chat/<uuid>/` redireciona para status
2. Consulta `aprovado` → 200 e cria `Conversa` uma única vez
3. Enviar sem texto / >2000 caracteres → 400
4. Enviar antes de iniciar → aceito, status `aguardando`
5. `iniciar` define `segundos_concedidos = duracao*60`
6. Envio após `expira_em` → bloqueado, status `expirada`
7. `estender` soma tempo; reabre conversa expirada
8. `encerrar` bloqueia novos envios
9. Polling com `apos=N` retorna só mensagens novas
10. Painel sem `staff` → 302 para login; com staff → 200
11. Texto com `<script>` aparece escapado (render via `textContent`)
12. CSRF ausente em POST → 403
13. UUID inválido/inexistente → 404

---

## 11. Segurança e antiabuso

- UUID4 como credencial; sem listagem pública de conversas
- `noindex, nofollow` + `robots.txt` já bloqueia `/admin/`
- CSRF em todos os POSTs; `X-Frame-Options` já ativo
- Escapar todo texto no DOM com `textContent` (nunca `innerHTML`)
- Limite de tamanho e throttle por conversa/IP (cache)
- Nenhum dado sensível além do que a cliente escrever
- Retenção sugerida: 6 meses (limpeza manual/management command na v2)
- Backup do SQLite antes de cada deploy

---

## 12. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Polling segurar workers do Gunicorn | 3–4 s, respostas pequenas; com poucas clientes é tranquilo. Escala → Channels |
| SQLite travando com escrita simultânea | WAL + queries curtas; poucas conversas simultâneas |
| Pessoa com o link entra como cliente | UUID difícil de adivinhar; v2: PIN por e-mail/WhatsApp |
| Atendente esquece de encerrar | Expiração automática pelo tempo pago |
| Cliente fecha o navegador e perde o link | Link estável por UUID; sucesso/status sempre reexibem; v2: reenvio por e-mail |
| Fuso horário | Servidor calcula tudo em `America/Sao_Paulo`; JS só espelha |

---

## 13. Melhorias futuras (v2)

1. WebSocket (Channels + Redis) quando houver volume
2. Notificação de nova mensagem por e-mail/WhatsApp
3. Upload de imagem/áudio
4. Pacotes de minutos e saldo
5. Fila e distribuição entre várias atendentes
6. Avaliação (1–5 estrelas) ao encerrar
7. Painel com métricas: conversas/dia, tempo médio, receita

---

## 14. Estimativa

| Fase | Tempo |
|---|---|
| 1. Dados + admin | 2 h |
| 2. Chat cliente | 4 h |
| 3. Painel atendente | 4 h |
| 4. Integração + acabamento | 2 h |
| 5. Testes + deploy | 2 h |
| **Total** | **~14 h (1,5–2 dias)** |

---

## 15. API de pagamento — decisões pendentes

Hoje já existe: **Mercado Pago Checkout Pro** (redirect), webhook que sempre rebusca o pagamento autenticado, bloqueio de valor divergente e boleto excluído. O chat muda o que o pagamento precisa fazer, então estas escolhas precisam ser fechadas **antes da Fase 2**.

### 15.1 Extensão de tempo: grátis ou paga?

| Opção | Como funciona | Prós | Contras |
|---|---|---|---|
| **A. Manual e grátis** (plano atual) | Atendente clica +10/+15/+30 | Zero código de pagamento | Tempo extra não é cobrado; acerto por fora (Pix no WhatsApp) |
| **B. Paga dentro do chat** | Atendente oferece "+15 min por R$ X"; cliente paga; webhook aprovado estende sozinho | Monetiza o "quero mais", como o SorteCigana | Exige modelo de pagamento genérico (15.3) e preços por minuto |
| **C. Híbrido** | Botões manuais continuam (cortesia) + extensão paga opcional | Flexível | Mais UI no painel |

**Recomendação:** A na v1, com o modelo de dados já preparado para B (15.3). Se a extensão paga for prioridade, C.

### 15.2 Onde a cliente paga

| Opção | Experiência | Esforço |
|---|---|---|
| **A. Checkout Pro** (atual) | Sai do site, volta por `back_urls` | Já pronto |
| **B. Pix transparente** (API `/v1/payments` com `payment_method_id='pix'`) | QR code + copia-e-cola **dentro** do site; a página faz polling e abre o chat sozinha ao aprovar | Médio: tela do QR + expiração do Pix |
| **C. Payment Brick** (cartão + Pix embutidos) | Tudo no site, inclusive cartão | Maior: JS do MP, `MERCADOPAGO_PUBLIC_KEY`, PCI fica com o MP |

**Recomendação:** manter A para a consulta inicial e usar **B (Pix transparente)** se a extensão paga entrar: pagar sem sair do chat é o que faz a extensão converter.

### 15.3 Modelo de dados do pagamento

- **Manter campos em `Consulta`** (`mp_payment_id`, `mp_preference_id`): suficiente se só existir um pagamento por consulta (15.1 = A).
- **Novo model `Pagamento`** (`consulta`, `tipo: consulta|extensao`, `minutos`, `valor`, `status`, `mp_payment_id`, `external_reference` UUID próprio, `aplicado_em`): necessário para 15.1 = B/C. O webhook passa a procurar `Pagamento` pela `external_reference` e, se `tipo=extensao` e aprovado, chama `conversa.estender(minutos)` **uma única vez** (idempotente via `aplicado_em`).

**Recomendação:** criar `Pagamento` só quando B/C for aprovado; migrar os campos atuais para ele nessa hora.

### 15.4 Reembolso / chargeback com chat em andamento

Hoje `pode_receber_mensagem` exige `consulta.status == 'aprovado'`, então um `refunded`/`charged_back` vindo do webhook **bloqueia o chat na hora**.

- **A. Bloquear na hora** (comportamento atual)
- **B. Deixar terminar** e só marcar no admin

**Recomendação:** A. É a regra mais segura e não exige código novo.

### 15.5 Assinatura do webhook (`x-signature`)

Hoje não é validada (o corpo é ignorado e o pagamento é rebuscado). Se o webhook passar a **estender tempo**, vale validar: `MERCADOPAGO_WEBHOOK_SECRET` + HMAC-SHA256 do manifest `id:<data.id>;request-id:<x-request-id>;ts:<ts>;`.

**Recomendação:** implementar junto com 15.1 = B/C; opcional se ficar em A.

### Decisão (16/11/2026)

**15.1 = A (grátis na v1).** Com isso 15.2 fica no Checkout Pro, 15.3 sem model `Pagamento`, 15.4 mantém o bloqueio na hora e 15.5 continua opcional. Revisitar a extensão paga depois de ver o uso real.

### Resumo para decidir

| # | Pergunta | Recomendado |
|---|---|---|
| 15.1 | Extensão grátis, paga ou híbrida? | Grátis na v1 |
| 15.2 | Checkout Pro, Pix no site ou Brick? | Checkout Pro; Pix no site se houver extensão paga |
| 15.3 | Novo model `Pagamento`? | Só se a extensão for paga |
| 15.4 | Reembolso bloqueia o chat? | Sim, na hora |
| 15.5 | Validar `x-signature`? | Sim, se o webhook estender tempo |
