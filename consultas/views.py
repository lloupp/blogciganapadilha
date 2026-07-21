import json
import logging

import mercadopago
from django.conf import settings
from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt

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


def _mp_sdk():
    if not settings.MERCADOPAGO_ACCESS_TOKEN:
        return None
    return mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)


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
        nome = request.POST.get('nome', '').strip()
        email = request.POST.get('email', '').strip()
        whatsapp = request.POST.get('whatsapp', '').strip()

        if not nome or not email or not whatsapp:
            messages.error(request, 'Preencha todos os campos para continuar.')
            return render(request, 'consultas/solicitar.html', {'tipo': tipo})

        consulta = Consulta.objects.create(
            tipo_consulta=tipo,
            nome_cliente=nome,
            email_cliente=email,
            whatsapp_cliente=whatsapp,
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
                'name': nome,
                'email': email,
            },
            'external_reference': str(consulta.referencia),
            'back_urls': {
                'success': request.build_absolute_uri(reverse('consultas:sucesso')),
                'pending': request.build_absolute_uri(reverse('consultas:pendente')),
                'failure': request.build_absolute_uri(reverse('consultas:erro')),
            },
            'auto_return': 'approved',
            'notification_url': request.build_absolute_uri(reverse('consultas:webhook')),
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

    return render(request, 'consultas/solicitar.html', {'tipo': tipo})


def sucesso(request):
    return render(request, 'consultas/sucesso.html')


def pendente(request):
    return render(request, 'consultas/pendente.html')


def erro(request):
    return render(request, 'consultas/erro.html')


@csrf_exempt
def webhook(request):
    """Recebe notificações do Mercado Pago.

    A notificação em si nunca é confiável (qualquer um pode fazer POST
    nesta URL). Por isso, ela só é usada como um sinal para ir buscar o
    pagamento de verdade na API do Mercado Pago usando nosso access
    token — é essa consulta autenticada que decide o status da consulta,
    nunca o corpo da requisição recebida aqui.
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

    external_reference = payment.get('external_reference')
    if not external_reference:
        return JsonResponse({'status': 'ignored'})

    try:
        consulta = Consulta.objects.get(referencia=external_reference)
    except (Consulta.DoesNotExist, ValueError):
        return JsonResponse({'status': 'ignored'})

    novo_status = STATUS_MAP.get(payment.get('status'), consulta.status)
    consulta.status = novo_status
    consulta.mp_payment_id = str(payment.get('id', ''))
    consulta.save(update_fields=['status', 'mp_payment_id', 'atualizado_em'])

    return JsonResponse({'status': 'ok'})
