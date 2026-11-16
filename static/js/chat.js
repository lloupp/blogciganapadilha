/* ============================================================
   Chat da consulta — polling, envio e contador.
   Usado pela cliente (data-papel="cliente") e pelo painel da
   atendente (data-papel="atendente").

   Segurança: todo texto vai para o DOM via textContent, nunca innerHTML.
   ============================================================ */
(function () {
    'use strict';

    var AVISOS = {
        cliente: {
            aguardando: 'A Cigana foi avisada e vai iniciar seu atendimento. Você já pode escrever: o tempo só começa a contar quando ela iniciar.',
            ativa: '',
            expirada: 'O tempo da consulta acabou.',
            encerrada: 'O atendimento foi encerrado.'
        },
        atendente: {
            aguardando: 'Cliente aguardando. O relógio só começa quando você clicar em "Iniciar atendimento".',
            ativa: '',
            expirada: 'Tempo esgotado. Use +10/+15/+30 min para reabrir.',
            encerrada: 'Atendimento encerrado.'
        }
    };

    var INTERVALO_FECHADA = 10000;
    var INTERVALO_OCULTA = 15000;
    var INTERVALO_MAX_ERRO = 30000;

    function formatarTempo(segundos) {
        segundos = Math.max(0, Math.floor(segundos));
        var h = Math.floor(segundos / 3600);
        var m = Math.floor((segundos % 3600) / 60);
        var s = segundos % 60;
        var mm = (m < 10 ? '0' : '') + m;
        var ss = (s < 10 ? '0' : '') + s;
        return h > 0 ? h + ':' + mm + ':' + ss : mm + ':' + ss;
    }

    function Chat(raiz) {
        this.raiz = raiz;
        this.papel = raiz.dataset.papel || 'cliente';
        this.urlMensagens = raiz.dataset.urlMensagens;
        this.urlEnviar = raiz.dataset.urlEnviar;
        this.csrf = raiz.dataset.csrf;
        this.intervalo = parseInt(raiz.dataset.intervalo, 10) || 3000;

        this.el = {};
        var nomes = ['lista', 'vazio', 'form', 'texto', 'enviar', 'erro', 'aviso',
                     'relogio', 'tempo', 'fim', 'presenca', 'presenca-texto'];
        for (var i = 0; i < nomes.length; i++) {
            this.el[nomes[i]] = raiz.querySelector('[data-chat="' + nomes[i] + '"]');
        }

        this.ultimoId = 0;
        this.lidasAte = 0;
        this.status = null;
        this.podeEnviar = false;
        this.segundos = 0;
        this.ancora = 0;       // Date.now() do último payload
        this.enviando = false;
        this.timerPoll = null;
        this.erros = 0;

        this._ligarEventos();
        this.poll();
        var self = this;
        setInterval(function () { self._tick(); }, 1000);
    }

    Chat.prototype._ligarEventos = function () {
        var self = this;
        if (this.el.form) {
            this.el.form.addEventListener('submit', function (e) {
                e.preventDefault();
                self.enviar();
            });
        }
        if (this.el.texto) {
            this.el.texto.addEventListener('keydown', function (e) {
                if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) {
                    e.preventDefault();
                    self.enviar();
                }
            });
            this.el.texto.addEventListener('input', function () { self._autoAltura(); });
        }
        document.addEventListener('visibilitychange', function () {
            if (!document.hidden) { self.poll(); }
        });
    };

    Chat.prototype._autoAltura = function () {
        var t = this.el.texto;
        t.style.height = 'auto';
        var altura = t.scrollHeight + 2; // + borda (box-sizing: border-box)
        t.style.height = Math.min(altura, 140) + 'px';
        t.style.overflowY = altura > 140 ? 'auto' : 'hidden';
    };

    /* --- rede ---------------------------------------------------- */

    Chat.prototype._agendar = function (ms) {
        var self = this;
        clearTimeout(this.timerPoll);
        this.timerPoll = setTimeout(function () { self.poll(); }, ms);
    };

    Chat.prototype._proximoIntervalo = function () {
        if (this.erros) {
            return Math.min(this.intervalo * Math.pow(2, this.erros), INTERVALO_MAX_ERRO);
        }
        if (document.hidden) { return INTERVALO_OCULTA; }
        if (this.status === 'encerrada' || this.status === 'expirada') { return INTERVALO_FECHADA; }
        return this.intervalo;
    };

    Chat.prototype._url = function (base) {
        return base + (base.indexOf('?') === -1 ? '?' : '&') + 'apos=' + this.ultimoId;
    };

    Chat.prototype._lerResposta = function (resp) {
        return resp.json().catch(function () { return {}; }).then(function (dados) {
            return { status: resp.status, dados: dados };
        });
    };

    Chat.prototype.poll = function () {
        var self = this;
        clearTimeout(this.timerPoll);
        if (this.carregando) { return; }
        this.carregando = true;
        fetch(this._url(this.urlMensagens), {
            credentials: 'same-origin',
            headers: { 'Accept': 'application/json' }
        })
            .then(function (resp) { return self._lerResposta(resp); })
            .then(function (r) {
                if (r.status === 403 && r.dados.redirect) {
                    window.location.href = r.dados.redirect;
                    return;
                }
                if (!r.dados.ok) { throw new Error(r.dados.erro || 'erro'); }
                self.erros = 0;
                self._mostrarErro('');
                self.aplicar(r.dados);
            })
            .catch(function () {
                self.erros = Math.min(self.erros + 1, 5);
                self._mostrarErro('Sem conexão. Tentando de novo…');
            })
            .then(function () {
                self.carregando = false;
                self._agendar(self._proximoIntervalo());
            });
    };

    Chat.prototype.enviar = function () {
        var self = this;
        var texto = (this.el.texto.value || '').trim();
        if (!texto || this.enviando || !this.podeEnviar) { return; }
        if (texto.length > 2000) {
            this._mostrarErro('A mensagem pode ter no máximo 2000 caracteres.');
            return;
        }

        this.enviando = true;
        this._atualizarForm();
        this._mostrarErro('');

        fetch(this._url(this.urlEnviar), {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRFToken': this.csrf
            },
            body: JSON.stringify({ texto: texto })
        })
            .then(function (resp) { return self._lerResposta(resp); })
            .then(function (r) {
                if (r.status === 403 && r.dados.redirect) {
                    window.location.href = r.dados.redirect;
                    return;
                }
                if (!r.dados.ok) {
                    self._mostrarErro(r.dados.erro || 'Não foi possível enviar. Tente de novo.');
                    if (r.status === 409) { self.poll(); }
                    return;
                }
                self.el.texto.value = '';
                self._autoAltura();
                self.aplicar(r.dados, true);
            })
            .catch(function () {
                self._mostrarErro('Não foi possível enviar. Verifique a conexão e tente de novo.');
            })
            .then(function () {
                self.enviando = false;
                self._atualizarForm();
                if (self.podeEnviar) { self.el.texto.focus(); }
            });
    };

    /* --- renderização -------------------------------------------- */

    Chat.prototype.aplicar = function (p, rolarSempre) {
        var lista = this.el.lista;
        var pertoDoFim = lista.scrollHeight - lista.scrollTop - lista.clientHeight < 80;

        for (var i = 0; i < p.mensagens.length; i++) {
            var m = p.mensagens[i];
            if (m.id <= this.ultimoId && lista.querySelector('[data-id="' + m.id + '"]')) { continue; }
            lista.appendChild(this._criarMensagem(m));
        }
        if (p.ultimo_id > this.ultimoId) { this.ultimoId = p.ultimo_id; }
        if (this.el.vazio) { this.el.vazio.hidden = lista.querySelector('.chat-msg') !== null; }

        this.lidasAte = p.lidas_ate || 0;
        this._marcarLidas();

        this.status = p.status;
        this.podeEnviar = !!p.pode_enviar;
        this.segundos = p.segundos_restantes;
        this.ancora = Date.now();

        this._atualizarPresenca(p.atendente);
        this._atualizarEstado();
        this._tick();

        if (p.mensagens.length && (pertoDoFim || rolarSempre)) {
            lista.scrollTop = lista.scrollHeight;
        }

        this.raiz.dispatchEvent(new CustomEvent('chat:payload', { detail: p }));
    };

    Chat.prototype._criarMensagem = function (m) {
        var li = document.createElement('li');
        var classe = m.autor === 'sistema' ? 'is-sistema' : (m.autor === this.papel ? 'is-eu' : 'is-outro');
        li.className = 'chat-msg ' + classe;
        li.dataset.id = m.id;
        li.dataset.autor = m.autor;

        var corpo = document.createElement('span');
        corpo.textContent = m.texto;
        li.appendChild(corpo);

        var meta = document.createElement('span');
        meta.className = 'chat-msg-meta';
        meta.textContent = m.criada_em;
        li.appendChild(meta);
        return li;
    };

    Chat.prototype._marcarLidas = function () {
        var minhas = this.el.lista.querySelectorAll('.chat-msg.is-eu');
        for (var i = 0; i < minhas.length; i++) {
            var meta = minhas[i].querySelector('.chat-msg-meta');
            var hora = meta.textContent.replace(/ ✓+$/, '');
            var lida = parseInt(minhas[i].dataset.id, 10) <= this.lidasAte;
            meta.textContent = hora + (lida ? ' ✓✓' : ' ✓');
            meta.title = lida ? 'Lida' : 'Enviada';
        }
    };

    Chat.prototype._atualizarPresenca = function (atendente) {
        if (!atendente || !this.el.presenca) { return; }
        var dot = this.el.presenca.querySelector('.chat-dot');
        if (dot) { dot.classList.toggle('is-online', !!atendente.online); }
        if (this.el['presenca-texto']) {
            this.el['presenca-texto'].textContent = atendente.online ? 'Online' : 'Offline';
        }
    };

    Chat.prototype._atualizarEstado = function () {
        var avisos = AVISOS[this.papel] || AVISOS.cliente;
        if (this.el.aviso) { this.el.aviso.textContent = avisos[this.status] || ''; }

        var fechada = this.status === 'encerrada' || this.status === 'expirada';
        if (this.el.fim) { this.el.fim.hidden = !fechada || this.papel !== 'cliente'; }
        if (this.el.form) { this.el.form.hidden = fechada && this.papel === 'cliente'; }

        if (this.el.relogio) {
            this.el.relogio.className = 'chat-relogio is-' + this.status;
        }
        this._atualizarForm();
    };

    Chat.prototype._atualizarForm = function () {
        if (!this.el.texto) { return; }
        this.el.texto.disabled = !this.podeEnviar;
        this.el.enviar.disabled = !this.podeEnviar || this.enviando;
        this.el.enviar.textContent = this.enviando ? 'Enviando…' : 'Enviar';
    };

    Chat.prototype._tick = function () {
        if (this.status === null || !this.el.tempo) { return; }
        var restante = this.segundos;
        if (this.status === 'ativa') {
            restante = this.segundos - (Date.now() - this.ancora) / 1000;
            if (restante <= 0 && this.podeEnviar) {
                // Acabou localmente: bloqueia e confirma com o servidor.
                this.podeEnviar = false;
                this._atualizarForm();
                this.poll();
            }
            if (this.el.relogio) {
                this.el.relogio.classList.toggle('is-acabando', restante <= 120);
            }
        }
        this.el.tempo.textContent = formatarTempo(restante);
    };

    Chat.prototype._mostrarErro = function (texto) {
        if (this.el.erro) { this.el.erro.textContent = texto; }
    };

    window.ChatConsulta = Chat;

    document.addEventListener('DOMContentLoaded', function () {
        var raiz = document.getElementById('chat');
        if (raiz) { window.chatConsulta = new Chat(raiz); }
    });
})();
