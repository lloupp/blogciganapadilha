// Blog da Mãe — Main Script
document.addEventListener('DOMContentLoaded', function() {
    // Smooth fade-in for cards on scroll
    const cards = document.querySelectorAll('.post-card, .featured-card, .category-card');
    if (cards.length && 'IntersectionObserver' in window) {
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    entry.target.style.opacity = '1';
                    entry.target.style.transform = 'translateY(0)';
                }
            });
        }, { threshold: 0.1, rootMargin: '50px' });

        cards.forEach(card => {
            card.style.opacity = '0';
            card.style.transform = 'translateY(20px)';
            card.style.transition = 'opacity 0.6s ease, transform 0.6s ease';
            observer.observe(card);
        });
    }

    // Active nav link highlighting
    const currentPath = window.location.pathname;
    document.querySelectorAll('.nav-link').forEach(link => {
        const href = link.getAttribute('href');
        if (href === currentPath || (href !== '/' && currentPath.startsWith(href))) {
            link.classList.add('active');
        }
    });

    // Mobile nav toggle
    const navToggle = document.getElementById('navToggle');
    const mainNav = document.getElementById('mainNav');
    if (navToggle && mainNav) {
        navToggle.addEventListener('click', function() {
            const isOpen = mainNav.classList.toggle('open');
            navToggle.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        });

        mainNav.querySelectorAll('.nav-link').forEach(link => {
            link.addEventListener('click', function() {
                mainNav.classList.remove('open');
                navToggle.setAttribute('aria-expanded', 'false');
            });
        });

        document.addEventListener('click', function(event) {
            if (mainNav.classList.contains('open') &&
                !mainNav.contains(event.target) &&
                !navToggle.contains(event.target)) {
                mainNav.classList.remove('open');
                navToggle.setAttribute('aria-expanded', 'false');
            }
        });
    }
});