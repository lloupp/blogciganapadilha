"""
Django settings for blog_mae project.
"""

from pathlib import Path
from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-dev-key-change-in-production')

DEBUG = config('DEBUG', default=True, cast=bool)

ALLOWED_HOSTS = config(
    'ALLOWED_HOSTS',
    default='localhost,127.0.0.1,blogciganapadilha.com.br,www.blogciganapadilha.com.br'
).split(',')

CSRF_TRUSTED_ORIGINS = config(
    'CSRF_TRUSTED_ORIGINS',
    default='https://blogciganapadilha.com.br,https://www.blogciganapadilha.com.br,http://localhost:8000,http://127.0.0.1:8000'
).split(',')

INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sitemaps',
    'core',
    'axes',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'axes.middleware.AxesMiddleware',
]

AUTHENTICATION_BACKENDS = [
    'axes.backends.AxesBackend',
    'django.contrib.auth.backends.ModelBackend',
]

ROOT_URLCONF = 'blog_mae.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'core.context_processors.google_analytics',
            ],
        },
    },
]

WSGI_APPLICATION = 'blog_mae.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'pt-br'
TIME_ZONE = 'America/Sao_Paulo'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATICFILES_DIRS = [BASE_DIR / 'static']
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = 'media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

LOGIN_URL = 'admin:login'
LOGIN_REDIRECT_URL = 'admin:index'
LOGOUT_REDIRECT_URL = 'core:home'

# Admin customization
ADMIN_SITE_HEADER = '✨ Blog Cigana Padilha - Admin'
ADMIN_SITE_TITLE = 'Painel Admin'
ADMIN_INDEX_TITLE = 'Gerenciar Conteúdo'

# ============================================================
# Google Analytics
# ============================================================
GOOGLE_ANALYTICS_ID = config('GOOGLE_ANALYTICS_ID', default='')

# ============================================================
# Chatwoot
# ============================================================
CHATWOOT_TOKEN = config('CHATWOOT_TOKEN', default='')
CHATWOOT_URL = config('CHATWOOT_URL', default='https://app.chatwoot.com')

# ============================================================
# Segurança — Produção
# ============================================================

# Nginx termina TLS; o Gunicorn só vê HTTP puro via socket Unix.
# Este header tem que existir ANTES/JUNTO do SECURE_SSL_REDIRECT,
# senão o Django acha que toda request é insegura -> loop de redirect.
# Exige Nginx enviando "X-Forwarded-Proto $scheme" (já confirmado).
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)

CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True

SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=63072000, cast=int)  # 2 anos
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'strict-origin-when-cross-origin'

# django-axes — proteção de brute force no /admin/login/
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # horas
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_PARAMETERS = ['username', 'ip_address']