from django.core.management.base import BaseCommand
from core.models import Categoria, Tag
from django.contrib.auth import get_user_model


class Command(BaseCommand):
    help = 'Cria dados iniciais do blog'

    def handle(self, *args, **options):
        User = get_user_model()
        if not User.objects.filter(is_superuser=True).exists():
            User.objects.create_superuser('admin', 'admin@blogdamaee.com', 'admin123')
            self.stdout.write(self.style.SUCCESS('Superusuário criado: admin / admin123'))

        categorias = [
            {'nome': 'Tarô', 'icone': '🃏', 'descricao': 'Significados das cartas, tiragens e interpretações para todos os níveis.'},
            {'nome': 'Astrologia', 'icone': '⭐', 'descricao': 'Mapa astral, trânsitos, signos e influências dos astros.'},
            {'nome': 'Rituais', 'icone': '🕯️', 'descricao': 'Rituais de prosperidade, amor, proteção e limpeza energética.'},
            {'nome': 'Cristais', 'icone': '💎', 'descricao': 'Propriedades dos cristais, como usar e combinar para cada intenção.'},
            {'nome': 'Meditação', 'icone': '🧘', 'descricao': 'Técnicas de meditação, mindfulness e conexão espiritual.'},
            {'nome': 'Lua & Energia', 'icone': '🌙', 'descricao': 'Fases da lua, energias do dia e ciclos naturais.'},
            {'nome': 'Sonhos', 'icone': '💭', 'descricao': 'Interpretação dos sonhos e mensagens do inconsciente.'},
        ]

        for cat_data in categorias:
            Categoria.objects.get_or_create(nome=cat_data['nome'], defaults=cat_data)
            self.stdout.write(f'  ✓ Categoria: {cat_data["icone"]} {cat_data["nome"]}')

        tags = ['Tarô', 'Astrologia', 'Cristais', 'Rituais', 'Meditação', 'Lua Nova', 'Lua Cheia', 'Amor', 'Prosperidade', 'Proteção']
        for tag_name in tags:
            Tag.objects.get_or_create(nome=tag_name)
            self.stdout.write(f'  ✓ Tag: {tag_name}')

        self.stdout.write(self.style.SUCCESS('\n✨ Blog pronto para usar!'))