# 🔮 Blog da Mãe — Tarô & Esoterismo

Blog místico com tema de tarô e esoterismo feito em Django 4.2.
Sua mãe pode criar e gerenciar postagens pelo painel admin.

## 📦 Requisitos

- Python 3.10+
- pip / venv

## 🚀 Como Rodar

```bash
# 1. Ativar ambiente virtual
source venv/bin/activate

# 2. Rodar o servidor
python manage.py runserver 0.0.0.0:8000

# Ou use o script
./run.sh
```

Acessar: http://localhost:8000
Admin: http://localhost:8000/admin/

## 👤 Login Admin

> **Usuário:** `admin`
> **Senha:** `admin123`

*⚠️ Mude a senha no primeiro acesso!*

## 📝 Como Usar

1. Faça login no **Admin** (link no canto superior direito do blog)
2. Clique em **"Posts" → "Adicionar Post"**
3. Preencha:
   - **Título** — o nome do artigo
   - **Conteúdo** — o texto (use Enter para parágrafos)
   - **Categoria** — Tarô, Astrologia, Rituais, etc.
   - **Imagem de destaque** — opcional, mas recomendado
   - **Status** → selecione **"Publicado"** para aparecer no site
4. Clique em **"Salvar"** — pronto! O post aparece na home.

## 📂 Estrutura

```
blog_mae/
├── core/              # App principal (models, views, admin)
├── templates/         # Templates HTML
├── static/            # CSS, JS
├── media/             # Imagens enviadas
├── db.sqlite3         # Banco de dados
├── manage.py
└── requirements.txt
```

## ⚙️ Personalização

- **Categorias**: Admin → Categorias (adicione/edite)
- **Tags**: Admin → Tags
- **Imagens**: Envie junto com o post ou direto em Media
- **CSS**: Edite `static/css/style.css` pra mudar cores/tema

## 🌐 Deploy (para colocar online)

Quando quiser subir pra internet, crio um guia de deploy no Railway, Render, ou um VPS. É simples. Só avisar!

---

Feito com 💜 para a mamãe ✨