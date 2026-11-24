"""Avisos para a dona do blog (Telegram) quando uma consulta é paga."""
import logging
from urllib.parse import quote

import requests
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)


def _destinos():
    return [c.strip() for c in settings.TELEGRAM_CHAT_ID.split(',') if c.strip()]


def enviar_telegram(texto):
    """Envia `texto` a cada chat configurado. Nunca levanta exceção."""
    token = settings.TELEGRAM_BOT_TOKEN
    if not token or not _destinos():
        return False
    ok = True
    for chat_id in _destinos():
        try:
            resp = requests.post(
                f'https://api.telegram.org/bot{token}/sendMessage',
                json={'chat_id': chat_id, 'text': texto, 'disable_web_page_preview': True},
                timeout=8,
            )
            if resp.status_code != 200:
                ok = False
                logger.warning('Telegram recusou o aviso (HTTP %s): %s', resp.status_code, resp.text[:200])
        except requests.RequestException as exc:
            ok = False
            logger.warning('Falha ao enviar aviso pelo Telegram: %s', exc)
    return ok


def avisar_pagamento(consulta):
    tipo = consulta.tipo_consulta
    chat = settings.SITE_URL + reverse('consultas:chat', kwargs={'referencia': consulta.referencia})
    primeiro_nome = (consulta.nome_cliente.split() or [''])[0].title()
    convite = (f'Olá, {primeiro_nome}! Recebi o pagamento da sua consulta ({tipo.nome}). '
               f'Entre no chat por este link para começarmos: {chat}')
    texto = (
        '🔮 Nova consulta paga!\n\n'
        f'{tipo.icone} {tipo.nome} — R$ ' + f'{consulta.valor:.2f}'.replace('.', ',') + '\n'
        f'👤 {consulta.nome_cliente}\n'
        f'📱 WhatsApp: {consulta.whatsapp_cliente}\n\n'
        f'Abra o atendimento: {settings.SITE_URL}/atendimento/\n\n'
        'Se a cliente não aparecer no chat, mande o link para ela pelo WhatsApp '
        f'(já vai com a mensagem pronta): https://wa.me/{consulta.whatsapp_cliente}?text={quote(convite)}'
    )
    return enviar_telegram(texto)


def avisar_depoimento(depoimento):
    url = settings.SITE_URL + reverse('admin:consultas_depoimento_change', args=[depoimento.pk])
    confirmada = '✅ cliente com consulta paga' if depoimento.consulta_id else '⚠️ enviado sem link de consulta'
    texto = (
        '💬 Novo depoimento esperando aprovação\n\n'
        f'👤 {depoimento.nome}' + (f' ({depoimento.cidade})' if depoimento.cidade else '') + '\n'
        f'{confirmada}\n\n'
        f'"{depoimento.texto[:500]}"\n\n'
        f'Aprovar ou recusar: {url}'
    )
    return enviar_telegram(texto)
