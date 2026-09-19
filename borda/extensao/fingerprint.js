// GerencIA — Fingerprint de informação, na borda.
//
// Porte de espia/fingerprint.py. A ideia central do GerencIA: para saber QUAL
// informação da empresa foi para dentro de uma IA não é preciso guardar o
// que o colaborador digitou — basta a ASSINATURA. O texto vira shingles
// (n-gramas de 5 palavras), os shingles viram MinHash (Jaccard) e SimHash
// (quase-duplicata), e o texto original é descartado aqui mesmo.
//
// O que sai da máquina é só a assinatura: números que só fazem sentido
// comparados com a assinatura do acervo, no servidor (casar()).
//
// Hash: FNV-1a 64 bits sobre UTF-8, em BigInt. Não é o blake2b do Python —
// o lado servidor que fizer o casamento precisa usar ESTE mesmo hash para as
// assinaturas serem comparáveis (ver docs). O algoritmo é o do GerencIA.

(function () {
  var MASCARA_64 = (1n << 64n) - 1n;
  var PRIMO_MERSENNE = (1n << 61n) - 1n;
  var FNV_OFFSET = 0xcbf29ce484222325n, FNV_PRIME = 0x100000001b3n;

  function hash64(s) {
    var bytes = new TextEncoder().encode(s), h = FNV_OFFSET;
    for (var i = 0; i < bytes.length; i++) { h ^= BigInt(bytes[i]); h = (h * FNV_PRIME) & MASCARA_64; }
    return h;
  }

  // ── normalização (tolerante ao mundo real) ───────────────────────
  function normalizar(texto) {
    var t = (texto || "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
    t = t.replace(/[^a-z0-9\s]+/g, " ");
    return t.replace(/\s+/g, " ").trim();
  }

  function shingles(texto, n) {
    n = n || 5;
    var p = normalizar(texto).split(" ").filter(Boolean);
    var s = new Set();
    if (!p.length) return s;
    if (p.length < n) { s.add(p.join(" ")); return s; }
    for (var i = 0; i + n <= p.length; i++) s.add(p.slice(i, i + n).join(" "));
    return s;
  }

  // ── MinHash — estimador de Jaccard ───────────────────────────────
  var _coefs = {};
  function coeficientes(numPerm) {
    if (_coefs[numPerm]) return _coefs[numPerm];
    var out = [], estado = 0x5EEDn;
    for (var i = 0; i < numPerm; i++) {
      estado = hash64("a" + estado.toString());
      var a = (estado % (PRIMO_MERSENNE - 1n)) + 1n;
      estado = hash64("b" + estado.toString());
      var b = estado % PRIMO_MERSENNE;
      out.push([a, b]);
    }
    _coefs[numPerm] = out; return out;
  }

  function minhash(conjunto, numPerm) {
    numPerm = numPerm || 32;
    var coefs = coeficientes(numPerm), sig = new Array(numPerm).fill(PRIMO_MERSENNE);
    conjunto.forEach(function (item) {
      var h = hash64(item) % PRIMO_MERSENNE;
      for (var i = 0; i < numPerm; i++) {
        var v = (coefs[i][0] * h + coefs[i][1]) % PRIMO_MERSENNE;
        if (v < sig[i]) sig[i] = v;
      }
    });
    return sig.map(function (x) { return x.toString(16); });
  }

  // ── SimHash — quase-duplicata e reordenação ──────────────────────
  function simhash(conjunto) {
    var vetor = new Array(64).fill(0), vazio = true;
    conjunto.forEach(function (item) {
      vazio = false; var h = hash64(item);
      for (var bit = 0; bit < 64; bit++) vetor[bit] += ((h >> BigInt(bit)) & 1n) ? 1 : -1;
    });
    if (vazio) return "0";
    var valor = 0n;
    for (var b = 0; b < 64; b++) if (vetor[b] > 0) valor |= (1n << BigInt(b));
    return valor.toString(16);
  }

  // Assinatura: só o que vai para o servidor. Os shingles ficam aqui.
  function assinatura(texto, opts) {
    opts = opts || {};
    var sh = shingles(texto, opts.n || 5);
    return { minhash: minhash(sh, opts.numPerm || 32), simhash: simhash(sh), n_shingles: sh.size, hash: "fnv1a64" };
  }

  self.EspiaFingerprint = { normalizar: normalizar, shingles: shingles, minhash: minhash, simhash: simhash, assinatura: assinatura, hash64: hash64 };
})();
