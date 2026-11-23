from django.core.management.base import BaseCommand

from redator.agente import responder


class Command(BaseCommand):
    help = 'Gera a resposta do agente de postagens para uma mensagem (uso interno).'

    def add_arguments(self, parser):
        parser.add_argument('mensagem_id', type=int)

    def handle(self, *args, mensagem_id, **options):
        responder(mensagem_id)
