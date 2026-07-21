import uuid

from django.db import models
from django.urls import reverse
from django.utils.text import slugify


class TipoConsulta(models.Model):
    nome = models.CharField('Nome', max_length=100)
    slug = models.SlugField('Slug', max_length=120, unique=True, blank=True)
    descricao = models.TextField('Descrição', blank=True)
    preco = models.DecimalField('Preço (R$)', max_digits=8, decimal_places=2)
    duracao_minutos = models.PositiveIntegerField('Duração (min)', default=30)
    icone = models.CharField('Ícone (emoji)', max_length=10, default='🔮')
    ativo = models.BooleanField('Ativo', default=True)
    ordem = models.PositiveIntegerField('Ordem', default=0)

    class Meta:
        verbose_name = 'Tipo de Consulta'
        verbose_name_plural = 'Tipos de Consulta'
        ordering = ['ordem', 'nome']

    def __str__(self):
        return f'{self.icone} {self.nome} — R$ {self.preco}'

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.nome)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse('consultas:solicitar', kwargs={'slug': self.slug})


class Consulta(models.Model):
    STATUS_CHOICES = [
        ('pendente', 'Aguardando pagamento'),
        ('aprovado', 'Pago'),
        ('rejeitado', 'Recusado'),
        ('cancelado', 'Cancelado'),
    ]

    referencia = models.UUIDField('Referência', default=uuid.uuid4, editable=False, unique=True)
    tipo_consulta = models.ForeignKey(
        TipoConsulta,
        on_delete=models.PROTECT,
        related_name='consultas',
        verbose_name='Tipo de consulta',
    )
    nome_cliente = models.CharField('Nome', max_length=150)
    email_cliente = models.EmailField('E-mail')
    whatsapp_cliente = models.CharField('WhatsApp', max_length=30)
    valor = models.DecimalField('Valor (R$)', max_digits=8, decimal_places=2)
    status = models.CharField('Status', max_length=10, choices=STATUS_CHOICES, default='pendente')
    mp_preference_id = models.CharField('ID da preferência (Mercado Pago)', max_length=100, blank=True)
    mp_payment_id = models.CharField('ID do pagamento (Mercado Pago)', max_length=100, blank=True)
    criado_em = models.DateTimeField('Criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Consulta'
        verbose_name_plural = 'Consultas'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.nome_cliente} — {self.tipo_consulta.nome} ({self.get_status_display()})'
