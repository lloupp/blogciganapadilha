from django.urls import path

from . import views

# Painel da atendente: fica dentro do admin (/admin/atendimento/), só para staff.
app_name = 'painel'

urlpatterns = [
    path('', views.painel, name='painel'),
    path('<int:pk>/', views.painel_conversa, name='painel_conversa'),
    path('<int:pk>/mensagens/', views.painel_mensagens, name='painel_mensagens'),
    path('<int:pk>/enviar/', views.painel_enviar, name='painel_enviar'),
    path('<int:pk>/iniciar/', views.painel_iniciar, name='painel_iniciar'),
    path('<int:pk>/estender/', views.painel_estender, name='painel_estender'),
    path('<int:pk>/encerrar/', views.painel_encerrar, name='painel_encerrar'),
]
