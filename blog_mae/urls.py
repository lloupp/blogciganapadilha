"""
URL configuration for blog_mae project.
"""
from django.contrib import admin
from django.urls import path, include, re_path
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve as serve_media

admin.site.site_header = settings.ADMIN_SITE_HEADER
admin.site.site_title = settings.ADMIN_SITE_TITLE
admin.site.index_title = settings.ADMIN_INDEX_TITLE

urlpatterns = [
    path('admin/', admin.site.urls),
    path('consultas/', include('consultas.urls', namespace='consultas')),
    path('', include('core.urls', namespace='core')),
]

# Media (imagens enviadas pelo admin) — servido tambem em producao. O site e
# pequeno e fica atras da Cloudflare (que faz cache); o serve do Django trata
# path traversal com seguranca.
urlpatterns += [
    re_path(
        r'^%s(?P<path>.*)$' % settings.MEDIA_URL.lstrip('/'),
        serve_media,
        {'document_root': settings.MEDIA_ROOT},
    ),
]

# Em desenvolvimento, o runserver tambem serve os estaticos (em producao e o
# WhiteNoise que cuida disso).
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])