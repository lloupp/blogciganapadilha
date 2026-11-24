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
