# Auditoria Hermes — blog_mae

Gerado em: `2026-09-06 11:58:38`

## Escopo

- **Não alterei código-fonte nem arquivos de configuração.**
- Arquivo criado/atualizado por pedido do Eduardo: `HERMES_AUDIT.md`.
- Testes executados apenas quando havia comando/estrutura detectável, com timeout curto e sem instalar dependências do projeto.

## Resumo

- Tipo detectado: **Python app/lib**
- Arquivos analisados: **407**
- Tamanho aproximado analisado: **4.81 MB**

## Linguagens / tipos de arquivo

- Outro: 211
- YAML: 68
- JavaScript: 43
- Python: 33
- CSS: 27
- HTML: 12
- Markdown: 6
- Shell: 4
- PDF: 2
- JSON: 1

## Arquivos principais vistos

- `.env`
- `.gitignore`
- `.pi/plans/qual-a-senha-do-admin.md`
- `.pi/plans/teste-a-seguranca-de-https-blogciganapad.md`
- `.playwright-mcp/console-2026-08-04T00-19-20-710Z.log`
- `.playwright-mcp/console-2026-08-04T00-24-01-492Z.log`
- `.playwright-mcp/console-2026-08-04T22-35-01-085Z.log`
- `.playwright-mcp/console-2026-08-04T22-37-25-067Z.log`
- `.playwright-mcp/console-2026-08-04T22-46-02-602Z.log`
- `.playwright-mcp/console-2026-08-04T22-55-03-481Z.log`
- `.playwright-mcp/console-2026-08-25T22-42-21-811Z.log`
- `.playwright-mcp/console-2026-08-25T22-43-59-084Z.log`
- `.playwright-mcp/console-2026-08-25T22-59-38-015Z.log`
- `.playwright-mcp/console-2026-08-25T23-00-48-136Z.log`
- `.playwright-mcp/page-2026-08-04T00-19-23-955Z.yml`
- `.playwright-mcp/page-2026-08-04T00-19-55-572Z.yml`
- `.playwright-mcp/page-2026-08-04T00-20-10-179Z.yml`
- `.playwright-mcp/page-2026-08-04T00-20-28-788Z.yml`
- `.playwright-mcp/page-2026-08-04T00-20-37-017Z.yml`
- `.playwright-mcp/page-2026-08-04T00-21-40-612Z.yml`
- `.playwright-mcp/page-2026-08-04T00-21-49-277Z.yml`
- `.playwright-mcp/page-2026-08-04T00-22-12-035Z.yml`
- `.playwright-mcp/page-2026-08-04T00-23-10-638Z.yml`
- `.playwright-mcp/page-2026-08-04T00-23-21-275Z.yml`
- `.playwright-mcp/page-2026-08-04T00-23-34-472Z.yml`
- `.playwright-mcp/page-2026-08-04T00-24-01-902Z.yml`
- `.playwright-mcp/page-2026-08-04T00-24-27-073Z.yml`
- `.playwright-mcp/page-2026-08-04T00-24-34-854Z.yml`
- `.playwright-mcp/page-2026-08-04T00-24-52-494Z.yml`
- `.playwright-mcp/page-2026-08-04T00-25-02-906Z.yml`
- `.playwright-mcp/page-2026-08-04T00-25-19-749Z.jpeg`
- `.playwright-mcp/page-2026-08-04T00-25-28-516Z.yml`
- `.playwright-mcp/page-2026-08-04T00-25-34-855Z.yml`
- `.playwright-mcp/page-2026-08-04T00-25-47-680Z.yml`
- `.playwright-mcp/page-2026-08-04T00-26-03-077Z.yml`
- `.playwright-mcp/page-2026-08-04T00-26-15-841Z.yml`
- `.playwright-mcp/page-2026-08-04T00-26-22-625Z.yml`
- `.playwright-mcp/page-2026-08-04T00-26-35-591Z.yml`
- `.playwright-mcp/page-2026-08-04T00-26-58-149Z.yml`
- `.playwright-mcp/page-2026-08-04T00-27-07-768Z.yml`
- … mais 367 arquivo(s)

## Estado Git

- Comando: `git status --short --branch`
- Exit code: `0`

```text
## main...origin/main [à frente 3]
?? MANUAL_COM_IMAGENS.md
?? MANUAL_COM_IMAGENS.pdf
?? MANUAL_SEM_IMAGENS.md
?? MANUAL_SEM_IMAGENS.pdf
?? docs/
?? manual_prompt.txt
?? scripts/
```

## Resultado dos testes / validações

### ✅ OK
- Comando: `python3 -m compileall -q /home/eduardodlima/projetos/blog_mae/manage.py /home/eduardodlima/projetos/blog_mae/core/sitemaps.py /home/eduardodlima/projetos/blog_mae/core/models.py /home/eduardodlima/projetos/blog_mae/core/urls.py /home/eduardodlima/projetos/blog_mae/core/__init__.py /home/eduardodlima/projetos/blog_mae/core/apps.py /home/eduardodlima/projetos/blog_mae/core/views.py /home/eduardodlima/projetos/blog_mae/core/context_processors.py /home/eduardodlima/projetos/blog_mae/core/admin.py /home/eduardodlima/projetos/blog_mae/core/tests.py /home/eduardodlima/projetos/blog_mae/core/management/__init__.py /home/eduardodlima/projetos/blog_mae/core/management/commands/seed.py /home/eduardodlima/projetos/blog_mae/core/management/commands/__init__.py /home/eduardodlima/projetos/blog_mae/core/migrations/0002_post_video_url.py /home/eduardodlima/projetos/blog_mae/core/migrations/0001_initial.py /home/eduardodlima/projetos/blog_mae/core/migrations/__init__.py /home/eduardodlima/projetos/blog_mae/consultas/admin.py /home/eduardodlima/projetos/blog_mae/consultas/__init__.py /home/eduardodlima/projetos/blog_mae/consultas/tests.py /home/eduardodlima/projetos/blog_mae/consultas/urls.py /home/eduardodlima/projetos/blog_mae/consultas/views.py /home/eduardodlima/projetos/blog_mae/consultas/models.py /home/eduardodlima/projetos/blog_mae/consultas/apps.py /home/eduardodlima/projetos/blog_mae/consultas/forms.py /home/eduardodlima/projetos/blog_mae/consultas/migrations/__init__.py /home/eduardodlima/projetos/blog_mae/consultas/migrations/0002_consulta_pagamento_divergente.py /home/eduardodlima/projetos/blog_mae/consultas/migrations/0001_initial.py /home/eduardodlima/projetos/blog_mae/blog_mae/asgi.py /home/eduardodlima/projetos/blog_mae/blog_mae/urls.py /home/eduardodlima/projetos/blog_mae/blog_mae/wsgi.py /home/eduardodlima/projetos/blog_mae/blog_mae/__init__.py /home/eduardodlima/projetos/blog_mae/blog_mae/settings.py /home/eduardodlima/projetos/blog_mae/scripts/build_manual_pdf.py`
- Exit code: `0`
- Tempo: `1.58s`

```text
(sem saída)
```


## Propostas gerais de melhoria

1. Criar suíte mínima de testes em `tests/`.

## Próximo passo sugerido

Priorizar pequenas melhorias incrementais com teste antes/depois, porque o estado atual validou sem falhas nos checks executados.
