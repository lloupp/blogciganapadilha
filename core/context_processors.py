from django.conf import settings


def google_analytics(request):
    """Injeta GA4 no contexto dos templates."""
    return {
        'GOOGLE_ANALYTICS_ID': settings.GOOGLE_ANALYTICS_ID,
    }


def site_url(request):
    """Domínio canônico (não-www) para o link rel=canonical do base.html."""
    return {
        'SITE_URL': settings.SITE_URL,
    }