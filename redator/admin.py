from datetime import datetime

from django.conf import settings
from django.contrib import admin, messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from . import agente
from .models import Conversa, Memoria, Mensagem


@admin.register(Memoria)
class MemoriaAdmin(admin.ModelAdmin):
    list_display = ['texto', 'ativa', 'criada_em']
    list_editable = ['ativa']
    list_filter = ['ativa']
    search_fields = ['texto']
    fields = ['texto', 'ativa']


@admin.register(Conversa)
class ConversaAdmin(admin.ModelAdmin):
    list_display = ['abrir', 'situacao_post', 'num_mensagens', 'encerrada', 'atualizada_em']
    list_filter = ['encerrada']
    search_fields = ['titulo', 'mensagens__texto']
    list_display_links = None

    @admin.display(description='Conversa')
    def abrir(self, obj):
        url = reverse('admin:redator_conversa_chat', args=[obj.pk])
        return format_html('<a href="{}">{}</a>', url, obj)

    @admin.display(description='Post')
    def situacao_post(self, obj):
        post = obj.post
        if not post:
            return '—'
        if post.esta_agendado:
            return f'⏰ Agendado ({timezone.localtime(post.data_publicacao):%d/%m %H:%M})'
        return '✅ Publicado' if post.status == 'publicado' else '📝 Rascunho'

    @admin.display(description='Mensagens')
    def num_mensagens(self, obj):
        return obj.mensagens.filter(autor=Mensagem.DONA).count()

    # Toda a equipe (staff) usa o agente, sem precisar de permissões por modelo.
    def has_module_permission(self, request):
        return request.user.is_staff

    def has_view_permission(self, request, obj=None):
        return request.user.is_staff

    def has_change_permission(self, request, obj=None):
        return request.user.is_staff

    def has_add_permission(self, request):
        return request.user.is_staff

    def add_view(self, request, form_url='', extra_context=None):
        conversa = Conversa.objects.create(criada_por=request.user)
        return redirect('admin:redator_conversa_chat', conversa.pk)

    def change_view(self, request, object_id, form_url='', extra_context=None):
        return redirect('admin:redator_conversa_chat', object_id)

    def get_urls(self):
        v = self.admin_site.admin_view
        return [
            path('<int:pk>/chat/', v(self.chat_view), name='redator_conversa_chat'),
            path('<int:pk>/enviar/', v(self.enviar_view), name='redator_conversa_enviar'),
            path('<int:pk>/estado/', v(self.estado_view), name='redator_conversa_estado'),
            path('<int:pk>/publicar/', v(self.publicar_view), name='redator_conversa_publicar'),
            path('<int:pk>/agendar/', v(self.agendar_view), name='redator_conversa_agendar'),
        ] + super().get_urls()

    # -- telas ---------------------------------------------------------------

    def _conversa(self, request, pk):
        if not request.user.is_staff:
            raise Http404
        return get_object_or_404(Conversa.objects.select_related('post'), pk=pk)

    def chat_view(self, request, pk):
        conversa = self._conversa(request, pk)
        agente.expirar_pendentes(conversa)
        post = conversa.post
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': str(conversa),
            'conversa': conversa,
            'mensagens': conversa.mensagens.all(),
            'pensando': conversa.mensagens.filter(estado=Mensagem.PENSANDO).exists(),
            'post': post,
            'post_rascunho': bool(post and post.status == 'rascunho'),
            'restantes_hoje': agente.restantes_hoje(),
            'restantes_conversa': agente.restantes_na_conversa(conversa),
            'max_caracteres': settings.REDATOR_MAX_CARACTERES,
            'agora_local': timezone.localtime().strftime('%Y-%m-%dT%H:%M'),
        }
        return render(request, 'admin/redator/conversa_chat.html', context)

    def enviar_view(self, request, pk):
        if request.method != 'POST':
            return redirect('admin:redator_conversa_chat', pk)
        conversa = self._conversa(request, pk)
        agente.expirar_pendentes(conversa)
        texto = request.POST.get('texto', '')
        erro = agente.motivo_bloqueio(conversa, texto)
        if erro:
            messages.error(request, erro)
        else:
            agente.enviar(conversa, texto, request.user)
        return redirect('admin:redator_conversa_chat', pk)

    def estado_view(self, request, pk):
        conversa = self._conversa(request, pk)
        agente.expirar_pendentes(conversa)
        return JsonResponse({
            'pensando': conversa.mensagens.filter(estado=Mensagem.PENSANDO).exists(),
        })

    def _post_aprovavel(self, request, conversa):
        post = conversa.post
        if not post or post.status != 'rascunho':
            messages.error(request, 'Não há rascunho para aprovar nesta conversa.')
            return None
        if conversa.mensagens.filter(estado=Mensagem.PENSANDO).exists():
            messages.error(request, 'Espere o agente terminar a resposta antes de aprovar.')
            return None
        return post

    def _concluir(self, conversa, aviso, motivo):
        Mensagem.objects.create(conversa=conversa, autor=Mensagem.SISTEMA, texto=aviso)
        conversa.encerrar(motivo)

    def publicar_view(self, request, pk):
        if request.method != 'POST':
            return redirect('admin:redator_conversa_chat', pk)
        conversa = self._conversa(request, pk)
        post = self._post_aprovavel(request, conversa)
        if post:
            post.status = 'publicado'
            post.data_publicacao = timezone.now()
            post.save()
            self._concluir(conversa, f'✅ Post publicado: "{post.titulo}".', 'Post publicado')
            messages.success(request, format_html(
                'Post publicado. <a href="{}" target="_blank">Ver no blog</a>', post.get_absolute_url()))
        return redirect('admin:redator_conversa_chat', pk)

    def agendar_view(self, request, pk):
        if request.method != 'POST':
            return redirect('admin:redator_conversa_chat', pk)
        conversa = self._conversa(request, pk)
        post = self._post_aprovavel(request, conversa)
        if not post:
            return redirect('admin:redator_conversa_chat', pk)
        try:
            quando = timezone.make_aware(datetime.strptime(request.POST.get('quando', ''), '%Y-%m-%dT%H:%M'))
        except ValueError:
            messages.error(request, 'Escolha a data e a hora do agendamento.')
            return redirect('admin:redator_conversa_chat', pk)
        if quando <= timezone.now():
            messages.error(request, 'A data do agendamento precisa estar no futuro.')
            return redirect('admin:redator_conversa_chat', pk)
        post.status = 'publicado'
        post.data_publicacao = quando
        post.save()
        quando_txt = f'{timezone.localtime(quando):%d/%m/%Y às %H:%M}'
        self._concluir(conversa, f'⏰ Post agendado para {quando_txt}: "{post.titulo}".', 'Post agendado')
        messages.success(request, f'Post agendado para {quando_txt}.')
        return redirect('admin:redator_conversa_chat', pk)
