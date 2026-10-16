// GerencIA · borda — background (service worker no Chrome/Edge, event page no Firefox).
//
// Recebe eventos do content script, descobre o usuário do Windows via host de
// mensagens nativas e envia ao coletor. A identidade é resolvida aqui, não na
// página — o content script nunca a vê. Contrato: implantacao/coletores/extensao-gpo.json.

// Constantes de bootstrap (fonte única em config.js; inline aqui porque
// importScripts não é confiável entre Chrome e Firefox).
const AGENTE_PADRAO = "http://macbook-pro.local:8765";
const HOST_NATIVO = "com.starkbank.rastro.identidade";

const api = (typeof browser !== "undefined") ? browser : chrome;

let usuarioCache = null;     // { usuario, fonte } — resolvido uma vez por sessão
let maquinaCache = "";       // nome da máquina (do host nativo) — para a aba Estações
let enviados = 0;            // espelho em memória; o valor durável fica em storage,
                             // porque o navegador mata o service worker e zeraria o contador
api.storage.local.get(["enviados"]).then((s) => { enviados = s.enviados || 0; }).catch(() => {});

// O agente está nesta máquina (modo estação) ou é remoto (modo Mac central)?
function agenteLocal(url) {
  try { const h = new URL(url).hostname; return h === "127.0.0.1" || h === "localhost" || h === "::1"; }
  catch (e) { return false; }
}

async function getAgente() {
  try {
    const s = await api.storage.local.get(["agente", "declarado"]);
    return { url: s.agente || AGENTE_PADRAO, declarado: s.declarado || "" };
  } catch (e) {
    return { url: AGENTE_PADRAO, declarado: "" };
  }
}

// Pergunta ao host nativo do Windows quem é o usuário logado (%USERNAME%) e a
// máquina (%COMPUTERNAME%). Devolve o objeto inteiro do host (ou null).
function identidadeNativa() {
  return new Promise((resolve) => {
    try {
      api.runtime.sendNativeMessage(HOST_NATIVO, { pedido: "usuario" }, (resp) => {
        if (api.runtime.lastError || !resp || !resp.usuario) return resolve(null);
        resolve(resp);
      });
    } catch (e) { resolve(null); }
  });
}

async function resolverUsuario() {
  if (usuarioCache) return usuarioCache;
  const nativo = await identidadeNativa();
  if (nativo) {
    usuarioCache = { usuario: String(nativo.usuario), fonte: "nativo" };
    if (nativo.maquina) maquinaCache = String(nativo.maquina);
  } else {
    const { declarado } = await getAgente();
    usuarioCache = { usuario: declarado || "não identificado", fonte: "declarado" };
  }
  return usuarioCache;
}

// Nome da máquina para o heartbeat: do host nativo quando houver; senão, um id
// estável guardado neste navegador (modo sem host nativo, ex.: Mac central).
async function resolverMaquina() {
  if (maquinaCache) return maquinaCache;
  await resolverUsuario();                 // tenta preencher via host nativo
  if (maquinaCache) return maquinaCache;
  try {
    const s = await api.storage.local.get(["maquina"]);
    if (s.maquina) { maquinaCache = s.maquina; return maquinaCache; }
    maquinaCache = "navegador-" + Math.random().toString(36).slice(2, 8);
    await api.storage.local.set({ maquina: maquinaCache });
  } catch (e) { maquinaCache = "navegador"; }
  return maquinaCache;
}

async function enviar(evento) {
  const { url } = await getAgente();
  const ident = await resolverUsuario();
  const corpo = { ...evento, usuario: ident.usuario, usuario_fonte: ident.fonte };
  try {
    // contrato espia-borda: POST /eventos. Um coletor antigo (só /api/ingest)
    // responde 404 — então cai para a rota legada, para o rollout da extensão
    // não depender de todos os coletores atualizarem ao mesmo tempo.
    const base = url.replace(/\/+$/, "");
    const opts = { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corpo) };
    let r = await fetch(base + "/eventos", opts);
    if (r.status === 404) r = await fetch(base + "/api/ingest", opts);
    if (r.ok) {
      enviados++;
      try { await api.storage.local.set({ enviados }); } catch (e) {}
      badge(enviados);
      const j = await r.json().catch(() => ({}));
      return { ok: true, nivel: j.nivel };
    }
    return { ok: false, status: r.status };
  } catch (e) {
    return { ok: false, erro: String(e).slice(0, 80) };
  }
}

function badge(n) {
  try {
    api.action.setBadgeText({ text: n > 0 ? String(n) : "" });
    api.action.setBadgeBackgroundColor({ color: "#1c4f9c" });
  } catch (e) {}
}

// Heartbeat: avisa o coletor que a extensão está ATIVA nesta máquina. É o que
// acende o farol verde na aba Estações; a ausência dele (com o agente vivo)
// sinaliza extensão desabilitada.
async function enviarHeartbeat() {
  const { url } = await getAgente();
  const ident = await resolverUsuario();
  const maquina = await resolverMaquina();
  let versao = "";
  try { versao = api.runtime.getManifest().version; } catch (e) {}
  const corpo = JSON.stringify({ maquina, fonte: "extensao", usuario: ident.usuario, versao });
  try {
    await fetch(url.replace(/\/+$/, "") + "/api/heartbeat",
                { method: "POST", headers: { "Content-Type": "application/json" }, body: corpo });
  } catch (e) { /* coletor fora do ar: tenta no próximo alarme */ }
}

// Alarme periódico (~5 min) + um disparo ao iniciar/instalar.
try {
  api.alarms.create("heartbeat", { periodInMinutes: 5 });
  api.alarms.onAlarm.addListener((a) => { if (a.name === "heartbeat") enviarHeartbeat(); });
} catch (e) {}
try { api.runtime.onStartup.addListener(enviarHeartbeat); } catch (e) {}
try { api.runtime.onInstalled.addListener(enviarHeartbeat); } catch (e) {}
enviarHeartbeat();   // primeiro sinal assim que o service worker sobe

api.runtime.onMessage.addListener((msg, sender, sendResposta) => {
  if (msg && msg.tipo === "evento") {
    enviarHeartbeat();   // toda captura também confirma que a extensão está viva
    enviar(msg.evento).then((r) => { try { sendResposta(r); } catch (e) {} });
    return true;  // resposta assíncrona
  }
  if (msg && msg.tipo === "status") {
    (async () => {
      const { url } = await getAgente();
      let ident = await resolverUsuario();
      let saude = null;
      try {
        const r = await fetch(url.replace(/\/+$/, "") + "/api/saude");
        saude = r.ok ? await r.json() : null;
      } catch (e) {}
      // Modo estação: o agente roda NESTA máquina, como o usuário logado, e é
      // ele quem carimba a identidade em cada evento (lendo o SO). O host
      // nativo não é necessário aqui — mostramos o que o agente informa.
      if (ident.fonte !== "nativo" && saude && saude.analista_local && agenteLocal(url)) {
        ident = { usuario: saude.analista_local, fonte: "agente-local" };
      }
      try { sendResposta({ agente: url, ident, enviados, saude }); } catch (e) {}
    })();
    return true;
  }
});
