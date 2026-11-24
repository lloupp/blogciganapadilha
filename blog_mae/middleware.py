from django.conf import settings
from django.http import HttpResponsePermanentRedirect

WWW_HOST = 'www.blogciganapadilha.com.br'
LOCAL_HOSTS = {'localhost', '127.0.0.1'}


class WwwToNonWwwRedirectMiddleware:
    """Redireciona 301 www.blogciganapadilha.com.br -> blogciganapadilha.com.br.

    Preserva caminho e query string. Hosts locais e o host nu nunca
    redirecionam (SITE_URL é não-www, então não há loop).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(':')[0].lower()
        if host == WWW_HOST and host not in LOCAL_HOSTS:
            return HttpResponsePermanentRedirect(
                settings.SITE_URL + request.get_full_path()
            )
        return self.get_response(request)
