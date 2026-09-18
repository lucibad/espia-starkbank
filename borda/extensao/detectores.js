// EspIA — Detectores de conteúdo sensível na borda.
//
// Porte fiel de espia/detectores.py. Rodam no cliente e devolvem apenas
// CONTAGENS e tipos, nunca os valores encontrados. É a diferença entre um
// controle de governança e um keylogger.
//
// Responde "isto é sensível mesmo que não esteja em nenhum documento
// catalogado?" — o fingerprint (fingerprint.js) responde a outra pergunta,
// "de qual documento da empresa isto veio?".

(function () {
  // ── validadores brasileiros ──────────────────────────────────────
  function digitos(s) {
    var d = []; for (var i = 0; i < s.length; i++) { var c = s[i]; if (c >= "0" && c <= "9") d.push(+c); } return d;
  }
  function todosIguais(d) { for (var i = 1; i < d.length; i++) if (d[i] !== d[0]) return false; return true; }

  function cpfValido(cpf) {
    var d = digitos(cpf);
    if (d.length !== 11 || todosIguais(d)) return false;
    var tams = [9, 10];
    for (var t = 0; t < 2; t++) {
      var tam = tams[t], soma = 0;
      for (var i = 0; i < tam; i++) soma += d[i] * (tam + 1 - i);
      var dv = (soma * 10) % 11; if (dv === 10) dv = 0;
      if (dv !== d[tam]) return false;
    }
    return true;
  }

  function cnpjValido(cnpj) {
    var d = digitos(cnpj);
    if (d.length !== 14 || todosIguais(d)) return false;
    var pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
    var pesos2 = [6].concat(pesos1);
    var casos = [[pesos1, 12], [pesos2, 13]];
    for (var k = 0; k < 2; k++) {
      var pesos = casos[k][0], pos = casos[k][1], soma = 0;
      for (var i = 0; i < pos; i++) soma += d[i] * pesos[i];
      var resto = soma % 11, dv = resto < 2 ? 0 : 11 - resto;
      if (dv !== d[pos]) return false;
    }
    return true;
  }

  function luhnValido(numero) {
    var d = digitos(numero);
    if (d.length < 13 || d.length > 19) return false;
    var soma = 0, dobrar = false;
    for (var i = d.length - 1; i >= 0; i--) {
      var x = d[i];
      if (dobrar) { x *= 2; if (x > 9) x -= 9; }
      soma += x; dobrar = !dobrar;
    }
    return soma % 10 === 0;
  }

  // ── padrões (mesmos de espia/detectores.py) ──────────────────────
  var PADROES = {
    cpf: /\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b/g,
    cnpj: /\b\d{2}\.?\d{3}\.?\d{3}\/?\d{4}-?\d{2}\b/g,
    cartao: /\b(?:\d[ -]?){13,19}\b/g,
    email: /\b[\w.+-]+@[\w-]+\.[\w.]+\b/g,
    telefone: /\b(?:\+55\s?)?\(?\d{2}\)?\s?9?\d{4}[- ]?\d{4}\b/g,
    chave_pix_aleatoria: /\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b/gi,
    credencial: /(?:sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|-----BEGIN (?:RSA |EC )?PRIVATE KEY-----|(?:senha|password|secret|api[_-]?key|token)\s*[:=]\s*\S{8,})/gi,
    conta_bancaria: /\bag(?:[êe]ncia)?\.?\s*\d{4,5}[-\s/]?\d?\s*(?:c\/?c|conta)\.?\s*\d{4,12}-?\d\b/gi,
    iban_swift: /\b[A-Z]{6}[A-Z0-9]{2}(?:[A-Z0-9]{3})?\b/g,
  };
  var TIPOS_PII = { cpf: 1, email: 1, telefone: 1, chave_pix_aleatoria: 1 };

  function achados(texto, re) { var m = texto.match(re); return m || []; }

  // Varre e devolve [{tipo, contagem, validado}]. Nunca os valores.
  function detectar(texto) {
    var out = [];
    for (var tipo in PADROES) {
      var lista = achados(texto, PADROES[tipo]);
      if (!lista.length) continue;
      if (tipo === "cpf") {
        var v = lista.filter(cpfValido);
        if (v.length) out.push({ tipo: "cpf", contagem: v.length, validado: true });
      } else if (tipo === "cnpj") {
        var v2 = lista.filter(cnpjValido);
        if (v2.length) out.push({ tipo: "cnpj", contagem: v2.length, validado: true });
      } else if (tipo === "cartao") {
        var v3 = lista.filter(function (a) { return luhnValido(a) && !cpfValido(a) && !cnpjValido(a); });
        if (v3.length) out.push({ tipo: "cartao", contagem: v3.length, validado: true });
      } else if (tipo === "iban_swift") {
        if (/\bswift\b|\bbic\b|\biban\b/i.test(texto)) out.push({ tipo: "iban_swift", contagem: lista.length, validado: false });
      } else {
        out.push({ tipo: tipo, contagem: lista.length, validado: false });
      }
    }
    return out;
  }

  function totalPii(dets) {
    return dets.reduce(function (s, d) { return s + (TIPOS_PII[d.tipo] ? d.contagem : 0); }, 0);
  }
  function tem(dets, tipo) { return dets.some(function (d) { return d.tipo === tipo; }); }

  // ── mascaramento — "negocie, não bloqueie" ───────────────────────
  var SUBSTITUTOS = {
    cpf: "[CPF-MASCARADO]", cnpj: "[CNPJ-MASCARADO]", cartao: "[CARTAO-MASCARADO]",
    email: "[EMAIL-MASCARADO]", telefone: "[TELEFONE-MASCARADO]",
    chave_pix_aleatoria: "[CHAVE-PIX-MASCARADA]", credencial: "[CREDENCIAL-REMOVIDA]",
    conta_bancaria: "[CONTA-MASCARADA]",
  };

  function mascarar(texto) {
    var subs = 0, saida = texto;
    for (var tipo in PADROES) {
      if (!SUBSTITUTOS[tipo]) continue;
      if (tipo === "cpf") {
        saida = saida.replace(PADROES.cpf, function (m) { if (cpfValido(m)) { subs++; return SUBSTITUTOS.cpf; } return m; });
      } else if (tipo === "cartao") {
        saida = saida.replace(PADROES.cartao, function (m) { if (luhnValido(m)) { subs++; return SUBSTITUTOS.cartao; } return m; });
      } else {
        saida = saida.replace(PADROES[tipo], function () { subs++; return SUBSTITUTOS[tipo]; });
      }
    }
    return { texto: saida, substituicoes: subs };
  }

  // tipo/sensibilidade inferidos a partir das detecções, para o painel
  function classificarBorda(dets) {
    if (tem(dets, "credencial")) return { tipo: "Chave/API secret", sens: "Crítica" };
    if (tem(dets, "cartao")) return { tipo: "Dado financeiro (cartão)", sens: "Crítica" };
    if (tem(dets, "cpf")) return { tipo: "Dado pessoal (CPF)", sens: "Crítica" };
    if (tem(dets, "conta_bancaria")) return { tipo: "Dado bancário", sens: "Crítica" };
    if (tem(dets, "cnpj")) return { tipo: "Dado cadastral (CNPJ)", sens: "Confidencial" };
    if (tem(dets, "chave_pix_aleatoria")) return { tipo: "Chave Pix", sens: "Confidencial" };
    if (tem(dets, "email") || tem(dets, "telefone")) return { tipo: "Dado de contato", sens: "Interna" };
    return { tipo: "Conteúdo não classificado", sens: "Interna" };
  }

  self.EspiaDetectores = {
    detectar: detectar, mascarar: mascarar, totalPii: totalPii, tem: tem,
    classificarBorda: classificarBorda,
    cpfValido: cpfValido, cnpjValido: cnpjValido, luhnValido: luhnValido,
  };
})();
