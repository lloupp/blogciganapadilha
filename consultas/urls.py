from django.urls import path

from . import views

app_name = 'consultas'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('sucesso/', views.sucesso, name='sucesso'),
    path('pendente/', views.pendente, name='pendente'),
    path('erro/', views.erro, name='erro'),
    path('webhook/mercadopago/', views.webhook, name='webhook'),
    path('<slug:slug>/', views.solicitar, name='solicitar'),
]
