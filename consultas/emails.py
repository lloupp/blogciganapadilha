"""E-mails para as clientes: pedido recebido (link do Pix) e pagamento confirmado (link do chat)."""
import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

logger = logging.getLogger(__name__)


def _enviar(consulta, assunto, template, extra):
    if not settings.EMAIL_HOST_PASSWORD or not consulta.email_cliente:
        return False
    contexto = {
        'consulta': consulta,
        'primeiro_nome': (consulta.nome_cliente.split() or [''])[0].title(),
        'status_url': settings.SITE_URL + consulta.get_status_url(),
        **extra,
    }
    try:
        msg = EmailMultiAlternatives(
            assunto, render_to_string(f'consultas/email/{template}.txt', contexto),
            settings.DEFAULT_FROM_EMAIL, [consulta.email_cliente])
        msg.attach_alternative(render_to_string(f'consultas/email/{template}.html', contexto), 'text/html')
        msg.send()
        return True
    except Exception:
        logger.exception('Falha ao enviar o e-mail "%s" da consulta %s', template, consulta.pk)
        return False


def email_pedido_recebido(consulta):
    return _enviar(consulta, f'Seu pedido de consulta: {consulta.tipo_consulta.nome}', 'pedido', {})


def email_pagamento_confirmado(consulta):
    chat_url = settings.SITE_URL + reverse('consultas:chat', kwargs={'referencia': consulta.referencia})
    return _enviar(consulta, '✅ Pagamento confirmado — entre no chat da sua consulta', 'confirmado',
                   {'chat_url': chat_url})
