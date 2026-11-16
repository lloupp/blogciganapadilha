/* ============================================================
   Painel da atendente — ações sobre a conversa.
   O chat em si (polling, envio, contador) vem de chat.js.
   ============================================================ */
(function () {
    'use strict';

    document.addEventListener('DOMContentLoaded', function () {
        var painel = document.getElementById('painel-acoes');
        var raiz = document.getElementById('chat');
        if (!painel || !raiz) { return; }

        var el = function (nome) { return painel.querySelector('[data-acao="' + nome + '"]'); };
        var erro = el('erro');
        var ocupado = false;

        var ROTULOS = {
            aguardando: 'Aguardando atendente',
            ativa: 'Em atendimento',
            encerrada: 'Encerrada',
            expirada: 'Tempo esgotado'
        };

        function atualizar(status) {
            el('status').textContent = ROTULOS[status] || status;
            el('iniciar').hidden = status !== 'aguardando';
            el('estender-grupo').hidden = status !== 'ativa' && status !== 'expirada';
            el('encerrar').hidden = status !== 'aguardando' && status !== 'ativa';
        }

        function travar(sim) {
            ocupado = sim;
            var botoes = painel.querySelectorAll('button');
            for (var i = 0; i < botoes.length; i++) { botoes[i].disabled = sim; }
        }

        function acao(url, corpo, confirmar) {
            if (ocupado) { return; }
            if (confirmar && !window.confirm(confirmar)) { return; }
            var chat = window.chatConsulta;
            travar(true);
            erro.textContent = '';
            fetch(url + '?apos=' + (chat ? chat.ultimoId : 0), {
                method: 'POST',
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'X-CSRFToken': raiz.dataset.csrf
                },
                body: JSON.stringify(corpo || {})
            })
                .then(function (resp) {
                    return resp.json().catch(function () { return {}; });
                })
                .then(function (dados) {
                    if (!dados.ok) {
                        erro.textContent = dados.erro || 'Não foi possível concluir a ação.';
                        if (chat) { chat.poll(); }
                        return;
                    }
                    if (chat) { chat.aplicar(dados, true); }
                })
                .catch(function () {
                    erro.textContent = 'Sem conexão. Tente de novo.';
                })
                .then(function () { travar(false); });
        }

        raiz.addEventListener('chat:payload', function (e) { atualizar(e.detail.status); });

        el('iniciar').addEventListener('click', function () {
            acao(painel.dataset.urlIniciar);
        });
        el('encerrar').addEventListener('click', function () {
            acao(painel.dataset.urlEncerrar, null, 'Encerrar este atendimento? A cliente não poderá mais escrever.');
        });
        var extensoes = painel.querySelectorAll('[data-acao="estender"]');
        for (var i = 0; i < extensoes.length; i++) {
            extensoes[i].addEventListener('click', function () {
                acao(painel.dataset.urlEstender, { minutos: parseInt(this.dataset.minutos, 10) });
            });
        }
    });
})();
