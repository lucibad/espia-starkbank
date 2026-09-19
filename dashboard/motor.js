/* =====================================================================
   GerencIA — motor de regras no navegador.

   Porte fiel de `espia/regras.py`. Existe por um motivo só: o console de
   políticas precisa mostrar o impacto de uma mudança ANTES de publicá-la, e
   para isso tem de reavaliar os 650 eventos e os 15 casos de validação com a
   política candidata, na hora, sem ida ao servidor.

   Se este motor divergir do Python, a simulação mente. Por isso o repositório
   traz um teste de paridade que roda os dois sobre a mesma base e compara
   evento a evento (`python3 testes_paridade.py`).

   O formato da política candidata:

     {
       regras:   { R01: { nivel, acao, ativa }, ... },
       precedencia: ["R14","R13","R03", ...],
       ferramentas: { "IA-01": { status }, ... },
       limiteVolume: 10
     }
   ===================================================================== */

(function (global) {
  "use strict";

  const SEVERIDADE = { "Baixo": 0, "Médio": 1, "Alto": 2, "Crítico": 3 };
  const CLASSES = ["Pública", "Interna", "Confidencial", "Crítica"];

  const PRECEDENCIA_PADRAO = [
    "R14", "R13", "R03", "R05", "R04", "R06", "R02", "R01",
    "R11", "R10", "R07", "R09", "R08", "R12",
  ];

  // ----------------------------------------------------------------
  // Predicados que o motor Python obtém das dataclasses
  // ----------------------------------------------------------------

  const aprovada = f => !!f && !String(f.status || "").toLowerCase().startsWith("não aprovada");
  const publica = f => !!f && String(f.tipo || "").trim().toLowerCase() === "pública";
  const soConteudoPublico = f =>
    !!f && String(f.status || "").toLowerCase().includes("apenas para conteúdo público");

  const eCredencial = t => !!t && String(t.categoria || "").trim().toLowerCase() === "credencial";
  const eDadoPessoal = t =>
    !!t && String(t.categoria || "").trim().toLowerCase().startsWith("dados pessoais");
  const eCodigo = t => !!t && t.id === "INF-01";
  const eFinanceiroNaoDivulgado = t => !!t && t.id === "INF-09";

  // ----------------------------------------------------------------

  class Motor {
    /**
     * @param {object} base      { ferramentas: [...], tipos: [...], regras: [...] } do payload
     * @param {object} politica  a política candidata (ver cabeçalho)
     */
    constructor(base, politica) {
      this.ferramentasBase = Object.fromEntries(base.ferramentas.map(f => [f.id, f]));
      this.tipos = Object.fromEntries(base.tipos.map(t => [t.id, t]));
      this.regrasBase = Object.fromEntries(base.regras.map(r => [r.id, r]));
      this.aplicar(politica);
    }

    /** Troca a política sem reconstruir os índices. */
    aplicar(politica) {
      const p = politica || {};
      this.pol = {
        regras: p.regras || {},
        precedencia: p.precedencia && p.precedencia.length ? p.precedencia : PRECEDENCIA_PADRAO,
        ferramentas: p.ferramentas || {},
        limiteVolume: Number.isFinite(p.limiteVolume) ? p.limiteVolume : 10,
      };
      // ferramentas com o status da política candidata sobreposto
      this.ferramentas = {};
      for (const [id, f] of Object.entries(this.ferramentasBase)) {
        const sobrepor = this.pol.ferramentas[id];
        this.ferramentas[id] = sobrepor ? { ...f, status: sobrepor.status } : f;
      }
      return this;
    }

    /** Nível e ação de uma regra, segundo a política em vigor. */
    _r(rid) {
      const editada = this.pol.regras[rid] || {};
      const original = this.regrasBase[rid] || {};
      return {
        nivel: editada.nivel || original.nivel || "Médio",
        acao: editada.acao || original.acao || "",
        ativa: editada.ativa !== false,
      };
    }

    _achado(rid, titulo, motivo, opts) {
      const r = this._r(rid);
      if (!r.ativa) return null;                      // regra desligada não produz achado
      const o = opts || {};
      return {
        regra: rid,
        nivel: o.nivelFixo || r.nivel,
        titulo,
        motivo,
        acao: r.acao,
        contextual: !!o.contextual,
      };
    }

    // --------------------------------------------------------------

    avaliar(entrada) {
      const { ferramentaId, informacaoId, sensibilidade } = entrada;
      const qtd = entrada.qtd || 1;
      const foraHorario = !!entrada.foraHorario;
      const rastreavel = entrada.rastreavel !== false;

      const achados = [];
      let lacuna = null;
      const ferr = this.ferramentas[ferramentaId];
      const info = this.tipos[informacaoId];
      const sens = (sensibilidade || "").trim();

      // 1. rastreabilidade -----------------------------------------
      if (!rastreavel || !ferr) {
        const a = this._achado("R14", "Rastreabilidade insuficiente",
          "O evento não tem usuário, ferramenta ou data confiáveis. Sem isso não é possível " +
          "atribuir risco — e atribuir mesmo assim seria inventar.", { nivelFixo: "REVISAR" });
        if (a) return { nivel: "REVISAR", regra: "R14", achados: [a], lacuna: null };
      }
      if (!info || CLASSES.indexOf(sens) === -1) {
        const a = this._achado("R13", "Classificação ausente ou insuficiente",
          "O conteúdo não tem classificação suficiente para decidir. A política manda revisar, " +
          "não arbitrar um nível.", { nivelFixo: "REVISAR" });
        if (a) return { nivel: "REVISAR", regra: "R13", achados: [a], lacuna: null };
      }
      if (!ferr || !info) return { nivel: "Baixo", regra: "—", achados: [], lacuna: null };

      const ap = aprovada(ferr);
      const push = a => { if (a) achados.push(a); };

      // 2. credencial, em qualquer ferramenta ----------------------
      if (eCredencial(info)) {
        push(this._achado("R03", "Credencial ou segredo identificado",
          `${info.nome} foi inserido em ${ferr.nome}. A regra R03 não abre exceção para ` +
          "ferramenta aprovada — o caso CV12 confirma isso. A credencial deve ser considerada " +
          "comprometida."));
      }

      // 3. ferramenta não aprovada ---------------------------------
      if (!ap) {
        if (sens === "Crítica") {
          push(this._achado("R02", "Informação crítica em ferramenta não aprovada",
            `${info.nome} (${sens}) em ${ferr.nome}, que a governança classifica como ` +
            `'${ferr.status}'. Sem contrato corporativo, não há controle de retenção nem ` +
            "garantia sobre uso do conteúdo."));
        } else if (sens === "Confidencial") {
          push(this._achado("R01", "Informação confidencial em ferramenta não aprovada",
            `${info.nome} (${sens}) em ${ferr.nome} ('${ferr.status}').`));
        }

        if (eFinanceiroNaoDivulgado(info) && publica(ferr)) {
          push(this._achado("R05", "Resultado financeiro não divulgado em ferramenta pública",
            "Informação financeira ainda não divulgada ao mercado. Além do risco de vazamento, " +
            "há exposição a uso indevido de informação privilegiada."));
        }
        if (eDadoPessoal(info) && publica(ferr)) {
          push(this._achado("R04", "Dado pessoal identificável em IA pública",
            `${info.nome} é dado pessoal. A resposta não é só de segurança: aciona o ` +
            "procedimento de privacidade, com avaliação de comunicação ao titular e à autoridade."));
        }
        if (eCodigo(info) && publica(ferr) && sens === "Confidencial") {
          push(this._achado("R06", "Código confidencial em ferramenta pública",
            "R06 prevê nível Alto, mas R01 já classifica o mesmo fato como Crítico. Prevalece o " +
            "mais severo; R06 fica registrada porque indica o que precisa ser avaliado: " +
            "exposição de propriedade intelectual."));
        }

        if (sens === "Interna" || sens === "Pública") {
          lacuna = `Informação ${sens} em ferramenta não aprovada não tem regra própria na ` +
                   "política. R08 e R09 falam explicitamente em 'ferramenta aprovada'.";
          if (sens === "Pública") {
            push(this._achado("R08", "Informação pública (ferramenta não aprovada)",
              "O caso CV14 confirma que informação pública em ferramenta não aprovada fica em " +
              "Baixo. Mas a regra citada, R08, pressupõe ferramenta aprovada — a classificação " +
              "está certa e a citação, não."));
          } else {
            push(this._achado("R09", "Informação interna (ferramenta não aprovada)",
              "Sem regra própria na política. R09 pressupõe ferramenta aprovada; aplicá-la aqui " +
              "mantém o nível Baixo mas registra uma justificativa que não corresponde ao fato."));
          }
        }
      // 4. ferramenta aprovada -------------------------------------
      } else {
        if (qtd >= this.pol.limiteVolume && (sens === "Confidencial" || sens === "Crítica")) {
          push(this._achado("R11", `Volume elevado — ${qtd} itens`,
            `${qtd} itens de informação ${sens} num único uso. Volume desse porte não é ` +
            "consulta pontual: é transferência de acervo."));
        }

        if (sens === "Crítica") {
          push(this._achado("R10", "Informação crítica em ambiente aprovado",
            `${info.nome} (${sens}) em ${ferr.nome}. Ambiente aprovado reduz a exposição, mas ` +
            "informação crítica exige finalidade validada e registro — a política não a libera " +
            "por padrão em nenhuma ferramenta."));
        } else if (sens === "Confidencial") {
          push(this._achado("R07", "Confidencial em ferramenta aprovada",
            `Uso previsto pela política: ${info.nome} em ${ferr.nome}, que é '${ferr.status}'. ` +
            "Registrar e validar finalidade e acesso."));
        } else if (sens === "Interna") {
          push(this._achado("R09", "Informação interna em ferramenta aprovada",
            `${info.nome} em ambiente aprovado. Permitido conforme finalidade.`));
        } else {
          push(this._achado("R08", "Informação pública em ferramenta aprovada",
            `${info.nome} em ${ferr.nome}. Registrar sem alerta.`));
        }

        if (soConteudoPublico(ferr) && sens !== "Pública") {
          push(this._achado("R10", "Uso fora da finalidade aprovada da ferramenta",
            `${ferr.nome} é aprovada apenas para conteúdo público, e o conteúdo é ${sens}.`));
        }
      }

      // 5. contexto -------------------------------------------------
      if (foraHorario) {
        push(this._achado("R12", "Uso fora do horário padrão",
          "Registrado fora do horário comercial ou em fim de semana. A própria R12 diz que isso " +
          "não aumenta o risco sozinho — entra como contexto para quem investiga.",
          { contextual: true }));
      }

      // desfecho ----------------------------------------------------
      const prec = this.pol.precedencia;
      const ordem = a => {
        const i = prec.indexOf(a.regra);
        return i === -1 ? prec.length : i;
      };

      const elegiveis = achados.filter(a => !a.contextual);
      if (!elegiveis.length) return { nivel: "Baixo", regra: "—", achados, lacuna };

      const pior = Math.max(...elegiveis.map(a => SEVERIDADE[a.nivel] ?? 0));
      const nivel = Object.keys(SEVERIDADE).find(k => SEVERIDADE[k] === pior) || "Baixo";
      const candidatos = elegiveis.filter(a => (SEVERIDADE[a.nivel] ?? 0) === pior);
      const principal = candidatos.reduce((m, a) => (ordem(a) < ordem(m) ? a : m), candidatos[0]);

      achados.sort((x, y) =>
        (x.contextual ? 1 : 0) - (y.contextual ? 1 : 0) ||
        (SEVERIDADE[y.nivel] ?? 0) - (SEVERIDADE[x.nivel] ?? 0) ||
        ordem(x) - ordem(y));

      return { nivel, regra: principal.regra, achados, lacuna };
    }

    avaliarEvento(e) {
      return this.avaliar({
        ferramentaId: e.ferramenta_id,
        informacaoId: e.informacao_id,
        sensibilidade: e.sensibilidade,
        qtd: e.qtd,
        foraHorario: !!e.fora_horario,
        rastreavel: true,
      });
    }

    avaliarCaso(c) {
      return this.avaliar({
        ferramentaId: c.ferramenta_id,
        informacaoId: c.informacao_id,
        sensibilidade: (c.sensibilidade === "—" || c.sensibilidade === "-") ? "" : c.sensibilidade,
        qtd: c.qtd || 1,
        foraHorario: false,
        rastreavel: !!c.ferramenta_id,
      });
    }
  }

  // ----------------------------------------------------------------
  // Política corrente, extraída do payload
  // ----------------------------------------------------------------

  function politicaDoPayload(D) {
    return {
      regras: Object.fromEntries(D.politica.regras.map(r =>
        [r.id, { nivel: r.nivel, acao: r.acao, ativa: true }])),
      precedencia: D.politica.precedencia.map(x => x.split(" ")[0].trim()),
      ferramentas: Object.fromEntries(D.ferramentas.map(f => [f.id, { status: f.status }])),
      limiteVolume: 10,
    };
  }

  function clonar(p) {
    return JSON.parse(JSON.stringify(p));
  }

  global.ESPIA_MOTOR = { Motor, politicaDoPayload, clonar, SEVERIDADE, PRECEDENCIA_PADRAO };
})(window);
