from django.contrib import admin

from .models import Consulta, TipoConsulta


@admin.register(TipoConsulta)
class TipoConsultaAdmin(admin.ModelAdmin):
    list_display = ['icone', 'nome', 'preco', 'duracao_minutos', 'ativo', 'ordem']
    list_editable = ['ativo', 'ordem']
    prepopulated_fields = {'slug': ('nome',)}
    search_fields = ['nome', 'descricao']
    list_filter = ['ativo']


@admin.register(Consulta)
class ConsultaAdmin(admin.ModelAdmin):
    list_display = ['nome_cliente', 'tipo_consulta', 'valor', 'status', 'whatsapp_cliente', 'criado_em']
    list_filter = ['status', 'tipo_consulta']
    search_fields = ['nome_cliente', 'email_cliente', 'whatsapp_cliente', 'referencia']
    date_hierarchy = 'criado_em'
    readonly_fields = [
        'referencia', 'tipo_consulta', 'nome_cliente', 'email_cliente', 'whatsapp_cliente',
        'valor', 'mp_preference_id', 'mp_payment_id', 'criado_em', 'atualizado_em',
    ]

    def has_add_permission(self, request):
        return False
