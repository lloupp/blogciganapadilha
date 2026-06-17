from django.contrib import admin
from .models import Post, Categoria, Tag


@admin.register(Categoria)
class CategoriaAdmin(admin.ModelAdmin):
    list_display = ['icone', 'nome', 'slug', 'ordem', 'ativo']
    list_editable = ['ordem', 'ativo']
    prepopulated_fields = {'slug': ('nome',)}
    search_fields = ['nome', 'descricao']
    list_filter = ['ativo']


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ['nome', 'slug']
    prepopulated_fields = {'slug': ('nome',)}
    search_fields = ['nome']


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ['titulo', 'categoria', 'status', 'destaque', 'data_publicacao', 'visualizacoes']
    list_filter = ['status', 'categoria', 'tags', 'destaque', 'data_publicacao']
    list_editable = ['status', 'destaque']
    search_fields = ['titulo', 'subtitulo', 'conteudo']
    prepopulated_fields = {'slug': ('titulo',)}
    date_hierarchy = 'data_publicacao'
    ordering = ['-data_publicacao', '-data_criacao']
    readonly_fields = ['data_criacao', 'data_atualizacao', 'visualizacoes']
    filter_horizontal = ['tags']

    fieldsets = (
        ('Conteúdo Principal', {
            'fields': ('titulo', 'slug', 'subtitulo', 'conteudo', 'imagem_destaque')
        }),
        ('Organização', {
            'fields': ('categoria', 'tags')
        }),
        ('Publicação', {
            'fields': ('status', 'destaque', 'data_publicacao', 'tempo_leitura')
        }),
        ('Estatísticas (somente leitura)', {
            'fields': ('visualizacoes', 'data_criacao', 'data_atualizacao'),
            'classes': ('collapse',)
        }),
    )

    def save_model(self, request, obj, form, change):
        if obj.status == 'publicado' and not obj.data_publicacao:
            from django.utils import timezone
            obj.data_publicacao = timezone.now()
        super().save_model(request, obj, form, change)