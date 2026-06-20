from django.conf import settings


def google_analytics(request):
    """Injeta o GA4 ID no contexto dos templates."""
    return {
        'GOOGLE_ANALYTICS_ID': settings.GOOGLE_ANALYTICS_ID,
    }