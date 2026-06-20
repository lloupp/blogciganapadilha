from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpResponse
from django.urls import reverse
from .models import Post, Categoria, Tag


def robots_txt(request):
    lines = [
        'User-agent: *',
        'Disallow: /admin/',
        'Allow: /',
        '',
        f'Sitemap: {request.build_absolute_uri(reverse("core:sitemap"))}',
    ]
    return HttpResponse('\n'.join(lines), content_type='text/plain')


def sitemap_xml(request):
    """Sitemap XML simples sem depender do framework de sitemaps."""
    from django.utils import timezone
    import xml.etree.ElementTree as ET

    now = timezone.now().strftime('%Y-%m-%d')

    urlset = ET.Element('urlset', xmlns='http://www.sitemaps.org/schemas/sitemap/0.9')

    # Páginas estáticas
    static_pages = [
        ('core:home', '0.8', 'daily'),
        ('core:post_list', '0.6', 'weekly'),
    ]
    for name, priority, freq in static_pages:
        url = ET.SubElement(urlset, 'url')
        loc = ET.SubElement(url, 'loc')
        loc.text = request.build_absolute_uri(reverse(name))
        changefreq = ET.SubElement(url, 'changefreq')
        changefreq.text = freq
        prio = ET.SubElement(url, 'priority')
        prio.text = priority

    # Posts publicados
    for post in Post.objects.filter(status='publicado'):
        url = ET.SubElement(urlset, 'url')
        loc = ET.SubElement(url, 'loc')
        loc.text = request.build_absolute_uri(post.get_absolute_url())
        lastmod = ET.SubElement(url, 'lastmod')
        lastmod.text = post.data_atualizacao.strftime('%Y-%m-%d')
        changefreq = ET.SubElement(url, 'changefreq')
        changefreq.text = 'weekly'
        prio = ET.SubElement(url, 'priority')
        prio.text = '0.8'

    # Categorias ativas
    for cat in Categoria.objects.filter(ativo=True):
        url = ET.SubElement(urlset, 'url')
        loc = ET.SubElement(url, 'loc')
        loc.text = request.build_absolute_uri(cat.get_absolute_url())
        changefreq = ET.SubElement(url, 'changefreq')
        changefreq.text = 'monthly'
        prio = ET.SubElement(url, 'priority')
        prio.text = '0.5'

    xml_str = ET.tostring(urlset, encoding='unicode')
    return HttpResponse(xml_str, content_type='application/xml')


def home(request):
    posts_destaque = Post.objects.filter(
        status='publicado',
        destaque=True
    ).select_related('categoria').prefetch_related('tags')[:3]

    posts_recentes = Post.objects.filter(
        status='publicado'
    ).select_related('categoria').prefetch_related('tags')[:6]

    categorias = Categoria.objects.filter(ativo=True)

    context = {
        'posts_destaque': posts_destaque,
        'posts_recentes': posts_recentes,
        'categorias': categorias,
    }
    return render(request, 'core/home.html', context)


def post_list(request):
    queryset = Post.objects.filter(status='publicado').select_related('categoria').prefetch_related('tags')

    # Filtros
    categoria_slug = request.GET.get('categoria')
    tag_slug = request.GET.get('tag')
    busca = request.GET.get('q')

    if categoria_slug:
        queryset = queryset.filter(categoria__slug=categoria_slug)
    if tag_slug:
        queryset = queryset.filter(tags__slug=tag_slug)
    if busca:
        queryset = queryset.filter(
            Q(titulo__icontains=busca) |
            Q(subtitulo__icontains=busca) |
            Q(conteudo__icontains=busca)
        )

    paginator = Paginator(queryset, 9)
    page = request.GET.get('page')
    posts = paginator.get_page(page)

    categorias = Categoria.objects.filter(ativo=True)
    tags_populares = Tag.objects.all()[:20]

    context = {
        'posts': posts,
        'categorias': categorias,
        'tags_populares': tags_populares,
        'categoria_atual': categoria_slug,
        'tag_atual': tag_slug,
        'busca': busca,
    }
    return render(request, 'core/post_list.html', context)


def post_detail(request, slug):
    post = get_object_or_404(
        Post.objects.select_related('categoria').prefetch_related('tags'),
        slug=slug,
        status='publicado'
    )

    post.incrementar_visualizacoes()

    # Posts relacionados (mesma categoria ou tags)
    posts_relacionados = Post.objects.filter(
        status='publicado'
    ).exclude(pk=post.pk)

    if post.categoria:
        posts_relacionados = posts_relacionados.filter(categoria=post.categoria)
    else:
        tag_ids = post.tags.values_list('id', flat=True)
        if tag_ids:
            posts_relacionados = posts_relacionados.filter(tags__in=tag_ids)

    posts_relacionados = posts_relacionados.distinct()[:3]

    context = {
        'post': post,
        'posts_relacionados': posts_relacionados,
    }
    return render(request, 'core/post_detail.html', context)


def categoria_detail(request, slug):
    categoria = get_object_or_404(Categoria, slug=slug, ativo=True)
    posts = Post.objects.filter(
        categoria=categoria,
        status='publicado'
    ).select_related('categoria').prefetch_related('tags')

    paginator = Paginator(posts, 9)
    page = request.GET.get('page')
    posts_page = paginator.get_page(page)

    context = {
        'categoria': categoria,
        'posts': posts_page,
    }
    return render(request, 'core/categoria_detail.html', context)


def tag_detail(request, slug):
    tag = get_object_or_404(Tag, slug=slug)
    posts = Post.objects.filter(
        tags=tag,
        status='publicado'
    ).select_related('categoria').prefetch_related('tags')

    paginator = Paginator(posts, 9)
    page = request.GET.get('page')
    posts_page = paginator.get_page(page)

    context = {
        'tag': tag,
        'posts': posts_page,
    }
    return render(request, 'core/tag_detail.html', context)