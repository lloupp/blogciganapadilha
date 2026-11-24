import re

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse
from django.utils.text import slugify
from django.utils import timezone


class Categoria(models.Model):
    nome = models.CharField('Nome', max_length=100, unique=True)
    slug = models.SlugField('Slug', max_length=100, unique=True, blank=True)
    descricao = models.TextField('Descrição', blank=True)
    icone = models.CharField('Ícone (emoji)', max_length=10, default='🔮')
    ordem = models.PositiveIntegerField('Ordem', default=0)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Categoria'
        verbose_name_plural = 'Categorias'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return f'{self.icone} {self.nome}'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('core:categoria_detail', kwargs={'slug': self.slug})


class Tag(models.Model):
    nome = models.CharField('Nome', max_length=50, unique=True)
    slug = models.SlugField('Slug', max_length=50, unique=True, blank=True)

    class Meta:
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().save(*args, **kwargs)


class PostQuerySet(models.QuerySet):
    def publicados(self):
        """Visíveis ao público: publicados e com data já chegada (agendados ficam de fora)."""
        return self.filter(status='publicado', data_publicacao__lte=timezone.now())


class Post(models.Model):
    STATUS_CHOICES = [
        ('rascunho', 'Rascunho'),
        ('publicado', 'Publicado'),
    ]

    titulo = models.CharField('Título', max_length=200)
    slug = models.SlugField('Slug', max_length=220, unique=True, blank=True)
    subtitulo = models.CharField('Subtítulo', max_length=300, blank=True)
    conteudo = models.TextField('Conteúdo')
    imagem_destaque = models.ImageField(
        'Imagem de destaque',
        upload_to='posts/%Y/%m/',
        blank=True,
        null=True
    )
    categoria = models.ForeignKey(
        Categoria,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='posts',
        verbose_name='Categoria'
    )
    tags = models.ManyToManyField(Tag, blank=True, verbose_name='Tags')
    status = models.CharField('Status', max_length=10, choices=STATUS_CHOICES, default='rascunho')
    destaque = models.BooleanField('Destaque na home', default=False)
    data_criacao = models.DateTimeField('Criado em', auto_now_add=True)
    data_atualizacao = models.DateTimeField('Atualizado em', auto_now=True)
    data_publicacao = models.DateTimeField('Publicado em', null=True, blank=True)
    tempo_leitura = models.PositiveIntegerField('Tempo de leitura (min)', default=5)
    visualizacoes = models.PositiveIntegerField('Visualizações', default=0)

    objects = PostQuerySet.as_manager()

    class Meta:
        verbose_name = 'Post'
        verbose_name_plural = 'Posts'
        ordering = ['-data_publicacao', '-data_criacao']
        indexes = [
            models.Index(fields=['-data_publicacao', 'status']),
            models.Index(fields=['slug']),
        ]

    def __str__(self):
        return self.titulo

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.titulo)
            self.slug = base_slug
            counter = 1
            while Post.objects.filter(slug=self.slug).exclude(pk=self.pk).exists():
                self.slug = f'{base_slug}-{counter}'
                counter += 1

        if self.status == 'publicado' and not self.data_publicacao:
            self.data_publicacao = timezone.now()
        elif self.status == 'rascunho':
            self.data_publicacao = None

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('core:post_detail', kwargs={'slug': self.slug})

    @property
    def esta_agendado(self):
        return self.status == 'publicado' and self.data_publicacao and self.data_publicacao > timezone.now()

    @property
    def esta_publicado(self):
        return self.status == 'publicado' and self.data_publicacao and self.data_publicacao <= timezone.now()

    def incrementar_visualizacoes(self):
        self.visualizacoes += 1
        self.save(update_fields=['visualizacoes'])

YOUTUBE_RE = re.compile(
    r'(?:youtube(?:-nocookie)?\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)|youtu\.be/)([A-Za-z0-9_-]{11})'
)
INSTAGRAM_RE = re.compile(
    r'instagram\.com/(?:[A-Za-z0-9_.]+/)?(p|reels?|tv)/([A-Za-z0-9_-]+)'
)


def identificar_video(url):
    """Devolve (plataforma, id, tipo) para uma URL do YouTube ou Instagram, ou None."""
    url = (url or '').strip()
    m = YOUTUBE_RE.search(url)
    if m:
        return ('youtube', m.group(1), None)
    m = INSTAGRAM_RE.search(url)
    if m:
        tipo = 'p' if m.group(1) == 'p' else 'reel' if m.group(1).startswith('reel') else 'tv'
        return ('instagram', m.group(2), tipo)
    return None


class Video(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name='videos', verbose_name='Post')
    url = models.URLField(
        'Link do vídeo',
        max_length=500,
        help_text='Link do YouTube (vídeo, Shorts ou live) ou do Instagram (Reel ou post). '
                  'No Instagram, a conta precisa ser pública.'
    )
    legenda = models.CharField('Legenda (opcional)', max_length=200, blank=True)
    ordem = models.PositiveIntegerField('Ordem', default=0)

    class Meta:
        verbose_name = 'Vídeo'
        verbose_name_plural = 'Vídeos'
        ordering = ['ordem', 'id']

    def __str__(self):
        return self.legenda or self.url

    def clean(self):
        if self.url and not identificar_video(self.url):
            raise ValidationError({'url': 'Link não reconhecido. Use um link do YouTube ou do Instagram.'})

    @property
    def plataforma(self):
        info = identificar_video(self.url)
        return info[0] if info else None

    @property
    def embed_url(self):
        info = identificar_video(self.url)
        if not info:
            return None
        plataforma, vid, tipo = info
        if plataforma == 'youtube':
            return f'https://www.youtube.com/embed/{vid}'
        return f'https://www.instagram.com/{tipo}/{vid}/embed/'
