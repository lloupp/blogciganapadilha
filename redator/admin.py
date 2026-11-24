from datetime import datetime

from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.core.files.storage import default_storage
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.html import format_html

from . import agente
from core.models import Post

from .models import Conversa, Memoria, Mensagem

MAX_IMAGEM_MB = 8


class ImagemForm(forms.Form):
    imagem = forms.ImageField(required=False)

    def clean_imagem(self):
        imagem = self.cleaned_data.get('imagem')
        if imagem and imagem.size > MAX_IMAGEM_MB * 1024 * 1024:
            raise forms.ValidationError(f'Imagem grande demais (máximo {MAX_IMAGEM_MB} MB).')
        if imagem and imagem.image.format not in ('JPEG', 'PNG', 'WEBP', 'GIF'):
            raise forms.ValidationError('Use uma imagem JPG, PNG ou WEBP.')
        return imagem


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
            path('<int:pk>/aprovar-alteracoes/', v(self.aprovar_alteracoes_view),
                 name='redator_conversa_aprovar_alteracoes'),
            path('<int:pk>/descartar-alteracoes/', v(self.descartar_alteracoes_view),
                 name='redator_conversa_descartar_alteracoes'),
            path('editar-post/<int:post_id>/', v(self.editar_post_view), name='redator_conversa_editar_post'),
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
        versao = agente.versao(conversa)
        if versao:
            versao['imagem_url'] = default_storage.url(versao['imagem']) if versao['imagem'] else ''
        context = {
            **self.admin_site.each_context(request),
            'opts': self.model._meta,
            'title': str(conversa),
            'conversa': conversa,
            'mensagens': conversa.mensagens.all(),
            'pensando': conversa.mensagens.filter(estado=Mensagem.PENSANDO).exists(),
            'post': post,
            'post_rascunho': bool(post and post.status == 'rascunho'),
            'versao': versao,
            'editando_publicado': agente.editando_publicado(conversa),
            'tem_proposta': bool(conversa.proposta),
            'max_imagem_mb': MAX_IMAGEM_MB,
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
        form = ImagemForm(files=request.FILES)
        if not form.is_valid():
            messages.error(request, form.errors['imagem'][0])
            return redirect('admin:redator_conversa_chat', pk)
        imagem = form.cleaned_data.get('imagem')
        erro = agente.motivo_bloqueio(conversa, texto, tem_imagem=bool(imagem))
        if erro:
            messages.error(request, erro)
        else:
            agente.enviar(conversa, texto, request.user, imagem=imagem)
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

    def _ocupado(self, request, conversa):
        if conversa.mensagens.filter(estado=Mensagem.PENSANDO).exists():
            messages.error(request, 'Espere o agente terminar a resposta antes de aprovar.')
            return True
        return False

    def aprovar_alteracoes_view(self, request, pk):
        if request.method != 'POST':
            return redirect('admin:redator_conversa_chat', pk)
        conversa = self._conversa(request, pk)
        if not (agente.editando_publicado(conversa) and conversa.proposta):
            messages.error(request, 'Não há alterações para aprovar.')
        elif not self._ocupado(request, conversa):
            agente.aprovar_alteracoes(conversa)
            post = conversa.post
            self._concluir(conversa, f'✅ Alterações aprovadas: "{post.titulo}" foi atualizado.',
                           'Alterações aprovadas')
            messages.success(request, format_html(
                'Post atualizado. <a href="{}" target="_blank">Ver no blog</a>', post.get_absolute_url()))
        return redirect('admin:redator_conversa_chat', pk)

    def descartar_alteracoes_view(self, request, pk):
        if request.method != 'POST':
            return redirect('admin:redator_conversa_chat', pk)
        conversa = self._conversa(request, pk)
        if conversa.proposta and not self._ocupado(request, conversa):
            conversa.proposta = None
            conversa.save(update_fields=['proposta', 'atualizada_em'])
            Mensagem.objects.create(conversa=conversa, autor=Mensagem.SISTEMA,
                                    texto='Alterações descartadas. O post no ar continua como estava.')
        return redirect('admin:redator_conversa_chat', pk)

    def editar_post_view(self, request, post_id):
        if not request.user.is_staff:
            raise Http404
        post = get_object_or_404(Post, pk=post_id)
        conversa = agente.iniciar_edicao(post, request.user)
        return redirect('admin:redator_conversa_chat', conversa.pk)
