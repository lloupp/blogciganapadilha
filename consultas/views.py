import json
import logging
from decimal import Decimal, InvalidOperation
from urllib.parse import quote

import mercadopago
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

from .forms import SolicitarConsultaForm
from .models import Consulta, TipoConsulta

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


def lista(request):
    tipos = TipoConsulta.objects.filter(ativo=True)
    context = {
        'tipos': tipos,
        'mp_configurado': bool(settings.MERCADOPAGO_ACCESS_TOKEN),
    }
    return render(request, 'consultas/lista.html', context)


def solicitar(request, slug):
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
        return render(request, 'consultas/sucesso.html', {'consulta': None, 'whatsapp_url': ''})

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
