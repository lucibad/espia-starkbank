const api = (typeof browser !== "undefined") ? browser : chrome;
const $ = (id) => document.getElementById(id);

async function carregar() {
  const s = await api.storage.local.get(["agente", "declarado"]);
  $("url").value = s.agente || "http://10.211.55.2:8765";
  $("decl").value = s.declarado || "";

  api.runtime.sendMessage({ tipo: "status" }, (r) => {
    if (!r) return;
    $("enviados").textContent = r.enviados;
    if (r.ident) {
      $("usuario").textContent = r.ident.usuario;
      const f = r.ident.fonte;
      const confiavel = f === "nativo" || f === "agente-local";
      $("usuario").className = "val " + (confiavel ? "ok" : "off");
      $("campoDecl").hidden = confiavel;
      $("hint").textContent =
        f === "agente-local" ? "Modo estação: identidade lida do Windows pelo agente local, que a carimba em cada evento. Host nativo não é necessário."
        : f === "nativo"     ? "Identidade lida do Windows pelo host nativo — não falsificável pela página."
        : "Agente remoto sem host nativo: identidade é o nome declarado abaixo (falsificável, só teste). Instale o host nativo (borda/EXTENSAO.md).";
    }
    if (r.saude && r.saude.ok) {
      $("saude").textContent = "conectado";
      $("saude").className = "val ok";
    } else {
      $("saude").textContent = "sem conexão";
      $("saude").className = "val off";
    }
  });
}

$("salvar").addEventListener("click", async () => {
  await api.storage.local.set({
    agente: $("url").value.trim(),
    declarado: $("decl").value.trim(),
  });
  $("hint").textContent = "Salvo. Recarregue a aba da ferramenta de IA para aplicar.";
  setTimeout(carregar, 300);
});

carregar();
