"""Filtro `emoji`: envolve emojis em <span class="emoji">.

Títulos com gradiente (background-clip: text + text-fill transparente)
transformam emojis em silhuetas da cor do gradiente. O span recebe a cor
normal via CSS (.emoji em style.css).

O texto é escapado antes; só o <span> é HTML confiável.
"""
import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()

# Pictogramas + seletor de variação / ZWJ / tons de pele que os acompanham.
_EMOJI = re.compile(
    '(?:[\U0001F300-\U0001FAFF☀-➿⌀-⏿⬀-⯿\U0001F1E6-\U0001F1FF]'
    '[️‍\U0001F3FB-\U0001F3FF]*)+'
)


@register.filter(name='emoji')
def emoji(value):
    texto = conditional_escape(value)
    return mark_safe(_EMOJI.sub(lambda m: f'<span class="emoji">{m.group(0)}</span>', texto))
