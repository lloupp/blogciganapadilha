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
    video_url = models.URLField(
        'URL do YouTube',
        blank=True,
        help_text='Cole a URL completa do YouTube (ex: https://www.youtube.com/watch?v=XXXXX)'
    )
    tempo_leitura = models.PositiveIntegerField('Tempo de leitura (min)', default=5)
    visualizacoes = models.PositiveIntegerField('Visualizações', default=0)

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
    def video_id(self):
        """Extrai o video_id de URLs do YouTube."""
        if not self.video_url:
            return None
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(self.video_url)
        if 'youtu.be' in parsed.netloc:
            return parsed.path.strip('/')
        if 'youtube.com' in parsed.netloc:
            qs = parse_qs(parsed.query)
            return qs.get('v', [None])[0]
        return None

    @property
    def video_embed_url(self):
        """Retorna a URL de embed do YouTube."""
        vid = self.video_id
        return f'https://www.youtube.com/embed/{vid}' if vid else None

    @property
    def esta_publicado(self):
        return self.status == 'publicado' and self.data_publicacao and self.data_publicacao <= timezone.now()

    def incrementar_visualizacoes(self):
        self.visualizacoes += 1
        self.save(update_fields=['visualizacoes'])