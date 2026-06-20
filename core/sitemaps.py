from django.contrib.sitemaps import Sitemap
from django.urls import reverse
from .models import Post, Categoria


class PostSitemap(Sitemap):
    changefreq = 'weekly'
    priority = 0.8

    def items(self):
        return Post.objects.filter(status='publicado')

    def lastmod(self, obj):
        return obj.data_atualizacao

    def location(self, obj):
        return obj.get_absolute_url()


class CategoriaSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.5

    def items(self):
        return Categoria.objects.filter(ativo=True)

    def location(self, obj):
        return obj.get_absolute_url()


class StaticSitemap(Sitemap):
    changefreq = 'monthly'
    priority = 0.3

    def items(self):
        return ['core:home', 'core:post_list']

    def location(self, item):
        return reverse(item)