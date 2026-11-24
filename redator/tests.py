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


@override_settings(**CONFIG, REDATOR_MODELO='go/gratis', REDATOR_MODELO_RESERVA='go/pago')
class ModeloReservaTests(TestCase):
    @override_settings(REDATOR_MODELO_RESERVA='go/gratis2, go/pago')
    def test_reservas_em_ordem(self):
        def rodar(prompt, modelo):
            if modelo != 'go/pago':
                raise agente.ErroAgente('falhou')
            return ('ok', 1, 1)
        with mock.patch.object(agente, '_rodar_opencode', side_effect=rodar) as m:
            agente.chamar_opencode('p')
        self.assertEqual([c.args[1] for c in m.call_args_list], ['go/gratis', 'go/gratis2', 'go/pago'])

    def test_usa_reserva_quando_o_principal_falha(self):
        def rodar(prompt, modelo):
            if modelo == 'go/gratis':
                raise agente.ErroAgente('limite atingido')
            return ('ok', 1, 1)
        with mock.patch.object(agente, '_rodar_opencode', side_effect=rodar) as m:
            self.assertEqual(agente.chamar_opencode('p'), ('ok', 1, 1))
        self.assertEqual([c.args[1] for c in m.call_args_list], ['go/gratis', 'go/pago'])

    def test_principal_ok_nao_chama_reserva(self):
        with mock.patch.object(agente, '_rodar_opencode', return_value=('ok', 1, 1)) as m:
            agente.chamar_opencode('p')
        m.assert_called_once_with('p', 'go/gratis')

    @override_settings(REDATOR_MODELO_RESERVA='')
    def test_sem_reserva_propaga_o_erro(self):
        with mock.patch.object(agente, '_rodar_opencode', side_effect=agente.ErroAgente('x')):
            with self.assertRaises(agente.ErroAgente):
                agente.chamar_opencode('p')


@override_settings(**CONFIG)
class WorkerTests(TestCase):
    def test_processa_pendentes_em_ordem_e_sai(self):
        from django.core.management import call_command
        conversa = Conversa.objects.create()
        a = agente.enviar(conversa, 'primeiro')
        outra = Conversa.objects.create()
        b = agente.enviar(outra, 'segundo')
        ordem = []

        def chamar(prompt):
            ordem.append(prompt.rsplit('Dona: ', 1)[1].split('\n')[0])
            return ('Resposta.', 1, 1)
        with mock.patch.object(agente, 'chamar_opencode', side_effect=chamar):
            call_command('redator_worker', '--uma-vez', stdout=open('/dev/null', 'w'))
        self.assertEqual(ordem, ['primeiro', 'segundo'])
        for m in (a, b):
            m.refresh_from_db()
            self.assertEqual(m.estado, Mensagem.PRONTA)
        self.assertIsNone(agente.proxima_pendente())

    def test_erro_inesperado_nao_trava_o_worker(self):
        from django.core.management import call_command
        m = agente.enviar(Conversa.objects.create(), 'oi')
        with mock.patch.object(agente, 'chamar_opencode', side_effect=RuntimeError('bug')), \
                mock.patch('redator.management.commands.redator_worker.responder',
                           side_effect=RuntimeError('bug')):
            call_command('redator_worker', '--uma-vez', stdout=open('/dev/null', 'w'))
        m.refresh_from_db()
        self.assertEqual(m.estado, Mensagem.ERRO)


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

    def test_enviar_deixa_resposta_pendente_para_o_worker(self):
        self.client.post(self.url('enviar'), {'texto': 'Deixe mais curto'})
        self.assertEqual(agente.proxima_pendente(), Mensagem.objects.get(estado=Mensagem.PENSANDO).pk)
        self.assertTrue(self.client.get(self.url('estado')).json()['pensando'])

    def test_enviar_bloqueado_nao_dispara(self):
        r = self.client.post(self.url('enviar'), {'texto': 'a' * 500}, follow=True)
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


# ---------------------------------------------------------------------------
# Imagens e edição de posts publicados
# ---------------------------------------------------------------------------
import io
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from PIL import Image

MEDIA_TESTE = tempfile.mkdtemp(prefix='redator-media-')


def _foto(nome='foto.jpg', formato='JPEG'):
    buf = io.BytesIO()
    Image.new('RGB', (40, 30), (120, 60, 200)).save(buf, formato)
    return SimpleUploadedFile(nome, buf.getvalue(), content_type='image/jpeg')


@override_settings(**CONFIG, MEDIA_ROOT=MEDIA_TESTE)
class ImagemEEdicaoTests(TestCase):
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TESTE, ignore_errors=True)

    def setUp(self):
        self.user = get_user_model().objects.create_superuser('dona', 'dona@example.com', 'x')
        self.client.force_login(self.user)

    def _responder(self, resposta):
        pk = agente.proxima_pendente()
        with mock.patch.object(agente, 'chamar_opencode', return_value=(resposta, 1, 1)):
            agente.responder(pk)

    def test_imagem_sozinha_nao_chama_o_modelo_nem_gasta_cota(self):
        conversa = Conversa.objects.create()
        url = reverse('admin:redator_conversa_enviar', args=[conversa.pk])
        self.client.post(url, {'texto': '', 'imagem': _foto()})
        self.assertIsNone(agente.proxima_pendente())
        self.assertEqual(agente.restantes_na_conversa(conversa), 3)
        self.assertTrue(conversa.mensagens.filter(autor=Mensagem.DONA).exclude(imagem='').exists())

    def test_imagem_antes_do_rascunho_vira_destaque_quando_ele_nasce(self):
        conversa = Conversa.objects.create()
        agente.enviar(conversa, '', imagem=_foto())
        agente.enviar(conversa, 'Post sobre O Sol')
        self._responder(RESPOSTA_COM_POST)
        conversa.refresh_from_db()
        self.assertTrue(conversa.post.imagem_destaque.name.startswith('redator/'))

    def test_imagem_com_rascunho_ja_existente(self):
        conversa = Conversa.objects.create()
        agente.enviar(conversa, 'Post sobre O Sol')
        self._responder(RESPOSTA_COM_POST)
        conversa.refresh_from_db()
        agente.enviar(conversa, 'Use esta foto', imagem=_foto())
        conversa.post.refresh_from_db()
        self.assertTrue(conversa.post.imagem_destaque)
        self.assertIn('imagem, que já virou', agente.montar_prompt(conversa))

    def test_arquivo_que_nao_e_imagem_e_recusado(self):
        conversa = Conversa.objects.create()
        url = reverse('admin:redator_conversa_enviar', args=[conversa.pk])
        falso = SimpleUploadedFile('x.jpg', b'nao sou imagem', content_type='image/jpeg')
        r = self.client.post(url, {'texto': 'oi', 'imagem': falso}, follow=True)
        self.assertFalse(Mensagem.objects.exists())
        self.assertTrue(any('imagem' in str(m).lower() for m in r.context['messages']))

    def _publicado(self):
        return Post.objects.create(titulo='A Lua no Tarô', subtitulo='Antigo', conteudo='Texto antigo',
                                   status='publicado')

    def test_editar_publicado_nao_muda_o_post_antes_de_aprovar(self):
        post = self._publicado()
        r = self.client.get(reverse('admin:redator_conversa_editar_post', args=[post.pk]))
        conversa = Conversa.objects.get(post=post)
        self.assertRedirects(r, reverse('admin:redator_conversa_chat', args=[conversa.pk]))
        agente.enviar(conversa, 'Mude o título')
        self._responder(RESPOSTA_COM_POST)
        agente.enviar(conversa, '', imagem=_foto())
        post.refresh_from_db()
        conversa.refresh_from_db()
        self.assertEqual(post.titulo, 'A Lua no Tarô')
        self.assertFalse(post.imagem_destaque)
        self.assertEqual(Post.objects.count(), 1)
        self.assertEqual(conversa.proposta['titulo'], 'O Sol no Tarô')
        self.assertTrue(conversa.proposta['imagem'])
        self.assertIn('JÁ PUBLICADO', agente.montar_prompt(conversa))
        pagina = self.client.get(reverse('admin:redator_conversa_chat', args=[conversa.pk]))
        self.assertContains(pagina, 'Aprovar alterações')
        self.assertNotContains(pagina, 'Aprovar e publicar agora')

    def test_aprovar_alteracoes_atualiza_post_no_ar(self):
        post = self._publicado()
        data = post.data_publicacao
        conversa = agente.iniciar_edicao(post)
        agente.enviar(conversa, 'Mude o título', imagem=_foto())
        self._responder(RESPOSTA_COM_POST)
        self.client.post(reverse('admin:redator_conversa_aprovar_alteracoes', args=[conversa.pk]))
        post.refresh_from_db()
        conversa.refresh_from_db()
        self.assertEqual(post.titulo, 'O Sol no Tarô')
        self.assertEqual(post.status, 'publicado')
        self.assertEqual(post.data_publicacao, data)
        self.assertTrue(post.imagem_destaque)
        self.assertIsNone(conversa.proposta)
        self.assertTrue(conversa.encerrada)

    def test_descartar_alteracoes(self):
        post = self._publicado()
        conversa = agente.iniciar_edicao(post)
        agente.enviar(conversa, 'Mude o título')
        self._responder(RESPOSTA_COM_POST)
        self.client.post(reverse('admin:redator_conversa_descartar_alteracoes', args=[conversa.pk]))
        post.refresh_from_db()
        conversa.refresh_from_db()
        self.assertEqual(post.titulo, 'A Lua no Tarô')
        self.assertIsNone(conversa.proposta)
        self.assertFalse(conversa.encerrada)

    def test_editar_rascunho_existente_altera_direto(self):
        post = Post.objects.create(titulo='Rascunho velho', conteudo='x', status='rascunho')
        conversa = agente.iniciar_edicao(post)
        agente.enviar(conversa, 'Reescreva')
        self._responder(RESPOSTA_COM_POST)
        post.refresh_from_db()
        self.assertEqual(post.titulo, 'O Sol no Tarô')
        self.assertEqual(post.status, 'rascunho')

    def test_botao_editar_com_o_agente_no_post(self):
        post = self._publicado()
        r = self.client.get(reverse('admin:core_post_change', args=[post.pk]))
        self.assertContains(r, reverse('admin:redator_conversa_editar_post', args=[post.pk]))
