// Configuração do GerencIA · borda (coletor de borda do GerencIA).
//
// AGENTE_PADRAO: onde o coletor escuta, visto de dentro do Windows.
// Na rede compartilhada do Parallels o Mac host é 10.211.55.2 e o coletor
// sobe na porta 8765. O popup permite trocar isso e guarda em storage.
// Em produção estes valores vêm da política de GPO
// (implantacao/coletores/extensao-gpo.json: ingestao_url, dominios_monitorados_url).
const RASTRO = {
  AGENTE_PADRAO: "http://10.211.55.2:8765",

  // Domínio → nome amigável da ferramenta. O status (aprovada/não) é decisão
  // da empresa e é resolvido no AGENTE, não aqui — a extensão só observa.
  FERRAMENTAS: {
    "chatgpt.com": "ChatGPT",
    "chat.openai.com": "ChatGPT",
    "claude.ai": "Claude",
    "gemini.google.com": "Gemini",
    "copilot.microsoft.com": "Copilot",
    "m365.cloud.microsoft": "Copilot",
    "chat.deepseek.com": "DeepSeek",
    "perplexity.ai": "Perplexity",
    "www.perplexity.ai": "Perplexity",
    "poe.com": "Poe",
    "huggingface.co": "HuggingChat",
    "meta.ai": "Meta AI",
    "www.meta.ai": "Meta AI",
    "grok.com": "Grok",
  },

  // Nome do host de mensagens nativas que informa o usuário do Windows.
  HOST_NATIVO: "com.starkbank.rastro.identidade",
};

// disponível tanto para service worker quanto para content script
if (typeof self !== "undefined") self.RASTRO = RASTRO;
