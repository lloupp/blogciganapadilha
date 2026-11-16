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
