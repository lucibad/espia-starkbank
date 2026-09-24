// GerencIA · borda — content script.
//
// Observa o uso de IA no navegador e reporta ao background. Modo "observacao":
// só governança, não bloqueia nada. Detectores e fingerprint rodam AQUI.
//
// GUARDA DE CONTEUDO: por decisão de governança, a extensão registra o CONTEUDO
// das pesquisas (prompt) e o RETORNO da IA (resposta). É a única camada que
// enxerga isso — o tráfego é TLS e o agente de rede vê só metadado. O conteúdo
// trafega para o coletor central (on-premise) e deve ser protegido lá.

(function () {
  var dominio = location.hostname.replace(/^www\./, "");
  var ultimoEnvio = 0;
  var LIMITE = 16000;   // teto de caracteres guardados por prompt/resposta

  // Onde fica a resposta da IA, por site (o último nó é a resposta mais recente).
  var SELETOR_RESPOSTA = {
    "chatgpt.com": '[data-message-author-role="assistant"]',
    "chat.openai.com": '[data-message-author-role="assistant"]',
    "claude.ai": '[data-testid="assistant-turn"], .font-claude-message',
    "gemini.google.com": 'message-content, .model-response-text',
    "copilot.microsoft.com": '[data-content="ai-message"], .ac-textBlock',
    "perplexity.ai": '.prose, [class*="answer"]',
    "www.perplexity.ai": '.prose, [class*="answer"]',
    "chat.deepseek.com": '.ds-markdown, [class*="message"]',
    "grok.com": '[class*="response"], .prose',
  };

  function campoAtivo() {
    var el = document.activeElement;
    if (!el) return null;
    if (el.tagName === "TEXTAREA") return el.value;
    if (el.tagName === "INPUT" && (el.type === "text" || el.type === "search")) return el.value;
    if (el.isContentEditable) return el.innerText;
    return null;
  }

  function textoDeCampos() {
    var cand = document.querySelectorAll('textarea, [contenteditable="true"]'), melhor = "";
    for (var i = 0; i < cand.length; i++) {
      var el = cand[i], v = el.value !== undefined ? el.value : el.innerText;
      if (v && v.length > melhor.length && el.offsetParent !== null) melhor = v;
    }
    return melhor;
  }

  function novoParId() {
    return "PAR-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 8);
  }

  // Evento no contrato do espia-borda. Agora inclui o CONTEUDO (prompt/resposta).
  function montarEvento(t, forma, parId, papel) {
    var D = self.EspiaDetectores, F = self.EspiaFingerprint;
    var dets = D.detectar(t);
    var cls = D.classificarBorda(dets);
    var masc = D.mascarar(t.slice(0, 160));
    var ev = {
      modo: "observacao",
      enviar_conteudo: true,             // guarda de conteúdo ligada
      par_id: parId,
      papel: papel,                      // "prompt" | "resposta"
      dominio: dominio,
      ferramenta: (self.RASTRO && self.RASTRO.FERRAMENTAS[dominio]) || dominio,
      forma: forma,
      qtd: 1,
      tamanho: t.length,
      titulo: document.title.slice(0, 120),
      deteccoes: dets,                   // [{tipo, contagem, validado}] — nunca valores
      pii_total: D.totalPii(dets),
      tipo: cls.tipo,
      sens: cls.sens,
      fingerprint: F.assinatura(t),
      previa: masc.texto.replace(/\s+/g, " ").trim().slice(0, 120),
    };
    // O conteúdo completo vai no campo do papel correspondente.
    if (papel === "resposta") ev.resposta = t.slice(0, LIMITE);
    else ev.prompt = t.slice(0, LIMITE);
    return ev;
  }

  function enviar(ev) {
    try { chrome.runtime.sendMessage({ tipo: "evento", evento: ev }); } catch (e) {}
  }

  function textoResposta() {
    var sel = SELETOR_RESPOSTA[dominio];
    var nos = sel ? document.querySelectorAll(sel) : [];
    if (nos && nos.length) return (nos[nos.length - 1].innerText || "").trim();
    return "";
  }

  // Depois de enviar o prompt, acompanha a resposta até ela parar de crescer
  // (fim do streaming) e então registra o retorno da IA.
  function observarResposta(parId) {
    var inicio = Date.now(), ultimo = "", estavelDesde = 0;
    var timer = setInterval(function () {
      var atual = textoResposta();
      if (atual && atual.length >= 2) {
        if (atual === ultimo) {
          if (!estavelDesde) estavelDesde = Date.now();
          if (Date.now() - estavelDesde >= 1800) {   // parou de crescer → fim do streaming
            clearInterval(timer);
            enviar(montarEvento(atual, "Resposta da IA", parId, "resposta"));
            return;
          }
        } else {
          ultimo = atual; estavelDesde = 0;
        }
      }
      if (Date.now() - inicio > 90000) {   // desiste após 90s
        clearInterval(timer);
        if (ultimo) enviar(montarEvento(ultimo, "Resposta da IA", parId, "resposta"));
      }
    }, 700);
  }

  function reportar(texto, forma) {
    var t = (texto || "").trim();
    if (t.length < 2) return;
    var agora = Date.now();
    if (agora - ultimoEnvio < 800) return;   // Enter + clique não duplicam
    ultimoEnvio = agora;
    var parId = novoParId();
    enviar(montarEvento(t, forma || "Prompt", parId, "prompt"));
    observarResposta(parId);                 // e captura o retorno da IA
  }

  document.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
      var txt = campoAtivo();
      if (txt && txt.trim().length >= 2) reportar(txt, "Prompt");
    }
  }, true);

  document.addEventListener("click", function (e) {
    var alvo = e.target.closest('button, [role="button"]');
    if (!alvo) return;
    var rot = ((alvo.getAttribute("aria-label") || "") + " " + (alvo.getAttribute("data-testid") || "") + " " + (alvo.title || "")).toLowerCase();
    if (/send|enviar|submit|prompt/.test(rot)) reportar(campoAtivo() || textoDeCampos(), "Prompt");
  }, true);

  // colar um bloco grande = trecho de documento (o caso do fingerprint)
  document.addEventListener("paste", function (e) {
    var t = (e.clipboardData && e.clipboardData.getData("text")) || "";
    if (t.length >= 400) {
      var parId = novoParId();
      enviar(montarEvento(t, "Trecho de documento", parId, "prompt"));
      observarResposta(parId);
    }
  }, true);
})();
