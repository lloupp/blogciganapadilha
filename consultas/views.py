import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import mercadopago
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from .forms import MensagemForm, SolicitarConsultaForm
from .models import Atendente, Consulta, Conversa, Mensagem, TipoConsulta

logger = logging.getLogger(__name__)

STATUS_MAP = {
    'approved': 'aprovado',
    'pending': 'pendente',
    'in_process': 'pendente',
    'rejected': 'rejeitado',
    'cancelled': 'cancelado',
    'refunded': 'cancelado',
    'charged_back': 'cancelado',
}

THROTTLE_LIMITE = 5
THROTTLE_JANELA = 900  # segundos


def _mp_sdk():
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        return None
    return mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)


def _client_ip(request):
    # Atrás do Cloudflare Tunnel o REMOTE_ADDR é sempre local;
    # o IP real do visitante vem neste header.
    return request.META.get('HTTP_CF_CONNECTING_IP') or request.META.get('REMOTE_ADDR', '')


def _throttle_excedido(request, chave, limite=THROTTLE_LIMITE, janela=THROTTLE_JANELA):
    cache_key = f'consultas:throttle:{chave}:{_client_ip(request)}'
    tentativas = cache.get_or_set(cache_key, 0, janela)
    if tentativas >= limite:
        return True
    try:
        cache.incr(cache_key)
    except ValueError:
        cache.set(cache_key, 1, janela)
    return False


def _whatsapp_url(consulta):
    if not settings.WHATSAPP_NUMERO:
        return ''
    mensagem = (
        f'Ola! Acabei de pagar a consulta "{consulta.tipo_consulta.nome}". '
        f'Meu nome e {consulta.nome_cliente} e a referencia e '
        f'{consulta.referencia}.'
    )
    return f'https://wa.me/{settings.WHATSAPP_NUMERO}?text={quote(mensagem)}'


def _chat_context(consulta):
    """Link e estado do chat para as páginas de sucesso/status (só aprovado)."""
    if consulta is None or consulta.status != 'aprovado':
        return {'chat_url': '', 'chat_status': ''}
    try:
        conversa = consulta.conversa
    except Conversa.DoesNotExist:
        conversa = None
    else:
        conversa.expirar_se_preciso()
    return {
        'chat_url': reverse('consultas:chat', kwargs={'referencia': consulta.referencia}),
        'chat_status': conversa.status if conversa else Conversa.STATUS_AGUARDANDO,
    }


def _aplicar_pagamento(consulta, payment):
    """Aplica um pagamento (já rebuscado autenticado na API) à consulta.

    - Se o valor pago divergir do valor da consulta, não muda o status:
      marca `pagamento_divergente` para decisão manual no admin.
    - Nunca rebaixa uma consulta aprovada (ver Consulta.pode_transicionar).
    """
    consulta.mp_payment_id = str(payment.get('id', '') or '')

    try:
        valor_pago = Decimal(str(payment.get('transaction_amount')))
    except (InvalidOperation, TypeError):
        valor_pago = None

    if valor_pago is not None and valor_pago != consulta.valor:
        logger.warning(
            'Pagamento %s com valor divergente para a consulta %s: pago %s, esperado %s',
            consulta.mp_payment_id, consulta.pk, valor_pago, consulta.valor,
        )
        consulta.pagamento_divergente = True
        consulta.save(update_fields=['pagamento_divergente', 'mp_payment_id', 'atualizado_em'])
        return consulta

    novo_status = STATUS_MAP.get(payment.get('status'))
    if novo_status and consulta.pode_transicionar(novo_status):
        consulta.status = novo_status
    elif novo_status:
        logger.info(
            'Transição de status bloqueada para a consulta %s: %s → %s',
            consulta.pk, consulta.status, novo_status,
        )
    consulta.save(update_fields=['status', 'mp_payment_id', 'atualizado_em'])
    return consulta


def _buscar_consulta(referencia):
    if not referencia:
        return None
    try:
        return Consulta.objects.get(referencia=referencia)
    except (Consulta.DoesNotExist, ValueError, ValidationError):
        return None


def _consultas_fechadas(request):
    return not settings.CONSULTAS_ABERTAS and not request.user.is_staff


def lista(request):
    if _consultas_fechadas(request):
        raise Http404
    tipos = TipoConsulta.objects.filter(ativo=True)
    context = {
        'tipos': tipos,
        'mp_configurado': bool(settings.MERCADOPAGO_ACCESS_TOKEN),
    }
    return render(request, 'consultas/lista.html', context)


def solicitar(request, slug):
    if _consultas_fechadas(request):
        raise Http404
    tipo = get_object_or_404(TipoConsulta, slug=slug, ativo=True)

    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        messages.error(request, 'O pagamento online ainda não está configurado. Tente novamente mais tarde.')
        return redirect('consultas:lista')

    if request.method == 'POST':
        if _throttle_excedido(request, 'solicitar'):
            messages.error(request, 'Muitas tentativas seguidas. Aguarde alguns minutos e tente novamente.')
            return render(request, 'consultas/solicitar.html', {'tipo': tipo, 'form': SolicitarConsultaForm()})

        form = SolicitarConsultaForm(request.POST)
        if not form.is_valid():
            return render(request, 'consultas/solicitar.html', {'tipo': tipo, 'form': form})

        dados = form.cleaned_data
        consulta = Consulta.objects.create(
            tipo_consulta=tipo,
            nome_cliente=dados['nome'],
            email_cliente=dados['email'],
            whatsapp_cliente=dados['whatsapp'],
            valor=tipo.preco,
        )

        preference_data = {
            'items': [{
                'title': f'Consulta: {tipo.nome}',
                'quantity': 1,
                'unit_price': float(tipo.preco),
                'currency_id': 'BRL',
            }],
            'payer': {
                'name': dados['nome'],
                'email': dados['email'],
            },
            'external_reference': str(consulta.referencia),
            'back_urls': {
                'success': request.build_absolute_uri(reverse('consultas:sucesso')),
                'pending': request.build_absolute_uri(reverse('consultas:pendente')),
                'failure': request.build_absolute_uri(reverse('consultas:erro')),
            },
            'auto_return': 'approved',
            'notification_url': request.build_absolute_uri(reverse('consultas:webhook')),
            # Boleto leva dias para compensar e deixaria a consulta pendente
            # por tempo demais; só cartão e Pix.
            'payment_methods': {
                'excluded_payment_types': [{'id': 'ticket'}],
            },
        }

        try:
            sdk = _mp_sdk()
            result = sdk.preference().create(preference_data)
            preference = result['response']
            init_point = preference['init_point']
        except Exception:
            logger.exception('Erro ao criar preferência do Mercado Pago para a consulta %s', consulta.pk)
            consulta.status = 'cancelado'
            consulta.save(update_fields=['status'])
            messages.error(request, 'Não foi possível iniciar o pagamento agora. Tente novamente em instantes.')
            return redirect('consultas:lista')

        consulta.mp_preference_id = preference.get('id', '')
        consulta.save(update_fields=['mp_preference_id'])
        return redirect(init_point)

    return render(request, 'consultas/solicitar.html', {'tipo': tipo, 'form': SolicitarConsultaForm()})


def sucesso(request):
    """Página de retorno de pagamento aprovado.

    O link do WhatsApp só é liberado quando a consulta está de fato com
    status 'aprovado' no banco. Como o retorno do cliente pode chegar
    antes do webhook, se vier um `payment_id` na querystring rebuscamos o
    pagamento autenticado na API e aplicamos o status na hora.
    """
    external_reference = request.GET.get('external_reference')
    consulta = _buscar_consulta(external_reference)
    if consulta is None:
        return render(request, 'consultas/sucesso.html', {'consulta': None, 'whatsapp_url': '', 'chat_url': ''})

    payment_id = request.GET.get('payment_id') or request.GET.get('collection_id')
    if consulta.status != 'aprovado' and payment_id:
        sdk = _mp_sdk()
        if sdk is not None:
            try:
                payment = sdk.payment().get(payment_id)['response']
            except Exception:
                logger.exception('Erro ao revalidar o pagamento %s no retorno da consulta %s', payment_id, consulta.pk)
                payment = None
            if payment and payment.get('external_reference') == str(consulta.referencia):
                consulta = _aplicar_pagamento(consulta, payment)

    if consulta.status != 'aprovado':
        return redirect(consulta.get_status_url())

    context = {
        'consulta': consulta,
        'whatsapp_url': _whatsapp_url(consulta),
        **_chat_context(consulta),
    }
    return render(request, 'consultas/sucesso.html', context)


def status(request, referencia):
    consulta = get_object_or_404(Consulta, referencia=referencia)
    try:
        tentativa = int(request.GET.get('t', 0))
    except ValueError:
        tentativa = 0

    aprovado = consulta.status == 'aprovado'
    auto_refresh = consulta.status == 'pendente' and tentativa < 5
    context = {
        'consulta': consulta,
        'whatsapp_url': _whatsapp_url(consulta) if aprovado else '',
        'auto_refresh': auto_refresh,
        'proxima_url': f'{consulta.get_status_url()}?t={tentativa + 1}',
        **_chat_context(consulta),
    }
    return render(request, 'consultas/status.html', context)


def pendente(request):
    consulta = _buscar_consulta(request.GET.get('external_reference'))
    return render(request, 'consultas/pendente.html', {'consulta': consulta})


def erro(request):
    consulta = _buscar_consulta(request.GET.get('external_reference'))
    return render(request, 'consultas/erro.html', {'consulta': consulta})


@csrf_exempt
def webhook(request):
    """Recebe notificações do Mercado Pago.

    A notificação em si nunca é confiável (qualquer um pode fazer POST
    nesta URL). Por isso, ela só é usada como um sinal para ir buscar o
    pagamento de verdade na API do Mercado Pago usando nosso access
    token — é essa consulta autenticada que decide o status da consulta,
    nunca o corpo da requisição recebida aqui.

    Não validamos o header x-signature: como o corpo é ignorado e o
    pagamento é sempre rebuscado autenticado, um POST forjado no pior
    caso gera uma chamada extra à API. Melhoria futura, se necessário:
    MERCADOPAGO_WEBHOOK_SECRET + HMAC-SHA256 do manifest
    `id:<data.id>;request-id:<x-request-id>;ts:<ts>;`.
    """
    payment_id = request.GET.get('data.id') or request.GET.get('id')
    topic = request.GET.get('type') or request.GET.get('topic')

    if not payment_id and request.body:
        try:
            body = json.loads(request.body.decode('utf-8'))
        except (ValueError, UnicodeDecodeError):
            body = {}
        payment_id = payment_id or (body.get('data') or {}).get('id')
        topic = topic or body.get('type')

    if topic and topic != 'payment':
        return JsonResponse({'status': 'ignored'})

    if not payment_id:
        return JsonResponse({'status': 'ignored'})

    sdk = _mp_sdk()
    if sdk is None:
        return JsonResponse({'status': 'ignored'})

    try:
        result = sdk.payment().get(payment_id)
        payment = result['response']
    except Exception:
        logger.exception('Erro ao consultar o pagamento %s no Mercado Pago', payment_id)
        return JsonResponse({'status': 'error'})

    consulta = _buscar_consulta(payment.get('external_reference'))
    if consulta is None:
        return JsonResponse({'status': 'ignored'})

    _aplicar_pagamento(consulta, payment)
    return JsonResponse({'status': 'ok'})


# ============================================================
# Chat da consulta (cliente acessa pelo UUID, sem login)
# ============================================================

CHAT_LIMITE_MENSAGENS = 20   # por conversa
CHAT_JANELA = 60             # segundos
CHAT_MAX_POR_POLL = 200


def _noindex(response):
    response['X-Robots-Tag'] = 'noindex, nofollow'
    return response


def _obter_conversa(consulta):
    conversa, _ = Conversa.objects.select_related('atendente', 'consulta__tipo_consulta').get_or_create(
        consulta=consulta,
        defaults={'atendente': Atendente.padrao()},
    )
    conversa.expirar_se_preciso()
    return conversa


def _ler_apos(request):
    try:
        return max(0, int(request.GET.get('apos', 0)))
    except (TypeError, ValueError):
        return 0


def _atendente_json(atendente):
    if atendente is None:
        return None
    return {
        'nome': atendente.nome,
        'foto': atendente.foto.url if atendente.foto else '',
        'online': atendente.online,
    }


def chat_payload(conversa, apos, leitor):
    """Estado da conversa + mensagens com id > `apos`.

    `leitor` é quem está lendo ('cliente' ou 'atendente'): as mensagens do
    outro lado são marcadas como lidas.
    """
    outro = Mensagem.AUTOR_ATENDENTE if leitor == Mensagem.AUTOR_CLIENTE else Mensagem.AUTOR_CLIENTE
    conversa.mensagens.filter(autor=outro, lida=False).update(lida=True)

    mensagens = list(conversa.mensagens.filter(id__gt=apos).order_by('id')[:CHAT_MAX_POR_POLL])
    lidas_ate = (
        conversa.mensagens.filter(autor=leitor, lida=True).order_by('-id').values_list('id', flat=True).first()
        or 0
    )
    expira_em = conversa.expira_em
    return {
        'ok': True,
        'status': conversa.status,
        'status_display': conversa.get_status_display(),
        'iniciada': conversa.iniciada_em is not None,
        'pode_enviar': conversa.pode_receber_mensagem,
        'segundos_restantes': conversa.segundos_restantes,
        'expira_em': timezone.localtime(expira_em).isoformat() if expira_em else None,
        'atendente': _atendente_json(conversa.atendente),
        'mensagens': [
            {
                'id': m.id,
                'autor': m.autor,
                'texto': m.texto,
                'criada_em': timezone.localtime(m.criada_em).strftime('%H:%M'),
            }
            for m in mensagens
        ],
        'ultimo_id': mensagens[-1].id if mensagens else apos,
        'lidas_ate': lidas_ate,
    }


def _chat_throttle_excedido(conversa):
    chave = f'consultas:chat:throttle:{conversa.pk}'
    enviadas = cache.get_or_set(chave, 0, CHAT_JANELA)
    if enviadas >= CHAT_LIMITE_MENSAGENS:
        return True
    try:
        cache.incr(chave)
    except ValueError:
        cache.set(chave, 1, CHAT_JANELA)
    return False


def _ler_texto(request):
    if request.content_type == 'application/json':
        try:
            dados = json.loads(request.body.decode('utf-8') or '{}')
        except (ValueError, UnicodeDecodeError):
            return None, 'Requisição inválida.'
        if not isinstance(dados, dict):
            return None, 'Requisição inválida.'
    else:
        dados = request.POST
    form = MensagemForm({'texto': dados.get('texto', '')})
    if not form.is_valid():
        return None, form.errors['texto'][0]
    return form.cleaned_data['texto'], None


def criar_mensagem(request, conversa, autor):
    """Valida e grava uma mensagem; devolve (JsonResponse de erro | None)."""
    texto, erro = _ler_texto(request)
    if erro:
        return JsonResponse({'ok': False, 'erro': erro}, status=400)
    conversa.expirar_se_preciso()
    if not conversa.pode_receber_mensagem:
        return JsonResponse({'ok': False, 'erro': 'Esta conversa não aceita novas mensagens.'}, status=409)
    if _chat_throttle_excedido(conversa):
        return JsonResponse({'ok': False, 'erro': 'Muitas mensagens seguidas. Aguarde um minuto.'}, status=429)
    conversa.mensagens.create(autor=autor, texto=texto)
    Conversa.objects.filter(pk=conversa.pk).update(atualizada_em=timezone.now())
    return None


@never_cache
@require_GET
def chat(request, referencia):
    consulta = get_object_or_404(Consulta.objects.select_related('tipo_consulta'), referencia=referencia)
    if consulta.status != 'aprovado':
        messages.info(request, 'O chat é liberado assim que o pagamento for confirmado.')
        return redirect(consulta.get_status_url())

    conversa = _obter_conversa(consulta)
    context = {
        'consulta': consulta,
        'conversa': conversa,
        'atendente': conversa.atendente,
        'whatsapp_url': _whatsapp_url(consulta),
    }
    return _noindex(render(request, 'consultas/chat.html', context))


def _consulta_do_chat(referencia):
    consulta = get_object_or_404(Consulta, referencia=referencia)
    if consulta.status != 'aprovado':
        resposta = JsonResponse(
            {'ok': False, 'erro': 'Pagamento não confirmado.', 'redirect': consulta.get_status_url()},
            status=403,
        )
        return consulta, resposta
    return consulta, None


@never_cache
@require_GET
def chat_mensagens(request, referencia):
    consulta, erro = _consulta_do_chat(referencia)
    if erro:
        return _noindex(erro)
    conversa = _obter_conversa(consulta)
    return _noindex(JsonResponse(chat_payload(conversa, _ler_apos(request), Mensagem.AUTOR_CLIENTE)))


@never_cache
@require_POST
def chat_enviar(request, referencia):
    consulta, erro = _consulta_do_chat(referencia)
    if erro:
        return _noindex(erro)
    conversa = _obter_conversa(consulta)
    erro = criar_mensagem(request, conversa, Mensagem.AUTOR_CLIENTE)
    if erro:
        return _noindex(erro)
    return _noindex(JsonResponse(chat_payload(conversa, _ler_apos(request), Mensagem.AUTOR_CLIENTE)))


# ============================================================
# Painel da atendente (staff)
# ============================================================

EXTENSOES_PERMITIDAS = (10, 15, 30)
PAINEL_ENCERRADAS_DIAS = 7


def _painel_conversas():
    return Conversa.objects.select_related('consulta__tipo_consulta', 'atendente').annotate(
        nao_lidas=Count(
            'mensagens',
            filter=Q(mensagens__autor=Mensagem.AUTOR_CLIENTE, mensagens__lida=False),
        ),
    )


def _conversa_do_painel(pk):
    conversa = get_object_or_404(_painel_conversas(), pk=pk)
    conversa.expirar_se_preciso()
    return conversa


def _atendente_do_usuario(user):
    return getattr(user, 'atendente', None)


@never_cache
@staff_member_required
@require_GET
def painel(request):
    # Expira as que passaram do tempo antes de montar a lista.
    for conversa in Conversa.objects.filter(status=Conversa.STATUS_ATIVA).select_related('consulta__tipo_consulta'):
        conversa.expirar_se_preciso()

    base = _painel_conversas()
    limite = timezone.now() - timedelta(days=PAINEL_ENCERRADAS_DIAS)
    context = {
        'aguardando': base.filter(status=Conversa.STATUS_AGUARDANDO).order_by('criada_em'),
        'ativas': base.filter(status=Conversa.STATUS_ATIVA).order_by('iniciada_em'),
        'encerradas': base.filter(
            status__in=[Conversa.STATUS_ENCERRADA, Conversa.STATUS_EXPIRADA],
            atualizada_em__gte=limite,
        ).order_by('-atualizada_em')[:30],
        'atendente': _atendente_do_usuario(request.user) or Atendente.padrao(),
    }
    return _noindex(render(request, 'consultas/painel.html', context))


@never_cache
@staff_member_required
@require_GET
def painel_conversa(request, pk):
    conversa = _conversa_do_painel(pk)
    context = {
        'conversa': conversa,
        'consulta': conversa.consulta,
        'extensoes': EXTENSOES_PERMITIDAS,
    }
    return _noindex(render(request, 'consultas/painel_conversa.html', context))


@never_cache
@staff_member_required
@require_GET
def painel_mensagens(request, pk):
    conversa = _conversa_do_painel(pk)
    return JsonResponse(chat_payload(conversa, _ler_apos(request), Mensagem.AUTOR_ATENDENTE))


@never_cache
@staff_member_required
@require_POST
def painel_enviar(request, pk):
    conversa = _conversa_do_painel(pk)
    erro = criar_mensagem(request, conversa, Mensagem.AUTOR_ATENDENTE)
    if erro:
        return erro
    return JsonResponse(chat_payload(conversa, _ler_apos(request), Mensagem.AUTOR_ATENDENTE))


def _acao_painel(request, conversa, ok, erro):
    if not ok:
        return JsonResponse({'ok': False, 'erro': erro}, status=409)
    return JsonResponse(chat_payload(conversa, _ler_apos(request), Mensagem.AUTOR_ATENDENTE))


@never_cache
@staff_member_required
@require_POST
def painel_iniciar(request, pk):
    conversa = _conversa_do_painel(pk)
    if conversa.consulta.status != 'aprovado':
        return JsonResponse({'ok': False, 'erro': 'O pagamento desta consulta não está aprovado.'}, status=409)
    ok = conversa.iniciar(_atendente_do_usuario(request.user))
    return _acao_painel(request, conversa, ok, 'Este atendimento já foi iniciado.')


@never_cache
@staff_member_required
@require_POST
def painel_estender(request, pk):
    conversa = _conversa_do_painel(pk)
    try:
        if request.content_type == 'application/json':
            minutos = int(json.loads(request.body.decode('utf-8') or '{}').get('minutos'))
        else:
            minutos = int(request.POST.get('minutos'))
    except (TypeError, ValueError, AttributeError, UnicodeDecodeError):
        minutos = None
    if minutos not in EXTENSOES_PERMITIDAS:
        return JsonResponse({'ok': False, 'erro': 'Tempo de extensão inválido.'}, status=400)
    ok = conversa.estender(minutos)
    return _acao_painel(request, conversa, ok, 'Só dá para estender um atendimento em andamento ou com tempo esgotado.')


@never_cache
@staff_member_required
@require_POST
def painel_encerrar(request, pk):
    conversa = _conversa_do_painel(pk)
    ok = conversa.encerrar()
    return _acao_painel(request, conversa, ok, 'Este atendimento já está encerrado.')
