import uuid
from datetime import timedelta

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.urls import reverse
from django.utils.text import slugify


class TipoConsulta(models.Model):
    nome = models.CharField('Nome', max_length=100)
    slug = models.SlugField('Slug', max_length=120, unique=True, blank=True)
    descricao = models.TextField('Descrição', blank=True)
    preco = models.DecimalField('Preço (R$)', max_digits=8, decimal_places=2)
    duracao_minutos = models.PositiveIntegerField('Duração (min)', default=30)
    icone = models.CharField('Ícone (emoji)', max_length=10, default='🔮',
                             help_text='Aparece quando não há imagem.')
    imagem = models.ImageField('Imagem', upload_to='consultas/', blank=True,
                               help_text='Opcional. Aparece no topo do cartão no lugar do emoji.')
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
    pagamento_divergente = models.BooleanField('Pagamento com valor divergente', default=False)
    mp_preference_id = models.CharField('ID da preferência (Mercado Pago)', max_length=100, blank=True)
    mp_payment_id = models.CharField('ID do pagamento (Mercado Pago)', max_length=100, blank=True)
    # Pix direto na página (API de Orders do Mercado Pago)
    mp_order_id = models.CharField('ID do pedido (Mercado Pago)', max_length=100, blank=True)
    pix_copia_cola = models.TextField('Pix copia e cola', blank=True)
    pix_qr_base64 = models.TextField('QR Code do Pix (base64)', blank=True)
    pix_expira_em = models.DateTimeField('Pix vence em', null=True, blank=True)
    criado_em = models.DateTimeField('Criado em', auto_now_add=True)
    atualizado_em = models.DateTimeField('Atualizado em', auto_now=True)

    class Meta:
        verbose_name = 'Consulta'
        verbose_name_plural = 'Consultas'
        ordering = ['-criado_em']

    def __str__(self):
        return f'{self.nome_cliente} — {self.tipo_consulta.nome} ({self.get_status_display()})'

    def pode_transicionar(self, novo_status):
        """Uma consulta aprovada só pode ser cancelada (refund/chargeback).

        Evita que uma notificação atrasada do Mercado Pago rebaixe uma
        consulta já paga para pendente/rejeitado.
        """
        if novo_status not in dict(self.STATUS_CHOICES):
            return False
        if self.status == 'aprovado':
            return novo_status in ('aprovado', 'cancelado')
        return True

    def get_status_url(self):
        return reverse('consultas:status', kwargs={'referencia': self.referencia})


# ============================================================
# Chat de consultas
# ============================================================

class Atendente(models.Model):
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='atendente',
        verbose_name='Usuário (login do painel)',
    )
    nome = models.CharField('Nome', max_length=100)
    bio = models.TextField('Apresentação', blank=True)
    foto = models.ImageField('Foto', upload_to='atendentes/', blank=True)
    online = models.BooleanField('Online', default=False)
    ativo = models.BooleanField('Ativo', default=True)
    criado_em = models.DateTimeField('Criado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Atendente'
        verbose_name_plural = 'Atendentes'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    @classmethod
    def padrao(cls):
        """Primeira atendente ativa (online primeiro)."""
        return cls.objects.filter(ativo=True).order_by('-online', 'pk').first()


class Conversa(models.Model):
    STATUS_AGUARDANDO = 'aguardando'
    STATUS_ATIVA = 'ativa'
    STATUS_ENCERRADA = 'encerrada'
    STATUS_EXPIRADA = 'expirada'
    STATUS_CHOICES = [
        (STATUS_AGUARDANDO, 'Aguardando atendente'),
        (STATUS_ATIVA, 'Em atendimento'),
        (STATUS_ENCERRADA, 'Encerrada'),
        (STATUS_EXPIRADA, 'Tempo esgotado'),
    ]

    consulta = models.OneToOneField(
        Consulta,
        on_delete=models.CASCADE,
        related_name='conversa',
        verbose_name='Consulta',
    )
    atendente = models.ForeignKey(
        Atendente,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='conversas',
        verbose_name='Atendente',
    )
    status = models.CharField('Status', max_length=12, choices=STATUS_CHOICES, default=STATUS_AGUARDANDO)
    iniciada_em = models.DateTimeField('Iniciada em', null=True, blank=True)
    segundos_concedidos = models.PositiveIntegerField('Tempo concedido (s)', default=0)
    encerrada_em = models.DateTimeField('Encerrada em', null=True, blank=True)
    criada_em = models.DateTimeField('Criada em', auto_now_add=True)
    atualizada_em = models.DateTimeField('Atualizada em', auto_now=True)

    class Meta:
        verbose_name = 'Conversa'
        verbose_name_plural = 'Conversas'
        ordering = ['-atualizada_em']

    def __str__(self):
        return f'Conversa #{self.pk} — {self.consulta.nome_cliente} ({self.get_status_display()})'

    # --- tempo -------------------------------------------------------

    @property
    def expira_em(self):
        if not self.iniciada_em:
            return None
        return self.iniciada_em + timedelta(seconds=self.segundos_concedidos)

    @property
    def segundos_restantes(self):
        if self.status == self.STATUS_AGUARDANDO:
            return self.consulta.tipo_consulta.duracao_minutos * 60
        if self.status != self.STATUS_ATIVA or self.expira_em is None:
            return 0
        return max(0, int((self.expira_em - timezone.now()).total_seconds()))

    @property
    def tempo_restante_display(self):
        m, s = divmod(self.segundos_restantes, 60)
        h, m = divmod(m, 60)
        return f'{h}:{m:02d}:{s:02d}' if h else f'{m:02d}:{s:02d}'

    @property
    def pode_receber_mensagem(self):
        if self.consulta.status != 'aprovado':
            return False
        if self.status == self.STATUS_AGUARDANDO:
            return True
        return self.status == self.STATUS_ATIVA and self.segundos_restantes > 0

    # --- transições --------------------------------------------------

    def _mensagem_sistema(self, texto):
        return self.mensagens.create(autor=Mensagem.AUTOR_SISTEMA, texto=texto, lida=True)

    def iniciar(self, atendente=None):
        if self.status != self.STATUS_AGUARDANDO:
            return False
        self.atendente = atendente or self.atendente or Atendente.padrao()
        self.status = self.STATUS_ATIVA
        self.iniciada_em = timezone.now()
        self.segundos_concedidos = self.consulta.tipo_consulta.duracao_minutos * 60
        self.save(update_fields=['atendente', 'status', 'iniciada_em', 'segundos_concedidos', 'atualizada_em'])
        minutos = self.segundos_concedidos // 60
        self._mensagem_sistema(f'Atendimento iniciado. Você tem {minutos} minutos.')
        return True

    def estender(self, minutos):
        """Soma tempo. Se a conversa já expirou, reabre por `minutos`.

        Conversa encerrada manualmente ou ainda aguardando não é estendida.
        """
        minutos = int(minutos)
        if minutos <= 0:
            return False
        self.expirar_se_preciso()
        if self.status == self.STATUS_ATIVA:
            self.segundos_concedidos += minutos * 60
        elif self.status == self.STATUS_EXPIRADA:
            # Reabre a partir de agora: o tempo concedido passa a cobrir
            # o que já foi usado + os minutos novos.
            usados = int((timezone.now() - self.iniciada_em).total_seconds())
            self.segundos_concedidos = usados + minutos * 60
            self.status = self.STATUS_ATIVA
        else:
            return False
        self.save(update_fields=['status', 'segundos_concedidos', 'atualizada_em'])
        self._mensagem_sistema(f'Tempo estendido em {minutos} minutos.')
        return True

    def expirar_se_preciso(self):
        if self.status != self.STATUS_ATIVA or self.expira_em is None:
            return False
        if timezone.now() < self.expira_em:
            return False
        self.status = self.STATUS_EXPIRADA
        self.encerrada_em = self.expira_em
        self.save(update_fields=['status', 'encerrada_em', 'atualizada_em'])
        self._mensagem_sistema('Tempo da consulta encerrado.')
        return True

    def encerrar(self):
        if self.status in (self.STATUS_ENCERRADA, self.STATUS_EXPIRADA):
            return False
        self.status = self.STATUS_ENCERRADA
        self.encerrada_em = timezone.now()
        self.save(update_fields=['status', 'encerrada_em', 'atualizada_em'])
        self._mensagem_sistema('Atendimento encerrado.')
        return True


class Mensagem(models.Model):
    AUTOR_CLIENTE = 'cliente'
    AUTOR_ATENDENTE = 'atendente'
    AUTOR_SISTEMA = 'sistema'
    AUTOR_CHOICES = [
        (AUTOR_CLIENTE, 'Cliente'),
        (AUTOR_ATENDENTE, 'Atendente'),
        (AUTOR_SISTEMA, 'Sistema'),
    ]
    TAMANHO_MAXIMO = 2000

    conversa = models.ForeignKey(
        Conversa,
        on_delete=models.CASCADE,
        related_name='mensagens',
        verbose_name='Conversa',
    )
    autor = models.CharField('Autor', max_length=10, choices=AUTOR_CHOICES)
    texto = models.TextField('Texto', max_length=TAMANHO_MAXIMO)
    lida = models.BooleanField('Lida', default=False)
    criada_em = models.DateTimeField('Enviada em', auto_now_add=True)

    class Meta:
        verbose_name = 'Mensagem'
        verbose_name_plural = 'Mensagens'
        ordering = ['id']
        indexes = [
            models.Index(fields=['conversa', 'id'], name='msg_conversa_id_idx'),
            models.Index(fields=['conversa', 'lida'], name='msg_conversa_lida_idx'),
        ]

    def __str__(self):
        return f'[{self.get_autor_display()}] {self.texto[:50]}'
