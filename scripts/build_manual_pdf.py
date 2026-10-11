#!/usr/bin/env python3
"""Gera os PDFs do manual do painel administrativo a partir dos arquivos .md.

Uso (a partir da raiz do projeto):

    ./venv/bin/python scripts/build_manual_pdf.py

Converte MANUAL_COM_IMAGENS.md e MANUAL_SEM_IMAGENS.md em PDF usando o
markdown-it-py (já instalado no venv) para gerar o HTML e o Google Chrome em
modo headless para imprimir. Não precisa de nenhuma dependência extra.
"""
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from markdown_it import MarkdownIt

RAIZ = Path(__file__).resolve().parent.parent
MANUAIS = ['MANUAL_COM_IMAGENS.md', 'MANUAL_SEM_IMAGENS.md']

CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body {
  font-family: "DejaVu Sans", "Noto Sans", Arial, sans-serif;
  font-size: 12pt; line-height: 1.6; color: #222; margin: 0;
}
h1 { font-size: 26pt; color: #3f6f89; margin: 0 0 .2em; }
h2 {
  font-size: 19pt; color: #3f6f89; margin: 1.4em 0 .5em;
  border-bottom: 2px solid #a8cadd; padding-bottom: .2em;
  page-break-after: avoid;
}
h3 { font-size: 14.5pt; color: #2f5568; margin: 1.2em 0 .4em; page-break-after: avoid; }
p, li { orphans: 2; widows: 2; }
ul, ol { padding-left: 1.4em; }
li { margin: .3em 0; }
code {
  background: #f2f4f6; padding: .1em .35em; border-radius: 3px;
  font-family: "DejaVu Sans Mono", monospace; font-size: .9em;
}
blockquote {
  margin: 1em 0; padding: .7em 1em; background: #f7f9fb;
  border-left: 4px solid #7fb0c9; border-radius: 0 4px 4px 0;
  page-break-inside: avoid;
}
blockquote p { margin: .3em 0; }
img {
  max-width: 100%; height: auto; display: block; margin: 1em auto;
  border: 1px solid #d5dde3; border-radius: 4px; page-break-inside: avoid;
}
hr { border: 0; border-top: 1px solid #d5dde3; margin: 1.8em 0; }
a { color: #2f6f8f; text-decoration: none; }
/* cada secao numerada comeca em pagina nova */
h2.nova-pagina { page-break-before: always; }
"""

MOLDE = """<!doctype html>
<html lang="pt-br"><head><meta charset="utf-8"><title>{titulo}</title>
<style>{css}</style></head><body>{corpo}</body></html>
"""


def achar_chrome():
    for nome in ('google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser'):
        caminho = shutil.which(nome)
        if caminho:
            return caminho
    sys.exit('Nenhum Chrome/Chromium encontrado no sistema — não dá para gerar o PDF.')


def markdown_para_html(md_path: Path) -> str:
    md = MarkdownIt('commonmark').enable(['table', 'strikethrough'])
    corpo = md.render(md_path.read_text(encoding='utf-8'))

    # imagens com caminho relativo viram file:// absoluto, para o Chrome achá-las
    def absolutizar(m):
        src = m.group(1)
        if src.startswith(('http://', 'https://', 'data:', 'file://')):
            return m.group(0)
        return 'src="file://{}"'.format((RAIZ / src).resolve())

    corpo = re.sub(r'src="([^"]+)"', absolutizar, corpo)

    # quebra de pagina antes de cada secao numerada (menos a primeira)
    partes = corpo.split('<h2>')
    if len(partes) > 2:
        corpo = partes[0] + '<h2>' + partes[1] + ''.join(
            '<h2 class="nova-pagina">' + p for p in partes[2:]
        )
    return corpo


def gerar_pdf(md_path: Path, chrome: str) -> Path:
    pdf_path = md_path.with_suffix('.pdf')
    html = MOLDE.format(titulo=md_path.stem, css=CSS, corpo=markdown_para_html(md_path))

    with tempfile.TemporaryDirectory() as tmp:
        perfil = Path(tmp) / 'perfil'
        html_path = RAIZ / f'.{md_path.stem}.tmp.html'
        html_path.write_text(html, encoding='utf-8')
        try:
            subprocess.run(
                [chrome, '--headless=new', '--no-sandbox', '--disable-gpu',
                 f'--user-data-dir={perfil}', '--no-pdf-header-footer',
                 '--virtual-time-budget=20000',
                 f'--print-to-pdf={pdf_path}', f'file://{html_path}'],
                check=True, capture_output=True, timeout=180,
            )
        finally:
            html_path.unlink(missing_ok=True)
    return pdf_path


def main():
    chrome = achar_chrome()
    for nome in MANUAIS:
        md_path = RAIZ / nome
        if not md_path.exists():
            sys.exit(f'Arquivo não encontrado: {md_path}')
        pdf = gerar_pdf(md_path, chrome)
        print(f'  ✓ {pdf.name} ({pdf.stat().st_size / 1024:.0f} KB)')


if __name__ == '__main__':
    main()
