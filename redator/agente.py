"""Agente de postagens: limites de uso, contexto (memória), chamada ao opencode e
leitura da resposta.

O agente roda via `opencode run` num diretório só dele (redator/opencode), sem
nenhuma ferramenta: ele só devolve texto. Quem grava o rascunho no banco é este
módulo, e quem publica ou agenda é sempre a dona, pelos botões do admin.
"""
import json
import logging
import os
import re
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from core.models import Categoria, Post, Tag

from .models import Conversa, Memoria, Mensagem

logger = logging.getLogger(__name__)

DIR_OPENCODE = Path(__file__).resolve().parent / 'opencode'
PENSANDO_EXPIRA = timedelta(minutes=10)
MAX_POSTS_CONTEXTO = 40
MAX_MEMORIAS_CONTEXTO = 60
MAX_MEMORIAS_POR_RESPOSTA = 2


# ---------------------------------------------------------------------------
# Limites
# ---------------------------------------------------------------------------

def _inicio_do_dia():
    agora = timezone.localtime()
    return agora.replace(hour=0, minute=0, second=0, microsecond=0)


def mensagens_hoje():
    return Mensagem.objects.filter(autor=Mensagem.DONA, criada_em__gte=_inicio_do_dia()).count()


def restantes_hoje():
    return max(0, settings.REDATOR_MSGS_POR_DIA - mensagens_hoje())


def restantes_na_conversa(conversa):
    usadas = conversa.mensagens.filter(autor=Mensagem.DONA).count()
    return max(0, settings.REDATOR_MSGS_POR_CONVERSA - usadas)


def motivo_bloqueio(conversa, texto):
    """Devolve a mensagem de erro se a dona não puder enviar `texto` agora, ou None."""
    if conversa.encerrada:
        return 'Esta conversa foi encerrada. Comece uma nova conversa para outro post.'
    if conversa.mensagens.filter(estado=Mensagem.PENSANDO).exists():
        return 'O agente ainda está escrevendo a resposta anterior. Aguarde um instante.'
    if not texto.strip():
        return 'Escreva uma mensagem.'
    if len(texto) > settings.REDATOR_MAX_CARACTERES:
        return (f'Mensagem longa demais ({len(texto)} caracteres). '
                f'O limite é {settings.REDATOR_MAX_CARACTERES}.')
    if restantes_hoje() <= 0:
        return (f'O limite de {settings.REDATOR_MSGS_POR_DIA} mensagens por dia foi atingido. '
                'Volte amanhã.')
    if restantes_na_conversa(conversa) <= 0:
        return (f'Esta conversa chegou ao limite de {settings.REDATOR_MSGS_POR_CONVERSA} mensagens. '
                'Publique, agende ou ajuste o rascunho no editor, ou comece uma nova conversa.')
    return None


# ---------------------------------------------------------------------------
# Contexto enviado ao modelo
# ---------------------------------------------------------------------------

def _bloco_memoria():
    linhas = [f'- {m.texto}' for m in Memoria.objects.filter(ativa=True)[:MAX_MEMORIAS_CONTEXTO]]
    return '\n'.join(linhas) or '(nenhuma lembrança ainda)'


def _bloco_posts():
    linhas = []
    for p in Post.objects.select_related('categoria').order_by('-data_criacao')[:MAX_POSTS_CONTEXTO]:
        if p.esta_agendado:
            situacao = f'agendado para {timezone.localtime(p.data_publicacao):%d/%m/%Y %H:%M}'
        elif p.status == 'publicado':
            situacao = f'publicado em {timezone.localtime(p.data_publicacao):%d/%m/%Y}'
        else:
            situacao = 'rascunho'
        categoria = p.categoria.nome if p.categoria else 'sem categoria'
        resumo = f' — {p.subtitulo}' if p.subtitulo else ''
        linhas.append(f'- "{p.titulo}" ({categoria}, {situacao}){resumo}')
    return '\n'.join(linhas) or '(o blog ainda não tem posts)'


def _bloco_rascunho(conversa):
    post = conversa.post
    if not post:
        return '(ainda não há rascunho nesta conversa)'
    tags = ', '.join(post.tags.values_list('nome', flat=True))
    return (
        f'TITULO: {post.titulo}\nSUBTITULO: {post.subtitulo}\n'
        f'CATEGORIA: {post.categoria.nome if post.categoria else ""}\nTAGS: {tags}\n'
        f'TEMPO_LEITURA: {post.tempo_leitura}\nCONTEUDO:\n{post.conteudo}'
    )


def _bloco_conversa(conversa):
    nomes = {Mensagem.DONA: 'Dona', Mensagem.AGENTE: 'Redator', Mensagem.SISTEMA: 'Sistema'}
    linhas = []
    for m in conversa.mensagens.filter(estado=Mensagem.PRONTA):
        texto = m.texto
        if m.autor == Mensagem.AGENTE and m.trouxe_rascunho:
            texto += '\n[o rascunho enviado nesta resposta está em RASCUNHO ATUAL]'
        linhas.append(f'{nomes[m.autor]}: {texto}')
    return '\n\n'.join(linhas)


def montar_prompt(conversa):
    categorias = ', '.join(Categoria.objects.filter(ativo=True).values_list('nome', flat=True))
    hoje = timezone.localtime()
    return (
        f'Data de hoje: {hoje:%d/%m/%Y}.\n\n'
        f'=== MEMÓRIA (o que você já sabe da dona e do blog) ===\n{_bloco_memoria()}\n\n'
        f'=== CATEGORIAS DO BLOG ===\n{categorias or "(nenhuma)"}\n\n'
        f'=== POSTS DO BLOG (mais recentes primeiro) ===\n{_bloco_posts()}\n\n'
        f'=== RASCUNHO ATUAL DESTA CONVERSA ===\n{_bloco_rascunho(conversa)}\n\n'
        f'=== CONVERSA ===\n{_bloco_conversa(conversa)}\n\n'
        'Responda à última mensagem da Dona, seguindo suas instruções.'
    )


# ---------------------------------------------------------------------------
# Chamada ao opencode
# ---------------------------------------------------------------------------

class ErroAgente(Exception):
    pass


def chamar_opencode(prompt):
    """Roda o agente e devolve (texto, tokens_entrada, tokens_saida)."""
    cmd = [
        settings.REDATOR_OPENCODE_BIN, 'run',
        '--model', settings.REDATOR_MODELO,
        '--agent', 'redator',
        '--format', 'json',
        '--archived',
        '--title', 'Agente de postagens do blog',
    ]
    # O opencode usa $PWD (não só o cwd do processo) para achar a configuração
    # do agente; sem isto ele herda a raiz do projeto e diz "Agent not found".
    env = {**os.environ, 'PWD': str(DIR_OPENCODE),
           'OPENCODE_CONFIG': str(DIR_OPENCODE / 'opencode.json')}
    try:
        proc = subprocess.run(
            cmd, input=prompt, capture_output=True, text=True, cwd=DIR_OPENCODE, env=env,
            timeout=settings.REDATOR_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise ErroAgente('O agente demorou demais para responder.')
    except OSError as exc:
        raise ErroAgente(f'Não foi possível iniciar o opencode: {exc}')

    textos, entrada, saida, erros = [], 0, 0, []
    for linha in proc.stdout.splitlines():
        try:
            evento = json.loads(linha)
        except ValueError:
            continue
        parte = evento.get('part') or {}
        if evento.get('type') == 'text' and parte.get('text'):
            textos.append(parte['text'])
        elif evento.get('type') == 'step_finish':
            tokens = parte.get('tokens') or {}
            entrada += int(tokens.get('input') or 0) + int((tokens.get('cache') or {}).get('read') or 0)
            saida += int(tokens.get('output') or 0) + int(tokens.get('reasoning') or 0)
        elif evento.get('type') == 'error' or evento.get('error'):
            erros.append(str(evento.get('error') or evento)[:300])

    texto = '\n'.join(textos).strip()
    if not texto:
        detalhe = '; '.join(erros) or proc.stderr.strip()[-300:] or f'código {proc.returncode}'
        raise ErroAgente(f'O agente não respondeu ({detalhe}).')
    return texto, entrada, saida


# ---------------------------------------------------------------------------
# Leitura da resposta
# ---------------------------------------------------------------------------

RE_POST = re.compile(r'<<<\s*POST\s*\n(.*?)\n?\s*POST\s*>>>', re.S)
RE_MEMORIA = re.compile(r'<<<\s*MEMORIA\s*:\s*(.+?)\s*>>>', re.S)
RE_FORA = re.compile(r'<<<\s*FORA_DO_ASSUNTO\s*>>>')
CAMPOS = ('TITULO', 'SUBTITULO', 'CATEGORIA', 'TAGS', 'TEMPO_LEITURA')


def _ler_post(bloco):
    dados = {}
    linhas = bloco.strip('\n').split('\n')
    for i, linha in enumerate(linhas):
        chave, _, valor = linha.partition(':')
        chave = chave.strip().upper()
        if chave == 'CONTEUDO':
            resto = [valor.strip()] if valor.strip() else []
            dados['CONTEUDO'] = '\n'.join(resto + linhas[i + 1:]).strip()
            break
        if chave in CAMPOS:
            dados[chave] = valor.strip()
    if not dados.get('TITULO') or not dados.get('CONTEUDO'):
        return None
    return dados


def interpretar_resposta(texto):
    """Separa a mensagem visível dos blocos de controle."""
    post = None
    achado = RE_POST.search(texto)
    if achado:
        post = _ler_post(achado.group(1))
    memorias = [m.strip()[:500] for m in RE_MEMORIA.findall(texto) if m.strip()]
    fora = bool(RE_FORA.search(texto))
    visivel = RE_FORA.sub('', RE_MEMORIA.sub('', RE_POST.sub('', texto))).strip()
    if not visivel:
        visivel = 'Pronto, atualizei o rascunho.' if post else '...'
    return {
        'texto': visivel,
        'post': post,
        'memorias': memorias[:MAX_MEMORIAS_POR_RESPOSTA],
        'fora_do_assunto': fora,
    }


def _limpar_conteudo(texto):
    """Tira marcações de Markdown que escapem: o blog mostra texto puro."""
    texto = re.sub(r'^\s{0,3}#{1,6}\s*', '', texto, flags=re.M)
    texto = re.sub(r'\*\*(.+?)\*\*', r'\1', texto)
    texto = re.sub(r'__(.+?)__', r'\1', texto)
    return texto.strip()


def aplicar_post(conversa, dados):
    """Cria ou atualiza o rascunho da conversa. Nunca publica."""
    post = conversa.post
    if post is None or post.status != 'rascunho':
        post = Post(status='rascunho')
    post.titulo = dados['TITULO'][:200]
    post.subtitulo = dados.get('SUBTITULO', '')[:300]
    post.conteudo = _limpar_conteudo(dados['CONTEUDO'])
    nome_categoria = dados.get('CATEGORIA', '').strip()
    post.categoria = (
        Categoria.objects.filter(nome__iexact=nome_categoria).first() if nome_categoria else None
    )
    try:
        post.tempo_leitura = max(1, min(60, int(re.sub(r'\D', '', dados.get('TEMPO_LEITURA', '')) or 0)))
    except ValueError:
        pass
    if not post.tempo_leitura:
        post.tempo_leitura = max(1, round(len(post.conteudo.split()) / 200))
    post.status = 'rascunho'
    post.save()

    tags = []
    for nome in [t.strip() for t in dados.get('TAGS', '').split(',') if t.strip()][:5]:
        nome = nome[:50]
        tag = Tag.objects.filter(nome__iexact=nome).first()
        if tag is None and slugify(nome):
            tag = Tag.objects.filter(slug=slugify(nome)).first() or Tag.objects.create(nome=nome)
        if tag:
            tags.append(tag)
    post.tags.set(tags)

    conversa.post = post
    if not conversa.titulo:
        conversa.titulo = post.titulo[:200]
    conversa.save(update_fields=['post', 'titulo', 'atualizada_em'])
    return post


# ---------------------------------------------------------------------------
# Fluxo
# ---------------------------------------------------------------------------

def enviar(conversa, texto, usuario=None):
    """Registra a mensagem da dona, cria a resposta "pensando" e dispara o agente."""
    with transaction.atomic():
        Mensagem.objects.create(conversa=conversa, autor=Mensagem.DONA, texto=texto.strip())
        resposta = Mensagem.objects.create(
            conversa=conversa, autor=Mensagem.AGENTE, estado=Mensagem.PENSANDO,
        )
        if not conversa.titulo:
            conversa.titulo = texto.strip()[:80]
        # Só estes campos: o objeto pode estar desatualizado quanto ao post.
        conversa.save(update_fields=['titulo', 'atualizada_em'])
    transaction.on_commit(lambda: disparar(resposta.pk))
    return resposta


def disparar(mensagem_id):
    """Responde num processo separado: o gunicorn derruba requisições após 30 s."""
    manage = Path(settings.BASE_DIR) / 'manage.py'
    subprocess.Popen(
        [sys.executable, str(manage), 'redator_responder', str(mensagem_id)],
        cwd=settings.BASE_DIR, start_new_session=True,
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


def responder(mensagem_id):
    """Executado pelo comando redator_responder: chama o modelo e grava o resultado."""
    resposta = Mensagem.objects.select_related('conversa').get(pk=mensagem_id)
    if resposta.estado != Mensagem.PENSANDO:
        return
    conversa = resposta.conversa
    try:
        texto, entrada, saida = chamar_opencode(montar_prompt(conversa))
    except ErroAgente as exc:
        logger.warning('Agente de postagens falhou na mensagem %s: %s', mensagem_id, exc)
        resposta.estado = Mensagem.ERRO
        resposta.texto = f'{exc} Tente enviar de novo daqui a pouco.'
        resposta.save()
        return

    lido = interpretar_resposta(texto)
    with transaction.atomic():
        conversa.refresh_from_db()
        if lido['post'] and not conversa.encerrada:
            aplicar_post(conversa, lido['post'])
            resposta.trouxe_rascunho = True
        for memoria in lido['memorias']:
            Memoria.objects.create(texto=memoria, conversa=conversa)
        resposta.texto = lido['texto']
        resposta.fora_do_assunto = lido['fora_do_assunto']
        resposta.tokens_entrada = entrada
        resposta.tokens_saida = saida
        resposta.estado = Mensagem.PRONTA
        resposta.save()

        fora = conversa.mensagens.filter(fora_do_assunto=True).count()
        if lido['fora_do_assunto'] and fora >= settings.REDATOR_FORA_DO_ASSUNTO_MAX:
            Mensagem.objects.create(
                conversa=conversa, autor=Mensagem.SISTEMA,
                texto='Conversa encerrada: o agente é só para criar postagens do blog. '
                      'Para um novo post, comece outra conversa.',
            )
            conversa.encerrar('Assuntos fora das postagens')


def expirar_pendentes(conversa):
    """Marca como erro respostas presas em "pensando" (ex.: servidor reiniciado)."""
    limite = timezone.now() - PENSANDO_EXPIRA
    conversa.mensagens.filter(estado=Mensagem.PENSANDO, criada_em__lt=limite).update(
        estado=Mensagem.ERRO, texto='A resposta não chegou. Tente enviar de novo.',
    )
