from datetime import timedelta
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from core.models import Categoria, Post, Tag

from . import agente
from .models import Conversa, Memoria, Mensagem

RESPOSTA_COM_POST = """Aqui está a primeira versão!

<<<POST
TITULO: O Sol no Tarô
SUBTITULO: A carta da alegria e da clareza
CATEGORIA: tarô
TAGS: tarô, arcanos maiores, Sol
TEMPO_LEITURA: 6
CONTEUDO:
## O que é a carta

O Sol traz **luz** e alegria.

Segundo parágrafo.
POST>>>
<<<MEMORIA: A dona prefere posts curtos, com até 600 palavras>>>"""

CONFIG = dict(
    SECURE_SSL_REDIRECT=False,
    STATICFILES_STORAGE='django.contrib.staticfiles.storage.StaticFilesStorage',
    REDATOR_MSGS_POR_DIA=5,
    REDATOR_MSGS_POR_CONVERSA=3,
    REDATOR_MAX_CARACTERES=100,
    REDATOR_FORA_DO_ASSUNTO_MAX=2,
)


@override_settings(**CONFIG)
class InterpretarRespostaTests(TestCase):
    def test_separa_texto_post_e_memoria(self):
        lido = agente.interpretar_resposta(RESPOSTA_COM_POST)
        self.assertEqual(lido['texto'], 'Aqui está a primeira versão!')
        self.assertEqual(lido['post']['TITULO'], 'O Sol no Tarô')
        self.assertEqual(lido['post']['TAGS'], 'tarô, arcanos maiores, Sol')
        self.assertTrue(lido['post']['CONTEUDO'].startswith('## O que é a carta'))
        self.assertTrue(lido['post']['CONTEUDO'].endswith('Segundo parágrafo.'))
        self.assertEqual(lido['memorias'], ['A dona prefere posts curtos, com até 600 palavras'])
        self.assertFalse(lido['fora_do_assunto'])

    def test_fora_do_assunto(self):
        lido = agente.interpretar_resposta('Aqui só ajudo com posts.\n<<<FORA_DO_ASSUNTO>>>')
        self.assertTrue(lido['fora_do_assunto'])
        self.assertEqual(lido['texto'], 'Aqui só ajudo com posts.')
        self.assertIsNone(lido['post'])

    def test_bloco_sem_titulo_e_ignorado(self):
        lido = agente.interpretar_resposta('Oi\n<<<POST\nCONTEUDO:\nTexto\nPOST>>>')
        self.assertIsNone(lido['post'])

    def test_limita_memorias_por_resposta(self):
        texto = 'ok\n' + '\n'.join(f'<<<MEMORIA: item {i}>>>' for i in range(5))
        self.assertEqual(len(agente.interpretar_resposta(texto)['memorias']), 2)


@override_settings(**CONFIG)
class FluxoAgenteTests(TestCase):
    def setUp(self):
        self.categoria = Categoria.objects.create(nome='Tarô')
        self.conversa = Conversa.objects.create()

    def _enviar_e_responder(self, texto, resposta):
        with mock.patch.object(agente, 'disparar'):
            with self.captureOnCommitCallbacks(execute=True):
                msg = agente.enviar(self.conversa, texto)
        with mock.patch.object(agente, 'chamar_opencode', return_value=(resposta, 100, 50)) as chamada:
            agente.responder(msg.pk)
        msg.refresh_from_db()
        return msg, chamada

    def test_cria_rascunho_sem_publicar_e_guarda_memoria(self):
        msg, _ = self._enviar_e_responder('Post sobre O Sol', RESPOSTA_COM_POST)
        self.conversa.refresh_from_db()
        post = self.conversa.post
        self.assertEqual(msg.estado, Mensagem.PRONTA)
        self.assertTrue(msg.trouxe_rascunho)
        self.assertEqual(post.status, 'rascunho')
        self.assertIsNone(post.data_publicacao)
        self.assertEqual(post.categoria, self.categoria)
        self.assertEqual(post.tempo_leitura, 6)
        self.assertEqual(sorted(post.tags.values_list('nome', flat=True)), ['Sol', 'arcanos maiores', 'tarô'])
        self.assertNotIn('##', post.conteudo)
        self.assertNotIn('**', post.conteudo)
        self.assertEqual(Memoria.objects.get().texto, 'A dona prefere posts curtos, com até 600 palavras')
        self.assertEqual(msg.tokens_entrada, 100)

    def test_segunda_versao_atualiza_o_mesmo_rascunho(self):
        self._enviar_e_responder('Post sobre O Sol', RESPOSTA_COM_POST)
        self._enviar_e_responder('Mude o título', RESPOSTA_COM_POST.replace('O Sol no Tarô', 'A luz do Sol'))
        self.assertEqual(Post.objects.count(), 1)
        self.assertEqual(Post.objects.get().titulo, 'A luz do Sol')
        self.assertEqual(Tag.objects.filter(nome__iexact='tarô').count(), 1)

    def test_prompt_leva_memoria_posts_e_rascunho(self):
        Memoria.objects.create(texto='Assinar como Cigana Padilha')
        Memoria.objects.create(texto='Esquecida', ativa=False)
        Post.objects.create(titulo='A Lua no Tarô', conteudo='x', status='publicado')
        self._enviar_e_responder('Post sobre O Sol', RESPOSTA_COM_POST)
        _, chamada = self._enviar_e_responder('Deixe mais curto', 'Feito.')
        prompt = chamada.call_args.args[0]
        self.assertIn('Assinar como Cigana Padilha', prompt)
        self.assertNotIn('Esquecida', prompt)
        self.assertIn('"A Lua no Tarô"', prompt)
        self.assertIn('TITULO: O Sol no Tarô', prompt)
        self.assertIn('Dona: Deixe mais curto', prompt)

    def test_erro_do_opencode_vira_mensagem_de_erro(self):
        with mock.patch.object(agente, 'disparar'):
            with self.captureOnCommitCallbacks(execute=True):
                msg = agente.enviar(self.conversa, 'Post sobre O Sol')
        with mock.patch.object(agente, 'chamar_opencode', side_effect=agente.ErroAgente('Falhou.')):
            agente.responder(msg.pk)
        msg.refresh_from_db()
        self.assertEqual(msg.estado, Mensagem.ERRO)
        self.assertIsNone(Conversa.objects.get().post)

    def test_encerra_apos_assuntos_fora_do_blog(self):
        fora = 'Aqui só ajudo com posts.\n<<<FORA_DO_ASSUNTO>>>'
        self._enviar_e_responder('Como está o tempo?', fora)
        self.conversa.refresh_from_db()
        self.assertFalse(self.conversa.encerrada)
        self._enviar_e_responder('Me conta uma piada', fora)
        self.conversa.refresh_from_db()
        self.assertTrue(self.conversa.encerrada)
        self.assertIn('encerrada', agente.motivo_bloqueio(self.conversa, 'oi'))


@override_settings(**CONFIG)
class LimitesTests(TestCase):
    def setUp(self):
        self.conversa = Conversa.objects.create()

    def _dona(self, conversa, quando=None):
        Mensagem.objects.create(conversa=conversa, autor=Mensagem.DONA, texto='x',
                                criada_em=quando or timezone.now())

    def test_mensagem_longa_demais(self):
        self.assertIn('longa demais', agente.motivo_bloqueio(self.conversa, 'a' * 101))
        self.assertIsNone(agente.motivo_bloqueio(self.conversa, 'a' * 100))

    def test_limite_por_conversa(self):
        for _ in range(3):
            self._dona(self.conversa)
        self.assertIn('limite de 3', agente.motivo_bloqueio(self.conversa, 'oi'))

    def test_limite_por_dia_soma_todas_as_conversas_e_zera_no_dia_seguinte(self):
        outra = Conversa.objects.create()
        ontem = timezone.now() - timedelta(days=1)
        for _ in range(5):
            self._dona(outra, ontem)
        self.assertIsNone(agente.motivo_bloqueio(self.conversa, 'oi'))
        for _ in range(5):
            self._dona(outra)
        self.assertIn('por dia', agente.motivo_bloqueio(self.conversa, 'oi'))

    def test_uma_resposta_por_vez(self):
        Mensagem.objects.create(conversa=self.conversa, autor=Mensagem.AGENTE, estado=Mensagem.PENSANDO)
        self.assertIn('ainda está escrevendo', agente.motivo_bloqueio(self.conversa, 'oi'))

    def test_pensando_antigo_expira(self):
        m = Mensagem.objects.create(conversa=self.conversa, autor=Mensagem.AGENTE, estado=Mensagem.PENSANDO,
                                    criada_em=timezone.now() - timedelta(minutes=11))
        agente.expirar_pendentes(self.conversa)
        m.refresh_from_db()
        self.assertEqual(m.estado, Mensagem.ERRO)


@override_settings(**CONFIG)
class AdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser('dona', 'dona@example.com', 'x')
        self.client.force_login(self.user)
        self.conversa = Conversa.objects.create()
        self.post = Post.objects.create(titulo='O Sol no Tarô', conteudo='Texto', status='rascunho')
        self.conversa.post = self.post
        self.conversa.save()

    def url(self, nome):
        return reverse(f'admin:redator_conversa_{nome}', args=[self.conversa.pk])

    def test_nova_conversa_abre_o_chat(self):
        r = self.client.get(reverse('admin:redator_conversa_add'))
        nova = Conversa.objects.latest('pk')
        self.assertRedirects(r, reverse('admin:redator_conversa_chat', args=[nova.pk]))

    def test_chat_mostra_rascunho_e_botoes(self):
        r = self.client.get(self.url('chat'))
        self.assertContains(r, 'O Sol no Tarô')
        self.assertContains(r, 'Aprovar e publicar agora')
        self.assertContains(r, 'Restam 5 mensagens hoje')

    def test_enviar_dispara_o_agente(self):
        with mock.patch.object(agente, 'disparar') as disparar:
            with self.captureOnCommitCallbacks(execute=True):
                self.client.post(self.url('enviar'), {'texto': 'Deixe mais curto'})
        disparar.assert_called_once()
        self.assertTrue(self.client.get(self.url('estado')).json()['pensando'])

    def test_enviar_bloqueado_nao_dispara(self):
        with mock.patch.object(agente, 'disparar') as disparar:
            r = self.client.post(self.url('enviar'), {'texto': 'a' * 500}, follow=True)
        disparar.assert_not_called()
        self.assertContains(r, 'longa demais')
        self.assertFalse(Mensagem.objects.exists())

    def test_publicar_agora(self):
        self.client.post(self.url('publicar'))
        self.post.refresh_from_db()
        self.conversa.refresh_from_db()
        self.assertEqual(self.post.status, 'publicado')
        self.assertTrue(self.post.esta_publicado)
        self.assertTrue(self.conversa.encerrada)
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 200)

    def test_agendar_so_aparece_na_data(self):
        quando = timezone.localtime() + timedelta(days=2)
        self.client.post(self.url('agendar'), {'quando': quando.strftime('%Y-%m-%dT%H:%M')})
        self.post.refresh_from_db()
        self.assertTrue(self.post.esta_agendado)
        self.client.logout()
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 404)
        self.assertNotContains(self.client.get(reverse('core:post_list')), 'O Sol no Tarô')
        Post.objects.filter(pk=self.post.pk).update(data_publicacao=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 200)

    def test_agendar_no_passado_recusa(self):
        quando = timezone.localtime() - timedelta(hours=1)
        self.client.post(self.url('agendar'), {'quando': quando.strftime('%Y-%m-%dT%H:%M')})
        self.post.refresh_from_db()
        self.assertEqual(self.post.status, 'rascunho')

    def test_publicar_exige_post(self):
        self.client.post(self.url('publicar'))
        self.client.post(self.url('publicar'))  # segunda vez: já não é rascunho
        self.assertEqual(Mensagem.objects.filter(autor=Mensagem.SISTEMA).count(), 1)

    def test_quem_nao_e_staff_nao_entra(self):
        self.client.logout()
        r = self.client.get(self.url('chat'))
        self.assertEqual(r.status_code, 302)
        self.assertIn('/admin/login/', r['Location'])
