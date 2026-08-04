from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from .forms import SolicitarConsultaForm
from .models import Consulta, TipoConsulta


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


class SolicitarViewTests(ConsultasTestCase):
    def _post(self, **overrides):
        dados = {'nome': 'Maria', 'email': 'maria@example.com', 'whatsapp': '(51) 99999-8888'}
        dados.update(overrides)
        return self.client.post(reverse('consultas:solicitar', kwargs={'slug': self.tipo.slug}), dados)

    @mock.patch('consultas.views.mercadopago.SDK')
    def test_post_valido_cria_consulta_e_redireciona(self, sdk_cls):
        sdk_cls.return_value = _mock_sdk()
        response = self._post()
        self.assertRedirects(response, 'https://mp.test/init', fetch_redirect_response=False)
        consulta = Consulta.objects.get()
        self.assertEqual(consulta.valor, self.tipo.preco)
        self.assertEqual(consulta.whatsapp_cliente, '5551999998888')
        self.assertEqual(consulta.mp_preference_id, 'pref-123')
        self.assertEqual(consulta.status, 'pendente')

    @mock.patch('consultas.views.mercadopago.SDK')
    def test_preferencia_exclui_boleto(self, sdk_cls):
        sdk = _mock_sdk()
        sdk_cls.return_value = sdk
        self._post()
        preference_data = sdk.preference.return_value.create.call_args[0][0]
        excluidos = preference_data['payment_methods']['excluded_payment_types']
        self.assertIn({'id': 'ticket'}, excluidos)

    @mock.patch('consultas.views.mercadopago.SDK')
    def test_post_invalido_nao_cria_consulta(self, sdk_cls):
        sdk_cls.return_value = _mock_sdk()
        response = self._post(email='invalido')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Consulta.objects.count(), 0)
        self.assertContains(response, 'form-group')

    @mock.patch('consultas.views.mercadopago.SDK')
    def test_falha_do_sdk_cancela_consulta(self, sdk_cls):
        sdk = _mock_sdk()
        sdk.preference.return_value.create.side_effect = RuntimeError('MP fora do ar')
        sdk_cls.return_value = sdk
        response = self._post()
        self.assertRedirects(response, reverse('consultas:lista'))
        self.assertEqual(Consulta.objects.get().status, 'cancelado')

    @mock.patch('consultas.views.mercadopago.SDK')
    def test_throttle_bloqueia_sexto_post(self, sdk_cls):
        sdk_cls.return_value = _mock_sdk()
        for _ in range(5):
            self._post()
        self.assertEqual(Consulta.objects.count(), 5)
        response = self._post()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Consulta.objects.count(), 5)
        self.assertContains(response, 'Muitas tentativas')


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
