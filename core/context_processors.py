from django.conf import settings


def google_analytics(request):
    """Injeta GA4 e Chatwoot no contexto dos templates."""
    return {
        'GOOGLE_ANALYTICS_ID': settings.GOOGLE_ANALYTICS_ID,
        'CHATWOOT_TOKEN': settings.CHATWOOT_TOKEN,
    }