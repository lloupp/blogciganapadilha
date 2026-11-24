from django.urls import path

from . import views

app_name = 'consultas'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('sucesso/', views.sucesso, name='sucesso'),
    path('pendente/', views.pendente, name='pendente'),
    path('erro/', views.erro, name='erro'),
    path('webhook/mercadopago/', views.webhook, name='webhook'),
    path('status/<uuid:referencia>/', views.status, name='status'),
    path('status/<uuid:referencia>/verificar/', views.verificar, name='verificar'),
    path('chat/<uuid:referencia>/', views.chat, name='chat'),
    path('chat/<uuid:referencia>/mensagens/', views.chat_mensagens, name='chat_mensagens'),
    path('chat/<uuid:referencia>/enviar/', views.chat_enviar, name='chat_enviar'),
    # Painel da atendente (staff). Precisa vir antes do <slug>.
    path('painel/', views.painel, name='painel'),
    path('painel/<int:pk>/', views.painel_conversa, name='painel_conversa'),
    path('painel/<int:pk>/mensagens/', views.painel_mensagens, name='painel_mensagens'),
    path('painel/<int:pk>/enviar/', views.painel_enviar, name='painel_enviar'),
    path('painel/<int:pk>/iniciar/', views.painel_iniciar, name='painel_iniciar'),
    path('painel/<int:pk>/estender/', views.painel_estender, name='painel_estender'),
    path('painel/<int:pk>/encerrar/', views.painel_encerrar, name='painel_encerrar'),
    path('<slug:slug>/', views.solicitar, name='solicitar'),
]
