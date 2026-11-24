from django.urls import path

from . import views

app_name = 'consultas'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('depoimento/', views.depoimento, name='depoimento'),
    path('sucesso/', views.sucesso, name='sucesso'),
    path('pendente/', views.pendente, name='pendente'),
    path('erro/', views.erro, name='erro'),
    path('webhook/mercadopago/', views.webhook, name='webhook'),
    path('status/<uuid:referencia>/', views.status, name='status'),
    path('status/<uuid:referencia>/verificar/', views.verificar, name='verificar'),
    path('chat/<uuid:referencia>/', views.chat, name='chat'),
    path('chat/<uuid:referencia>/mensagens/', views.chat_mensagens, name='chat_mensagens'),
    path('chat/<uuid:referencia>/enviar/', views.chat_enviar, name='chat_enviar'),
    path('<slug:slug>/', views.solicitar, name='solicitar'),
]
