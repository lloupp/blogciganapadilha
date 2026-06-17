from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('blog/', views.post_list, name='post_list'),
    path('busca/', views.post_list, name='busca'),
    path('categoria/<slug:slug>/', views.categoria_detail, name='categoria_detail'),
    path('tag/<slug:slug>/', views.tag_detail, name='tag_detail'),
    path('<slug:slug>/', views.post_detail, name='post_detail'),
]