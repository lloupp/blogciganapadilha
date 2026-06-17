from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.db.models import Q
from .models import Post, Categoria, Tag


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