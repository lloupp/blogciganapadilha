from django.conf import settings
from django.db import models
from django.utils import timezone


class Conversa(models.Model):
    """Uma conversa da dona com o agente, que resulta (ou não) em um post."""

    titulo = models.CharField('Assunto', max_length=200, blank=True)
    criada_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        verbose_name='Criada por',
    )
    post = models.ForeignKey(
        'core.Post', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='conversas_redator', verbose_name='Post criado',
    )
    encerrada = models.BooleanField('Encerrada', default=False)
    motivo_encerramento = models.CharField('Motivo do encerramento', max_length=200, blank=True)
    # Ao editar um post já publicado/agendado, a nova versão fica aqui até a
    # dona aprovar; o post no ar não muda antes disso.
    proposta = models.JSONField('Alterações propostas', null=True, blank=True)
    criada_em = models.DateTimeField('Criada em', auto_now_add=True)
    atualizada_em = models.DateTimeField('Atualizada em', auto_now=True)

    class Meta:
        verbose_name = 'Conversa com o agente'
        verbose_name_plural = 'Conversas com o agente'
        ordering = ['-atualizada_em']

    def __str__(self):
        return self.titulo or f'Conversa #{self.pk}'

    def encerrar(self, motivo):
        self.encerrada = True
        self.motivo_encerramento = motivo
        self.save(update_fields=['encerrada', 'motivo_encerramento', 'atualizada_em'])


class Mensagem(models.Model):
    DONA = 'dona'
    AGENTE = 'agente'
    SISTEMA = 'sistema'
    AUTORES = [(DONA, 'Dona do blog'), (AGENTE, 'Agente'), (SISTEMA, 'Aviso do sistema')]

    PRONTA = 'pronta'
    PENSANDO = 'pensando'
    ERRO = 'erro'
    ESTADOS = [(PRONTA, 'Pronta'), (PENSANDO, 'Pensando'), (ERRO, 'Erro')]

    conversa = models.ForeignKey(Conversa, on_delete=models.CASCADE, related_name='mensagens')
    autor = models.CharField(max_length=10, choices=AUTORES)
    texto = models.TextField(blank=True)
    imagem = models.ImageField('Imagem enviada', upload_to='redator/%Y/%m/', blank=True)
    estado = models.CharField(max_length=10, choices=ESTADOS, default=PRONTA)
    trouxe_rascunho = models.BooleanField('Trouxe rascunho do post', default=False)
    fora_do_assunto = models.BooleanField(default=False)
    tokens_entrada = models.PositiveIntegerField(default=0)
    tokens_saida = models.PositiveIntegerField(default=0)
    criada_em = models.DateTimeField(default=timezone.now)

    class Meta:
        verbose_name = 'Mensagem'
        verbose_name_plural = 'Mensagens'
        ordering = ['criada_em', 'pk']

    def __str__(self):
        return f'{self.get_autor_display()}: {self.texto[:60]}'


class Memoria(models.Model):
    """Fatos que o agente guarda entre conversas (preferências, assuntos já tratados)."""

    texto = models.CharField('Lembrança', max_length=500)
    ativa = models.BooleanField('Ativa', default=True,
                                help_text='Desmarque para o agente esquecer isto.')
    conversa = models.ForeignKey(Conversa, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name='memorias', verbose_name='Conversa de origem')
    criada_em = models.DateTimeField('Criada em', auto_now_add=True)

    class Meta:
        verbose_name = 'Memória do agente'
        verbose_name_plural = 'Memória do agente'
        ordering = ['-criada_em']

    def __str__(self):
        return self.texto
