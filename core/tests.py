from django.test import TestCase

# Create your tests here.


class EmojiFilterTests(TestCase):
    def test_envolve_emojis_e_escapa_html(self):
        from core.templatetags.emoji import emoji
        saida = emoji('🔮 Tarô <b>x</b> 🏷️')
        self.assertEqual(
            saida,
            '<span class="emoji">🔮</span> Tarô &lt;b&gt;x&lt;/b&gt; <span class="emoji">🏷️</span>',
        )

    def test_texto_sem_emoji_inalterado(self):
        from core.templatetags.emoji import emoji
        self.assertEqual(emoji('Tarô & Cia'), 'Tarô &amp; Cia')


from django.test import override_settings
from consultas.models import TipoConsulta


class SitemapConsultasTests(TestCase):
    def setUp(self):
        TipoConsulta.objects.create(nome='Cartas Ciganas', preco=50)
        TipoConsulta.objects.create(nome='Inativa', preco=10, ativo=False)

    @override_settings(CONSULTAS_ABERTAS=True)
    def test_consultas_no_sitemap_quando_abertas(self):
        xml = self.client.get('/sitemap.xml').content.decode()
        self.assertIn('/consultas/</loc>', xml)
        self.assertIn('/consultas/cartas-ciganas/', xml)
        self.assertNotIn('inativa', xml)

    @override_settings(CONSULTAS_ABERTAS=False)
    def test_consultas_fora_do_sitemap_quando_fechadas(self):
        xml = self.client.get('/sitemap.xml').content.decode()
        self.assertNotIn('/consultas/', xml)


class WwwRedirectTests(TestCase):
    def test_www_redireciona_301_preservando_path_e_query(self):
        resp = self.client.get(
            '/blog/foo/?utm=x&page=2',
            HTTP_HOST='www.blogciganapadilha.com.br',
        )
        self.assertEqual(resp.status_code, 301)
        self.assertEqual(
            resp['Location'],
            'https://blogciganapadilha.com.br/blog/foo/?utm=x&page=2',
        )

    def test_host_nu_nao_redireciona(self):
        resp = self.client.get('/', HTTP_HOST='blogciganapadilha.com.br')
        self.assertNotEqual(resp.status_code, 301)

    def test_localhost_nao_redireciona(self):
        for host in ('localhost', '127.0.0.1'):
            resp = self.client.get('/', HTTP_HOST=host)
            self.assertNotEqual(resp.status_code, 301)


class CanonicalTests(TestCase):
    def test_home_tem_canonical_autorreferente_nao_www(self):
        resp = self.client.get('/')
        self.assertEqual(resp.status_code, 200)
        self.assertContains(
            resp,
            '<link rel="canonical" href="https://blogciganapadilha.com.br/">',
        )


class SitemapRobotsHostTests(TestCase):
    """Views fixas em SITE_URL: testadas direto via RequestFactory para
    não passarem pelo middleware de redirect www→não-www."""

    def setUp(self):
        from django.test import RequestFactory
        self.factory = RequestFactory(HTTP_HOST='www.blogciganapadilha.com.br')

    def test_sitemap_so_urls_nao_www_mesmo_com_host_www(self):
        from core.views import sitemap_xml
        resp = sitemap_xml(self.factory.get('/sitemap.xml'))
        xml = resp.content.decode()
        self.assertIn('https://blogciganapadilha.com.br/', xml)
        self.assertNotIn('www.blogciganapadilha.com.br', xml)

    def test_robots_aponta_sitemap_nao_www(self):
        from core.views import robots_txt
        resp = robots_txt(self.factory.get('/robots.txt'))
        texto = resp.content.decode()
        self.assertIn('Sitemap: https://blogciganapadilha.com.br/sitemap.xml', texto)
        self.assertNotIn('www.blogciganapadilha.com.br', texto)
