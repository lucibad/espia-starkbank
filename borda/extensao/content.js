// EspIA · borda — content script.
//
// Observa o envio de prompts nas ferramentas de IA e reporta ao background.
// Modo "observacao": só governança, não bloqueia nada. Roda detectores e
// fingerprint AQUI; o texto nunca sai da máquina (enviar_conteudo: false).

(function () {
  var dominio = location.hostname.replace(/^www\./, "");
  var ultimoEnvio = 0;

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

  // Constrói o evento no contrato do espia-borda. Só metadados + assinaturas.
  function montarEvento(t, forma) {
    var D = self.EspiaDetectores, F = self.EspiaFingerprint;
    var dets = D.detectar(t);
    var cls = D.classificarBorda(dets);
    var masc = D.mascarar(t.slice(0, 160));
    return {
      modo: "observacao",
      enviar_conteudo: false,
      dominio: dominio,
      ferramenta: (self.RASTRO && self.RASTRO.FERRAMENTAS[dominio]) || dominio,
      forma: forma || "Prompt",
      qtd: 1,
      tamanho: t.length,
      titulo: document.title.slice(0, 120),
      deteccoes: dets,                    // [{tipo, contagem, validado}] — nunca valores
      pii_total: D.totalPii(dets),
      tipo: cls.tipo,
      sens: cls.sens,
      fingerprint: F.assinatura(t),       // minhash + simhash; o texto é descartado
      previa: masc.texto.replace(/\s+/g, " ").trim().slice(0, 120),
    };
  }

  function reportar(texto, forma) {
    var t = (texto || "").trim();
    if (t.length < 2) return;
    var agora = Date.now();
    if (agora - ultimoEnvio < 800) return;   // Enter + clique não duplicam
    ultimoEnvio = agora;
    try { chrome.runtime.sendMessage({ tipo: "evento", evento: montarEvento(t, forma) }); } catch (e) {}
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
      try { chrome.runtime.sendMessage({ tipo: "evento", evento: montarEvento(t, "Trecho de documento") }); } catch (e2) {}
    }
  }, true);
})();
