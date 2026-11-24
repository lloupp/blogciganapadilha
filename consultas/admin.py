from django.contrib import admin, messages
from django.utils.html import format_html

from .models import Atendente, Consulta, Conversa, Mensagem, TipoConsulta


@admin.register(TipoConsulta)
class TipoConsultaAdmin(admin.ModelAdmin):
    list_display = ['miniatura', 'nome', 'preco', 'duracao_minutos', 'ativo', 'ordem']
    list_editable = ['ativo', 'ordem']
    prepopulated_fields = {'slug': ('nome',)}
    search_fields = ['nome', 'descricao']
    list_filter = ['ativo']
    readonly_fields = ['previa']
    fields = ['nome', 'slug', 'descricao', 'preco', 'duracao_minutos',
              'imagem', 'previa', 'icone', 'ativo', 'ordem']

    @admin.display(description='Imagem')
    def miniatura(self, obj):
        if obj.imagem:
            return format_html('<img src="{}" style="height:40px;width:60px;object-fit:cover;border-radius:6px">',
                               obj.imagem.url)
        return obj.icone

    @admin.display(description='Prévia da imagem')
    def previa(self, obj):
        if obj.imagem:
            return format_html('<img src="{}" style="max-width:320px;border-radius:10px">', obj.imagem.url)
        return 'Sem imagem: o cartão mostra o emoji.'


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = [
        'nome_cliente', 'tipo_consulta', 'valor', 'status', 'pagamento_divergente',
        'whatsapp_cliente', 'referencia', 'criado_em',
    ]
    list_filter = ['status', 'pagamento_divergente', 'tipo_consulta']
    search_fields = ['nome_cliente', 'email_cliente', 'whatsapp_cliente', 'referencia']
    date_hierarchy = 'criado_em'
    readonly_fields = [
        'referencia', 'tipo_consulta', 'nome_cliente', 'email_cliente', 'whatsapp_cliente',
        'valor', 'pagamento_divergente', 'mp_preference_id', 'mp_payment_id',
        'criado_em', 'atualizado_em',
    ]

    def has_add_permission(self, request):
        return False


# ============================================================
# Chat
# ============================================================

@admin.register(Atendente)
class AtendenteAdmin(admin.ModelAdmin):
    list_display = ['nome', 'online', 'ativo', 'usuario', 'criado_em']
    list_editable = ['online', 'ativo']
    list_filter = ['online', 'ativo']
    search_fields = ['nome', 'usuario__username']
    actions = ['ficar_online', 'ficar_offline']

    @admin.action(description='Ficar online')
    def ficar_online(self, request, queryset):
        n = queryset.update(online=True)
        self.message_user(request, f'{n} atendente(s) online.', messages.SUCCESS)

    @admin.action(description='Ficar offline')
    def ficar_offline(self, request, queryset):
        n = queryset.update(online=False)
        self.message_user(request, f'{n} atendente(s) offline.', messages.SUCCESS)


class MensagemInline(admin.TabularInline):
    model = Mensagem
    extra = 0
    fields = ['criada_em', 'autor', 'texto', 'lida']
    readonly_fields = ['criada_em', 'autor', 'texto']
    ordering = ['id']
    can_delete = True

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Conversa)
class ConversaAdmin(admin.ModelAdmin):
    list_display = [
        'id', 'cliente', 'tipo', 'atendente', 'status', 'tempo_restante',
        'nao_lidas', 'iniciada_em', 'atualizada_em',
    ]
    list_filter = ['status', 'atendente']
    search_fields = ['consulta__nome_cliente', 'consulta__email_cliente', 'consulta__referencia']
    list_select_related = ['consulta__tipo_consulta', 'atendente']
    readonly_fields = [
        'consulta', 'status', 'iniciada_em', 'segundos_concedidos', 'encerrada_em',
        'expira_em', 'tempo_restante', 'criada_em', 'atualizada_em',
    ]
    fields = ['consulta', 'atendente', *readonly_fields[1:]]
    inlines = [MensagemInline]
    actions = ['iniciar', 'estender_10', 'estender_30', 'encerrar']

    def has_add_permission(self, request):
        return False

    @admin.display(description='Cliente', ordering='consulta__nome_cliente')
    def cliente(self, obj):
        return obj.consulta.nome_cliente

    @admin.display(description='Consulta')
    def tipo(self, obj):
        return obj.consulta.tipo_consulta.nome

    @admin.display(description='Tempo restante')
    def tempo_restante(self, obj):
        if obj.status != Conversa.STATUS_ATIVA:
            return '—'
        return obj.tempo_restante_display

    @admin.display(description='Não lidas')
    def nao_lidas(self, obj):
        n = obj.mensagens.filter(autor=Mensagem.AUTOR_CLIENTE, lida=False).count()
        return format_html('<strong>{}</strong>', n) if n else 0

    def _aplicar(self, request, queryset, metodo, rotulo, *args):
        n = sum(1 for c in queryset if getattr(c, metodo)(*args))
        self.message_user(request, f'{rotulo}: {n} conversa(s).', messages.SUCCESS)

    @admin.action(description='Iniciar atendimento')
    def iniciar(self, request, queryset):
        atendente = getattr(request.user, 'atendente', None)
        self._aplicar(request, queryset, 'iniciar', 'Iniciadas', atendente)

    @admin.action(description='Estender +10 min')
    def estender_10(self, request, queryset):
        self._aplicar(request, queryset, 'estender', 'Estendidas', 10)

    @admin.action(description='Estender +30 min')
    def estender_30(self, request, queryset):
        self._aplicar(request, queryset, 'estender', 'Estendidas', 30)

    @admin.action(description='Encerrar')
    def encerrar(self, request, queryset):
        self._aplicar(request, queryset, 'encerrar', 'Encerradas')
