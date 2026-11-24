import json
from decimal import Decimal
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .forms import SolicitarConsultaForm
from .models import Atendente, Consulta, Conversa, Mensagem, TipoConsulta


def _mock_sdk(payment=None):
    """SDK do Mercado Pago falso: preference().create e payment().get."""
    sdk = mock.Mock()
    sdk.preference.return_value.create.return_value = {
        'response': {'id': 'pref-123', 'init_point': 'https://mp.test/init'},
    }
    sdk.payment.return_value.get.return_value = {'response': payment or {}}
    return sdk


def _payment(consulta, status='approved', valor=None, payment_id='pay-1'):
    return {
        'id': payment_id,
        'status': status,
        'external_reference': str(consulta.referencia),
        'transaction_amount': float(valor if valor is not None else consulta.valor),
    }


@override_settings(
    SECURE_SSL_REDIRECT=False,
    MERCADOPAGO_ACCESS_TOKEN='TEST-token',
    WHATSAPP_NUMERO='5551999999999',
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
    CONSULTAS_ABERTAS=True, TELEGRAM_BOT_TOKEN='', TELEGRAM_CHAT_ID='',
)
class ConsultasTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.tipo = TipoConsulta.objects.create(nome='Tarô do Amor', preco=Decimal('80.00'))

    def _criar_consulta(self, **kwargs):
        dados = {
            'tipo_consulta': self.tipo,
            'nome_cliente': 'Maria',
            'email_cliente': 'maria@example.com',
            'whatsapp_cliente': '5551999998888',
            'valor': self.tipo.preco,
        }
        dados.update(kwargs)
        return Consulta.objects.create(**dados)


class SolicitarConsultaFormTests(TestCase):
    def test_email_invalido(self):
        form = SolicitarConsultaForm({'nome': 'Maria', 'email': 'nao-e-email', 'whatsapp': '51999998888'})
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_whatsapp_com_mascara_normalizado(self):
        form = SolicitarConsultaForm({'nome': 'Maria', 'email': 'maria@example.com', 'whatsapp': '(51) 99999-8888'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['whatsapp'], '5551999998888')

    def test_whatsapp_ja_com_ddi_mantido(self):
        form = SolicitarConsultaForm({'nome': 'Maria', 'email': 'maria@example.com', 'whatsapp': '+55 51 99999-8888'})
        self.assertTrue(form.is_valid(), form.errors)
        self.assertEqual(form.cleaned_data['whatsapp'], '5551999998888')

    def test_whatsapp_curto_invalido(self):
        form = SolicitarConsultaForm({'nome': 'Maria', 'email': 'maria@example.com', 'whatsapp': '99999'})
        self.assertFalse(form.is_valid())
        self.assertIn('whatsapp', form.errors)


class ConsultasFechadasTests(ConsultasTestCase):
    """Com CONSULTAS_ABERTAS=False só staff vê a lista e o formulário."""

    def test_cliente_recebe_404(self):
        with self.settings(CONSULTAS_ABERTAS=False):
            self.assertEqual(self.client.get(reverse('consultas:lista')).status_code, 404)
            url = reverse('consultas:solicitar', args=[self.tipo.slug])
            self.assertEqual(self.client.get(url).status_code, 404)
            self.assertEqual(self.client.post(url, {}).status_code, 404)

    def test_staff_continua_acessando(self):
        from django.contrib.auth import get_user_model
        staff = get_user_model().objects.create_user('staff', password='x', is_staff=True)
        self.client.force_login(staff)
        with self.settings(CONSULTAS_ABERTAS=False):
            self.assertEqual(self.client.get(reverse('consultas:lista')).status_code, 200)
            url = reverse('consultas:solicitar', args=[self.tipo.slug])
            self.assertEqual(self.client.get(url).status_code, 200)


def _order(consulta, status='action_required', pago='0.00', order_id='ORD1'):
    return {
        'id': order_id, 'status': status, 'external_reference': str(consulta.referencia),
        'total_amount': f'{consulta.valor:.2f}', 'total_paid_amount': pago,
        'transactions': {'payments': [{
            'id': 'PAY1', 'date_of_expiration': '2099-01-01T12:00:00.000+00:00',
            'payment_method': {'id': 'pix', 'qr_code': '000201PIXCOPIAECOLA', 'qr_code_base64': 'iVBORw0KGgo='},
        }]},
    }


def _resposta(json_data, status=201):
    r = mock.Mock(status_code=status)
    r.json.return_value = json_data
    return r


class SolicitarViewTests(ConsultasTestCase):
    def _post(self, **overrides):
        dados = {'nome': 'Maria', 'email': 'maria@example.com', 'whatsapp': '(51) 99999-8888'}
        dados.update(overrides)
        return self.client.post(reverse('consultas:solicitar', kwargs={'slug': self.tipo.slug}), dados)

    def _post_com_pix(self, **overrides):
        def criar(url, json, headers, timeout):
            consulta = Consulta.objects.get(referencia=json['external_reference'])
            self.corpo = json
            return _resposta(_order(consulta))
        with mock.patch('consultas.views.requests.post', side_effect=criar):
            return self._post(**overrides)

    def test_post_valido_gera_pix_e_mostra_qr_code(self):
        response = self._post_com_pix()
        consulta = Consulta.objects.get()
        self.assertRedirects(response, consulta.get_status_url(), fetch_redirect_response=False)
        self.assertEqual(consulta.valor, self.tipo.preco)
        self.assertEqual(consulta.whatsapp_cliente, '5551999998888')
        self.assertEqual(consulta.mp_order_id, 'ORD1')
        self.assertEqual(consulta.pix_copia_cola, '000201PIXCOPIAECOLA')
        self.assertEqual(consulta.status, 'pendente')
        self.assertEqual(self.corpo['transactions']['payments'][0]['payment_method']['id'], 'pix')
        self.assertEqual(self.corpo['total_amount'], '80.00')
        with mock.patch('consultas.views.requests.get', return_value=_resposta(_order(consulta), 200)):
            pagina = self.client.get(consulta.get_status_url())
        self.assertContains(pagina, '000201PIXCOPIAECOLA')
        self.assertContains(pagina, 'data:image/png;base64,iVBORw0KGgo=')
        self.assertNotContains(pagina, 'http-equiv="refresh"')

    def test_post_invalido_nao_cria_consulta(self):
        response = self._post_com_pix(email='invalido')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Consulta.objects.count(), 0)
        self.assertContains(response, 'form-group')

    def test_falha_do_mercado_pago_cancela_consulta(self):
        with mock.patch('consultas.views.requests.post', return_value=_resposta({'message': 'erro'}, 400)):
            response = self._post()
        self.assertRedirects(response, reverse('consultas:lista'))
        self.assertEqual(Consulta.objects.get().status, 'cancelado')

    def test_throttle_bloqueia_sexto_post(self):
        for _ in range(5):
            self._post_com_pix()
        self.assertEqual(Consulta.objects.count(), 5)
        response = self._post_com_pix()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Consulta.objects.count(), 5)
        self.assertContains(response, 'Muitas tentativas')


class PixStatusTests(ConsultasTestCase):
    def setUp(self):
        super().setUp()
        self.consulta = self._criar_consulta(mp_order_id='ORD1', pix_copia_cola='000201X', pix_qr_base64='iVBO')

    def _verificar(self, order):
        cache.clear()
        with mock.patch('consultas.views.requests.get', return_value=_resposta(order, 200)):
            return self.client.get(reverse('consultas:verificar', args=[self.consulta.referencia])).json()

    def test_pago_aprova(self):
        self.assertEqual(self._verificar(_order(self.consulta, 'processed', '80.00'))['status'], 'aprovado')
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, 'aprovado')

    def test_aguardando_continua_pendente(self):
        self.assertEqual(self._verificar(_order(self.consulta))['status'], 'pendente')

    def test_vencido_cancela(self):
        self.assertEqual(self._verificar(_order(self.consulta, 'expired'))['status'], 'cancelado')

    def test_valor_divergente_nao_aprova(self):
        self.assertEqual(self._verificar(_order(self.consulta, 'processed', '1.00'))['status'], 'pendente')
        self.consulta.refresh_from_db()
        self.assertTrue(self.consulta.pagamento_divergente)

    def test_pedido_de_outra_consulta_e_ignorado(self):
        outra = self._criar_consulta()
        self.assertEqual(self._verificar(_order(outra, 'processed', '80.00'))['status'], 'pendente')

    def test_nao_consulta_o_mp_a_cada_requisicao(self):
        cache.clear()
        with mock.patch('consultas.views.requests.get', return_value=_resposta(_order(self.consulta), 200)) as get:
            for _ in range(3):
                self.client.get(reverse('consultas:verificar', args=[self.consulta.referencia]))
        self.assertEqual(get.call_count, 1)

    def test_webhook_de_order_aprova(self):
        with mock.patch('consultas.views.requests.get',
                        return_value=_resposta(_order(self.consulta, 'processed', '80.00'), 200)):
            r = self.client.post(reverse('consultas:webhook') + '?type=order&data.id=ORD1')
        self.assertEqual(r.json()['status'], 'ok')
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, 'aprovado')


class WebhookTests(ConsultasTestCase):
    def _notificar(self, payment):
        with mock.patch('consultas.views.mercadopago.SDK') as sdk_cls:
            sdk_cls.return_value = _mock_sdk(payment=payment)
            return self.client.post(
                reverse('consultas:webhook') + f"?type=payment&data.id={payment['id']}",
            )

    def test_pagamento_aprovado(self):
        consulta = self._criar_consulta()
        response = self._notificar(_payment(consulta, status='approved'))
        self.assertEqual(response.json()['status'], 'ok')
        consulta.refresh_from_db()
        self.assertEqual(consulta.status, 'aprovado')
        self.assertEqual(consulta.mp_payment_id, 'pay-1')
        self.assertFalse(consulta.pagamento_divergente)

    def test_evento_atrasado_nao_rebaixa_aprovado(self):
        consulta = self._criar_consulta(status='aprovado')
        self._notificar(_payment(consulta, status='pending'))
        consulta.refresh_from_db()
        self.assertEqual(consulta.status, 'aprovado')

    def test_refund_cancela_aprovado(self):
        consulta = self._criar_consulta(status='aprovado')
        self._notificar(_payment(consulta, status='refunded'))
        consulta.refresh_from_db()
        self.assertEqual(consulta.status, 'cancelado')

    def test_valor_divergente_nao_aprova(self):
        consulta = self._criar_consulta()
        self._notificar(_payment(consulta, status='approved', valor=Decimal('1.00')))
        consulta.refresh_from_db()
        self.assertEqual(consulta.status, 'pendente')
        self.assertTrue(consulta.pagamento_divergente)

    def test_referencia_desconhecida_ignorada(self):
        payment = {
            'id': 'pay-x', 'status': 'approved',
            'external_reference': '00000000-0000-0000-0000-000000000000',
            'transaction_amount': 80.0,
        }
        response = self._notificar(payment)
        self.assertEqual(response.json()['status'], 'ignored')


class SucessoViewTests(ConsultasTestCase):
    def _get(self, consulta, payment_id=None):
        params = f'?external_reference={consulta.referencia}'
        if payment_id:
            params += f'&payment_id={payment_id}'
        return self.client.get(reverse('consultas:sucesso') + params)

    def test_pendente_sem_payment_id_redireciona_sem_liberar(self):
        consulta = self._criar_consulta()
        response = self._get(consulta)
        self.assertRedirects(response, consulta.get_status_url())

    @mock.patch('consultas.views.mercadopago.SDK')
    def test_pendente_com_payment_id_aprovado_na_api_libera(self, sdk_cls):
        consulta = self._criar_consulta()
        sdk_cls.return_value = _mock_sdk(payment=_payment(consulta, status='approved'))
        response = self._get(consulta, payment_id='pay-1')
        self.assertContains(response, 'wa.me/5551999999999')
        consulta.refresh_from_db()
        self.assertEqual(consulta.status, 'aprovado')

    def test_rejeitado_redireciona_sem_liberar(self):
        consulta = self._criar_consulta(status='rejeitado')
        response = self._get(consulta)
        self.assertRedirects(response, consulta.get_status_url())

    def test_aprovado_mostra_whatsapp(self):
        consulta = self._criar_consulta(status='aprovado')
        response = self._get(consulta)
        self.assertContains(response, 'wa.me/5551999999999')


class StatusViewTests(ConsultasTestCase):
    def test_aprovado_mostra_whatsapp(self):
        consulta = self._criar_consulta(status='aprovado')
        response = self.client.get(consulta.get_status_url())
        self.assertContains(response, 'wa.me/5551999999999')

    def test_pendente_nao_mostra_whatsapp_e_tem_refresh(self):
        consulta = self._criar_consulta()
        response = self.client.get(consulta.get_status_url())
        self.assertNotContains(response, 'wa.me/')
        self.assertContains(response, 'http-equiv="refresh"')

    def test_pendente_para_de_atualizar_apos_limite(self):
        consulta = self._criar_consulta()
        response = self.client.get(consulta.get_status_url() + '?t=5')
        self.assertNotContains(response, 'http-equiv="refresh"')

    def test_uuid_inexistente_404(self):
        response = self.client.get('/consultas/status/00000000-0000-0000-0000-000000000000/')
        self.assertEqual(response.status_code, 404)


class ConversaModelTests(TestCase):
    def setUp(self):
        self.tipo = TipoConsulta.objects.create(nome='Tarô', preco=Decimal('50.00'), duracao_minutos=30)
        self.consulta = Consulta.objects.create(
            tipo_consulta=self.tipo, nome_cliente='Ana', email_cliente='ana@example.com',
            whatsapp_cliente='51999999999', valor=Decimal('50.00'), status='aprovado',
        )
        self.conversa = Conversa.objects.create(consulta=self.consulta)

    def _voltar_relogio(self, segundos):
        self.conversa.iniciada_em -= timedelta(seconds=segundos)
        self.conversa.save(update_fields=['iniciada_em'])

    def test_atendente_padrao_criada_pela_migracao(self):
        self.assertEqual(Atendente.padrao().nome, 'Cigana Padilha')

    def test_aguardando_aceita_mensagem_sem_relogio(self):
        self.assertEqual(self.conversa.status, 'aguardando')
        self.assertIsNone(self.conversa.expira_em)
        self.assertTrue(self.conversa.pode_receber_mensagem)

    def test_consulta_nao_aprovada_nao_recebe_mensagem(self):
        self.consulta.status = 'pendente'
        self.consulta.save()
        self.assertFalse(self.conversa.pode_receber_mensagem)

    def test_iniciar_define_tempo_e_atendente(self):
        self.assertTrue(self.conversa.iniciar())
        self.assertEqual(self.conversa.status, 'ativa')
        self.assertEqual(self.conversa.segundos_concedidos, 30 * 60)
        self.assertEqual(self.conversa.atendente.nome, 'Cigana Padilha')
        self.assertGreater(self.conversa.segundos_restantes, 29 * 60)
        self.assertTrue(self.conversa.mensagens.filter(autor=Mensagem.AUTOR_SISTEMA).exists())
        self.assertFalse(self.conversa.iniciar())  # não reinicia

    def test_expira_e_bloqueia(self):
        self.conversa.iniciar()
        self._voltar_relogio(31 * 60)
        self.assertTrue(self.conversa.expirar_se_preciso())
        self.assertEqual(self.conversa.status, 'expirada')
        self.assertFalse(self.conversa.pode_receber_mensagem)

    def test_estender_ativa_soma_tempo(self):
        self.conversa.iniciar()
        self.assertTrue(self.conversa.estender(10))
        self.assertEqual(self.conversa.segundos_concedidos, 40 * 60)

    def test_estender_expirada_reabre(self):
        self.conversa.iniciar()
        self._voltar_relogio(35 * 60)
        self.assertTrue(self.conversa.estender(15))
        self.assertEqual(self.conversa.status, 'ativa')
        self.assertAlmostEqual(self.conversa.segundos_restantes, 15 * 60, delta=2)

    def test_encerrar_bloqueia_e_nao_estende(self):
        self.conversa.iniciar()
        self.assertTrue(self.conversa.encerrar())
        self.assertFalse(self.conversa.pode_receber_mensagem)
        self.assertFalse(self.conversa.estender(10))

    def test_estender_aguardando_nao_faz_nada(self):
        self.assertFalse(self.conversa.estender(10))
        self.assertEqual(self.conversa.segundos_concedidos, 0)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    WHATSAPP_NUMERO='5551999999999',
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
)
class ChatClienteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.tipo = TipoConsulta.objects.create(nome='Tarô', preco=Decimal('50.00'), duracao_minutos=30)
        self.consulta = Consulta.objects.create(
            tipo_consulta=self.tipo, nome_cliente='Ana', email_cliente='ana@example.com',
            whatsapp_cliente='51999999999', valor=Decimal('50.00'), status='aprovado',
        )
        ref = self.consulta.referencia
        self.url_chat = reverse('consultas:chat', args=[ref])
        self.url_msgs = reverse('consultas:chat_mensagens', args=[ref])
        self.url_enviar = reverse('consultas:chat_enviar', args=[ref])

    def _enviar(self, texto, client=None):
        return (client or self.client).post(
            self.url_enviar, data=json.dumps({'texto': texto}), content_type='application/json',
        )

    def test_pendente_redireciona_para_status(self):
        self.consulta.status = 'pendente'
        self.consulta.save()
        resp = self.client.get(self.url_chat)
        self.assertRedirects(resp, self.consulta.get_status_url())
        self.assertFalse(Conversa.objects.exists())
        self.assertEqual(self.client.get(self.url_msgs).status_code, 403)
        self.assertEqual(self._enviar('oi').status_code, 403)

    def test_aprovado_abre_e_cria_conversa_uma_vez(self):
        resp = self.client.get(self.url_chat)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'noindex, nofollow')
        self.assertEqual(resp['X-Robots-Tag'], 'noindex, nofollow')
        self.client.get(self.url_chat)
        self.client.get(self.url_msgs)
        self.assertEqual(Conversa.objects.filter(consulta=self.consulta).count(), 1)
        self.assertEqual(self.consulta.conversa.atendente.nome, 'Cigana Padilha')

    def test_texto_vazio_ou_longo_retorna_400(self):
        self.assertEqual(self._enviar('   ').status_code, 400)
        self.assertEqual(self._enviar('x' * 2001).status_code, 400)
        self.assertEqual(self._enviar('x' * 2000).status_code, 200)

    def test_envio_antes_de_iniciar_fica_aguardando(self):
        resp = self._enviar('Olá, Cigana')
        dados = resp.json()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(dados['status'], 'aguardando')
        self.assertFalse(dados['iniciada'])
        self.assertEqual(dados['segundos_restantes'], 30 * 60)
        self.assertEqual(dados['mensagens'][-1]['texto'], 'Olá, Cigana')

    def test_envio_apos_expirar_bloqueado(self):
        self.client.get(self.url_chat)
        conversa = self.consulta.conversa
        conversa.iniciar()
        conversa.iniciada_em -= timedelta(minutes=31)
        conversa.save(update_fields=['iniciada_em'])
        resp = self._enviar('ainda dá?')
        self.assertEqual(resp.status_code, 409)
        conversa.refresh_from_db()
        self.assertEqual(conversa.status, 'expirada')
        self.assertFalse(self.client.get(self.url_msgs).json()['pode_enviar'])

    def test_encerrada_bloqueia_envio(self):
        self.client.get(self.url_chat)
        self.consulta.conversa.iniciar()
        self.consulta.conversa.encerrar()
        self.assertEqual(self._enviar('oi').status_code, 409)

    def test_polling_retorna_so_novas_e_marca_lidas(self):
        self._enviar('primeira')
        conversa = self.consulta.conversa
        resposta = conversa.mensagens.create(autor=Mensagem.AUTOR_ATENDENTE, texto='Olá!')
        primeira_id = conversa.mensagens.get(texto='primeira').id

        dados = self.client.get(self.url_msgs, {'apos': primeira_id}).json()
        self.assertEqual([m['id'] for m in dados['mensagens']], [resposta.id])
        self.assertEqual(dados['ultimo_id'], resposta.id)
        resposta.refresh_from_db()
        self.assertTrue(resposta.lida)

        dados = self.client.get(self.url_msgs, {'apos': resposta.id}).json()
        self.assertEqual(dados['mensagens'], [])
        self.assertEqual(dados['ultimo_id'], resposta.id)

    def test_html_guardado_como_texto(self):
        payload = '<script>alert(1)</script>'
        dados = self._enviar(payload).json()
        self.assertEqual(dados['mensagens'][-1]['texto'], payload)
        # A página não injeta mensagens no HTML; o JS usa textContent.
        resp = self.client.get(self.url_chat)
        self.assertNotContains(resp, payload)
        self.assertNotContains(resp, 'innerHTML')

    def test_post_sem_csrf_retorna_403(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self._enviar('oi', client=client).status_code, 403)

    def test_uuid_inexistente_404(self):
        import uuid
        ref = uuid.uuid4()
        self.assertEqual(self.client.get(reverse('consultas:chat', args=[ref])).status_code, 404)
        self.assertEqual(self.client.get(reverse('consultas:chat_mensagens', args=[ref])).status_code, 404)
        self.assertEqual(self.client.get('/consultas/chat/nao-e-uuid/').status_code, 404)

    def test_throttle_por_conversa(self):
        for i in range(20):
            self.assertEqual(self._enviar(f'msg {i}').status_code, 200)
        self.assertEqual(self._enviar('uma a mais').status_code, 429)

    def test_get_em_enviar_nao_permitido(self):
        self.assertEqual(self.client.get(self.url_enviar).status_code, 405)


@override_settings(
    SECURE_SSL_REDIRECT=False,
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
)
class PainelTests(TestCase):
    def setUp(self):
        from django.contrib.auth.models import User
        cache.clear()
        self.tipo = TipoConsulta.objects.create(nome='Tarô', preco=Decimal('50.00'), duracao_minutos=30)
        self.consulta = Consulta.objects.create(
            tipo_consulta=self.tipo, nome_cliente='Ana', email_cliente='ana@example.com',
            whatsapp_cliente='51999999999', valor=Decimal('50.00'), status='aprovado',
        )
        self.conversa = Conversa.objects.create(consulta=self.consulta, atendente=Atendente.padrao())
        self.staff = User.objects.create_user('cigana', password='x', is_staff=True)
        self.comum = User.objects.create_user('curioso', password='x')
        self.client.force_login(self.staff)

    def _url(self, nome):
        return reverse(f'painel:{nome}', args=[self.conversa.pk])

    def _post(self, nome, dados=None):
        return self.client.post(self._url(nome), data=json.dumps(dados or {}), content_type='application/json')

    def test_sem_staff_redireciona_para_login(self):
        from django.test import Client
        anonimo = Client()
        comum = Client()
        comum.force_login(self.comum)
        for client in (anonimo, comum):
            for url in (reverse('painel:painel'), self._url('painel_conversa'), self._url('painel_mensagens')):
                resp = client.get(url)
                self.assertEqual(resp.status_code, 302, url)
                self.assertIn('/admin/login/', resp['Location'])
            resp = client.post(self._url('painel_iniciar'))
            self.assertEqual(resp.status_code, 302)
        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.status, 'aguardando')

    def test_staff_ve_lista_e_conversa(self):
        self.conversa.mensagens.create(autor=Mensagem.AUTOR_CLIENTE, texto='oi')
        resp = self.client.get(reverse('painel:painel'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'Ana')
        self.assertContains(resp, 'painel-badge')
        resp = self.client.get(self._url('painel_conversa'))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'ana@example.com')

    def test_fluxo_iniciar_responder_estender_encerrar(self):
        dados = self._post('painel_iniciar').json()
        self.assertEqual(dados['status'], 'ativa')
        self.assertEqual(self._post('painel_iniciar').status_code, 409)

        dados = self._post('painel_enviar', {'texto': 'Bem-vinda!'}).json()
        self.assertEqual(dados['mensagens'][-1]['autor'], 'atendente')

        self.conversa.refresh_from_db()
        antes = self.conversa.segundos_concedidos
        self._post('painel_estender', {'minutos': 15})
        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.segundos_concedidos, antes + 15 * 60)

        self.assertEqual(self._post('painel_estender', {'minutos': 7}).status_code, 400)
        self.assertEqual(self._post('painel_estender', {'minutos': 'x'}).status_code, 400)

        self.assertEqual(self._post('painel_encerrar').json()['status'], 'encerrada')
        self.assertEqual(self._post('painel_encerrar').status_code, 409)
        self.assertEqual(self._post('painel_enviar', {'texto': 'oi'}).status_code, 409)
        self.assertEqual(self._post('painel_estender', {'minutos': 10}).status_code, 409)

    def test_cliente_ve_acoes_da_atendente_no_proximo_poll(self):
        url_cliente = reverse('consultas:chat_mensagens', args=[self.consulta.referencia])
        self._post('painel_iniciar')
        self._post('painel_enviar', {'texto': 'Olá, Ana'})
        from django.test import Client
        dados = Client().get(url_cliente).json()
        self.assertEqual(dados['status'], 'ativa')
        self.assertEqual(dados['mensagens'][-1]['texto'], 'Olá, Ana')

    def test_leitura_nos_dois_sentidos(self):
        msg_cliente = self.conversa.mensagens.create(autor=Mensagem.AUTOR_CLIENTE, texto='oi')
        self.client.get(self._url('painel_mensagens'))
        msg_cliente.refresh_from_db()
        self.assertTrue(msg_cliente.lida)

        from django.test import Client
        url_cliente = reverse('consultas:chat_mensagens', args=[self.consulta.referencia])
        self.assertEqual(Client().get(url_cliente).json()['lidas_ate'], msg_cliente.id)

    def test_estender_reabre_expirada_pelo_painel(self):
        self._post('painel_iniciar')
        Conversa.objects.filter(pk=self.conversa.pk).update(
            iniciada_em=timezone.now() - timedelta(minutes=40),
        )
        self.assertEqual(self.client.get(self._url('painel_mensagens')).json()['status'], 'expirada')
        dados = self._post('painel_estender', {'minutos': 10}).json()
        self.assertEqual(dados['status'], 'ativa')
        self.assertTrue(dados['pode_enviar'])

    def test_lista_expira_conversas_vencidas(self):
        self._post('painel_iniciar')
        Conversa.objects.filter(pk=self.conversa.pk).update(
            iniciada_em=timezone.now() - timedelta(minutes=40),
        )
        self.client.get(reverse('painel:painel'))
        self.conversa.refresh_from_db()
        self.assertEqual(self.conversa.status, 'expirada')

    def test_iniciar_exige_pagamento_aprovado(self):
        Consulta.objects.filter(pk=self.consulta.pk).update(status='cancelado')
        self.assertEqual(self._post('painel_iniciar').status_code, 409)

    def test_post_do_painel_sem_csrf_retorna_403(self):
        from django.test import Client
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.staff)
        resp = client.post(self._url('painel_iniciar'), data='{}', content_type='application/json')
        self.assertEqual(resp.status_code, 403)


class ChatCtaTests(ConsultasTestCase):
    def _chat_url(self, consulta):
        return reverse('consultas:chat', args=[consulta.referencia])

    def test_status_aprovado_mostra_chat_e_whatsapp(self):
        consulta = self._criar_consulta(status='aprovado')
        resp = self.client.get(consulta.get_status_url())
        self.assertContains(resp, self._chat_url(consulta))
        self.assertContains(resp, 'Entrar no chat')
        self.assertContains(resp, 'wa.me/5551999999999')
        self.assertContains(resp, 'noindex, nofollow')

    def test_status_pendente_nao_mostra_chat(self):
        consulta = self._criar_consulta()
        resp = self.client.get(consulta.get_status_url())
        self.assertNotContains(resp, self._chat_url(consulta))

    @mock.patch('consultas.views.mercadopago.SDK')
    def test_sucesso_aprovado_leva_ao_chat(self, sdk_cls):
        consulta = self._criar_consulta()
        sdk_cls.return_value = _mock_sdk(payment=_payment(consulta, status='approved'))
        resp = self.client.get(
            reverse('consultas:sucesso') + f'?external_reference={consulta.referencia}&payment_id=pay-1'
        )
        self.assertContains(resp, self._chat_url(consulta))
        self.assertContains(resp, 'Entrar no chat')

    def test_conversa_encerrada_mostra_ver_conversa(self):
        consulta = self._criar_consulta(status='aprovado')
        conversa = Conversa.objects.create(consulta=consulta)
        conversa.iniciar()
        conversa.encerrar()
        resp = self.client.get(consulta.get_status_url())
        self.assertContains(resp, 'Ver conversa')
        self.assertContains(resp, self._chat_url(consulta))
        self.assertNotContains(resp, 'Entrar no chat')


@override_settings(
    SECURE_SSL_REDIRECT=False, CONSULTAS_ABERTAS=True,
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
)
class ImagemTipoConsultaTests(TestCase):
    def test_cartao_mostra_imagem_ou_emoji(self):
        com = TipoConsulta.objects.create(nome='Tarô do Amor', preco=Decimal('80'), icone='💘')
        com.imagem.name = 'consultas/amor.jpg'
        com.save()
        TipoConsulta.objects.create(nome='Cartas Ciganas', preco=Decimal('50'), icone='🔮')
        r = self.client.get(reverse('consultas:lista'))
        self.assertContains(r, '/media/consultas/amor.jpg')
        self.assertContains(r, '🔮')
        self.assertNotContains(r, '💘')


@override_settings(SECURE_SSL_REDIRECT=False,
                   STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage')
class PainelDentroDoAdminTests(TestCase):
    def test_endereco_antigo_nao_existe_mais(self):
        self.assertEqual(self.client.get('/consultas/painel/').status_code, 404)

    def test_painel_exige_login_da_equipe(self):
        r = self.client.get('/admin/atendimento/')
        self.assertEqual(r.status_code, 302)
        self.assertIn('/admin/login/', r['Location'])

    def test_atalho_curto(self):
        self.assertRedirects(self.client.get('/atendimento/'), '/admin/atendimento/', fetch_redirect_response=False)

    def test_link_no_topo_do_admin(self):
        from django.contrib.auth import get_user_model
        self.client.force_login(get_user_model().objects.create_superuser('a', 'a@example.com', 'x'))
        self.assertContains(self.client.get('/admin/'), 'href="/admin/atendimento/"')


class AvisoTelegramTests(ConsultasTestCase):
    def setUp(self):
        super().setUp()
        self.consulta = self._criar_consulta(mp_order_id='ORD1')

    def _aprovar(self):
        cache.clear()
        with mock.patch('consultas.views.requests.get',
                        return_value=_resposta(_order(self.consulta, 'processed', '80.00'), 200)):
            self.client.get(reverse('consultas:verificar', args=[self.consulta.referencia]))

    @override_settings(TELEGRAM_BOT_TOKEN='123:abc', TELEGRAM_CHAT_ID='999')
    def test_avisa_uma_unica_vez_quando_aprova(self):
        with mock.patch('consultas.avisos.requests.post', return_value=mock.Mock(status_code=200)) as post:
            self._aprovar()
            self._aprovar()
            with mock.patch('consultas.views.requests.get',
                            return_value=_resposta(_order(self.consulta, 'processed', '80.00'), 200)):
                self.client.post(reverse('consultas:webhook') + '?type=order&data.id=ORD1')
        self.assertEqual(post.call_count, 1)
        enviado = post.call_args.kwargs['json']
        self.assertEqual(enviado['chat_id'], '999')
        self.assertIn('Nova consulta paga', enviado['text'])
        self.assertIn('R$ 80,00', enviado['text'])
        self.assertIn('/atendimento/', enviado['text'])

    @override_settings(TELEGRAM_BOT_TOKEN='123:abc', TELEGRAM_CHAT_ID='999')
    def test_falha_do_telegram_nao_impede_aprovacao(self):
        import requests as req
        with mock.patch('consultas.avisos.requests.post', side_effect=req.ConnectionError('fora')):
            self._aprovar()
        self.consulta.refresh_from_db()
        self.assertEqual(self.consulta.status, 'aprovado')

    def test_sem_configuracao_nao_envia(self):
        with mock.patch('consultas.avisos.requests.post') as post:
            self._aprovar()
        post.assert_not_called()


class VerificacaoPeriodicaTests(ConsultasTestCase):
    @override_settings(TELEGRAM_BOT_TOKEN='123:abc', TELEGRAM_CHAT_ID='999')
    def test_confirma_pix_pago_com_pagina_fechada_e_avisa(self):
        from consultas.views import verificar_pix_pendentes
        paga = self._criar_consulta(mp_order_id='ORDPAGO1')
        aguardando = self._criar_consulta(mp_order_id='ORDABERTO1')
        sem_pix = self._criar_consulta()
        respostas = {'ORDPAGO1': _order(paga, 'processed', '80.00', 'ORDPAGO1'),
                     'ORDABERTO1': _order(aguardando, order_id='ORDABERTO1')}

        def get(url, headers, timeout):
            return _resposta(respostas[url.rsplit('/', 1)[1]], 200)
        with mock.patch('consultas.views.requests.get', side_effect=get) as g, \
                mock.patch('consultas.avisos.requests.post', return_value=mock.Mock(status_code=200)) as aviso:
            self.assertEqual(verificar_pix_pendentes(), 1)
        self.assertEqual(g.call_count, 2)
        self.assertEqual(aviso.call_count, 1)
        for c, esperado in ((paga, 'aprovado'), (aguardando, 'pendente'), (sem_pix, 'pendente')):
            c.refresh_from_db()
            self.assertEqual(c.status, esperado)

    def test_webhook_ignora_id_de_pedido_invalido(self):
        with mock.patch('consultas.views.requests.get') as g:
            r = self.client.post(reverse('consultas:webhook') + '?type=order&data.id=../payments/1')
        g.assert_not_called()
        self.assertEqual(r.json()['status'], 'ignored')
