import logging
import signal
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from redator.agente import proxima_pendente, responder

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = ('Responde as mensagens pendentes do agente de postagens e, a cada minuto, '
            'confere os Pix pendentes das consultas. Roda como o serviço blog-mae-redator.')

    def add_arguments(self, parser):
        parser.add_argument('--intervalo', type=float, default=2.0, help='segundos entre verificações')
        parser.add_argument('--uma-vez', action='store_true', help='processa o que houver e sai')

    def handle(self, *args, intervalo, uma_vez, **options):
        self.parar = False
        signal.signal(signal.SIGTERM, self._parar)
        signal.signal(signal.SIGINT, self._parar)
        self.stdout.write('redator_worker: aguardando mensagens')
        ultima_conferencia_pix = 0.0
        while not self.parar:
            close_old_connections()
            if time.monotonic() - ultima_conferencia_pix >= 60:
                ultima_conferencia_pix = time.monotonic()
                self._conferir_pix()
            mensagem_id = proxima_pendente()
            if mensagem_id:
                try:
                    responder(mensagem_id)
                except Exception:
                    logger.exception('Falha ao responder a mensagem %s', mensagem_id)
                    from redator.models import Mensagem
                    Mensagem.objects.filter(pk=mensagem_id, estado=Mensagem.PENSANDO).update(
                        estado=Mensagem.ERRO, texto='Erro inesperado. Tente enviar de novo.')
                continue
            if uma_vez:
                break
            time.sleep(intervalo)

    def _conferir_pix(self):
        """Confirma Pix pagos cuja página a cliente já fechou (e dispara o aviso)."""
        try:
            from consultas.views import verificar_pix_pendentes
            aprovadas = verificar_pix_pendentes()
            if aprovadas:
                logger.info('Conferência de Pix: %s consulta(s) aprovada(s)', aprovadas)
        except Exception:
            logger.exception('Falha na conferência periódica dos Pix pendentes')

    def _parar(self, *args):
        self.parar = True
