"""
GerencIA — Acervo sintético de informação corporativa.

ATENÇÃO: todo o conteúdo deste módulo é FICTÍCIO, gerado para demonstração
do Desafio 2 da Stark Bank. Nomes de pessoas, clientes, valores, números de
contrato e trechos de documento são inventados. Nenhum dado real de qualquer
instituição foi utilizado.

O acervo cumpre o papel do que, numa implantação real, viria dos conectores
de repositório (SharePoint, Drive, Confluence, repositório jurídico, ERP,
Git). Cada ativo é classificado UMA vez, na origem — e todo evento de IA que
casar com ele herda essa classificação. É o que evita classificar prompt a
prompt.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Ativo:
    id: str
    nome: str
    categoria: str          # chave de categorias_informacao no politica.yaml
    classificacao: str      # publico | interno | confidencial | critico
    area_dona: str
    repositorio: str
    texto: str              # conteúdo sintético — descartado após o fingerprint


ACERVO: list[Ativo] = [
    # ---------------- PÚBLICO ----------------
    Ativo(
        id="ATV-001",
        nome="Documentação pública da API de Cobrança",
        categoria="propriedade_intelectual",
        classificacao="publico",
        area_dona="Engenharia",
        repositorio="docs-publicas",
        texto=(
            "A API de cobrança permite criar invoices com vencimento, multa e juros "
            "configuráveis. Cada invoice gera automaticamente um código Pix copia e cola "
            "e um boleto registrado. A conciliação é devolvida por webhook no evento "
            "invoice.credited, contendo o identificador da cobrança, o valor efetivamente "
            "pago e a data de liquidação. O ambiente sandbox usa as mesmas rotas com "
            "credenciais de teste e não movimenta recursos financeiros reais."
        ),
    ),
    Ativo(
        id="ATV-002",
        nome="Release notes públicas — SDK Python v3",
        categoria="propriedade_intelectual",
        classificacao="publico",
        area_dona="Engenharia",
        repositorio="docs-publicas",
        texto=(
            "A versão três do SDK Python passa a suportar autenticação por chave privada "
            "em curva elíptica, adiciona paginação por cursor em todos os recursos de "
            "listagem e remove a dependência de bibliotecas de criptografia compiladas. "
            "A migração a partir da versão dois exige apenas a substituição do objeto de "
            "projeto e a revisão das chamadas de listagem que assumiam offset numérico."
        ),
    ),

    # ---------------- INTERNO ----------------
    Ativo(
        id="ATV-010",
        nome="Runbook de incidentes de plataforma",
        categoria="propriedade_intelectual",
        classificacao="interno",
        area_dona="Engenharia",
        repositorio="wiki-interna",
        texto=(
            "Ao receber alerta de latência acima de oitocentos milissegundos no serviço de "
            "liquidação, o plantonista deve primeiro verificar a fila de mensagens pendentes "
            "e o consumo de conexões do banco primário. Se a fila estiver acima de cinquenta "
            "mil mensagens, acionar o failover manual para a réplica da região secundária e "
            "comunicar no canal de incidentes. A abertura de post mortem é obrigatória para "
            "qualquer indisponibilidade acima de cinco minutos em horário de liquidação."
        ),
    ),
    Ativo(
        id="ATV-011",
        nome="Política interna de uso de Inteligência Artificial",
        categoria="estrategica",
        classificacao="interno",
        area_dona="Segurança da Informação",
        repositorio="wiki-interna",
        texto=(
            "O uso de ferramentas de inteligência artificial generativa é permitido e "
            "incentivado dentro dos limites desta política. Informação classificada como "
            "pública ou interna pode ser utilizada em qualquer ferramenta homologada pelo "
            "Comitê de Inteligência Artificial. Informação confidencial somente em "
            "ferramentas corporativas com acordo de tratamento de dados assinado. "
            "Informação crítica exige aprovação prévia do Comitê e registro da finalidade. "
            "O descumprimento sujeita o colaborador às medidas disciplinares previstas no "
            "código de conduta."
        ),
    ),
    Ativo(
        id="ATV-012",
        nome="Manual de onboarding de pessoas desenvolvedoras",
        categoria="dados_pessoais",
        classificacao="interno",
        area_dona="People",
        repositorio="drive-people",
        texto=(
            "Nos primeiros cinco dias a pessoa recém contratada recebe acesso ao repositório "
            "de código, ao ambiente de sandbox e ao canal do seu time. O acesso a ambientes "
            "de produção é concedido apenas após a conclusão do treinamento de segurança e "
            "da assinatura do termo de confidencialidade. O buddy designado acompanha as "
            "duas primeiras semanas e valida a primeira entrega em produção."
        ),
    ),

    # ---------------- CONFIDENCIAL ----------------
    Ativo(
        id="ATV-020",
        nome="Contrato de correspondente bancário — Cliente Arcadia Varejo",
        categoria="juridico",
        classificacao="confidencial",
        area_dona="Jurídico",
        repositorio="repositorio-juridico",
        texto=(
            "Pelo presente instrumento particular, a instituição contratante e a empresa "
            "Arcadia Varejo Distribuidora, inscrita no cadastro nacional de pessoa jurídica, "
            "ajustam a prestação de serviços de correspondente bancário pelo prazo de trinta "
            "e seis meses, renovável automaticamente por iguais períodos. A remuneração será "
            "calculada sobre o volume financeiro liquidado, aplicada a alíquota escalonada "
            "prevista no anexo dois, com piso mensal garantido. A rescisão imotivada por "
            "qualquer das partes exige aviso prévio de noventa dias e não gera multa "
            "compensatória, ressalvadas as obrigações já constituídas."
        ),
    ),
    Ativo(
        id="ATV-021",
        nome="Proposta comercial — Conta Enterprise Meridian Logística",
        categoria="comercial",
        classificacao="confidencial",
        area_dona="Comercial",
        repositorio="crm-anexos",
        texto=(
            "Proposta comercial para a Meridian Logística contemplando conta empresarial com "
            "isenção de tarifa de manutenção, quinze mil transações Pix mensais incluídas e "
            "taxa de zero vírgula trinta e cinco por cento sobre recebimentos via cartão. "
            "A margem projetada para a operação é de dezoito por cento no primeiro ano, "
            "considerando o custo de liquidação e o rateio de estrutura. O desconto oferecido "
            "está três pontos percentuais acima da política padrão e depende de aprovação do "
            "comitê comercial. A proposta concorre diretamente com oferta apresentada por "
            "instituição concorrente na semana anterior."
        ),
    ),
    Ativo(
        id="ATV-022",
        nome="Roadmap de produto 2027 — Pix Automático e Crédito Embutido",
        categoria="estrategica",
        classificacao="confidencial",
        area_dona="Produto",
        repositorio="notion-produto",
        texto=(
            "O roadmap para o exercício seguinte concentra três apostas. A primeira é o Pix "
            "automático para assinaturas recorrentes, com previsão de disponibilidade geral "
            "no segundo trimestre e meta de penetração em quarenta por cento da base de "
            "clientes com faturamento recorrente. A segunda é o crédito embutido no fluxo de "
            "recebíveis, com limite calculado a partir do histórico de liquidação do próprio "
            "cliente. A terceira é a reformulação do cartão corporativo com controles de "
            "política de gasto por centro de custo. Nenhuma dessas iniciativas foi comunicada "
            "ao mercado e a divulgação antecipada compromete a vantagem competitiva."
        ),
    ),
    Ativo(
        id="ATV-023",
        nome="Código-fonte — serviço de conciliação de recebíveis",
        categoria="propriedade_intelectual",
        classificacao="confidencial",
        area_dona="Engenharia",
        repositorio="git-monorepo",
        texto=(
            "O serviço de conciliação consome o stream de eventos de liquidação e aplica a "
            "máquina de estados de recebível. Cada evento é idempotente pela chave composta "
            "de identificador de cobrança e data de liquidação. Em caso de divergência entre "
            "o valor esperado e o valor liquidado, o registro é encaminhado para a fila de "
            "exceção e um alerta é emitido para o time financeiro. A reprocessagem é feita a "
            "partir do offset persistido no armazenamento de checkpoint, garantindo que "
            "nenhum evento seja perdido em caso de reinício do consumidor."
        ),
    ),
    Ativo(
        id="ATV-024",
        nome="Ata do Comitê de Crédito — sessão ordinária",
        categoria="estrategica",
        classificacao="confidencial",
        area_dona="Risco e Crédito",
        repositorio="repositorio-juridico",
        texto=(
            "Reunido o comitê de crédito, foram apreciadas sete propostas de limite acima da "
            "alçada da mesa. Aprovadas cinco, com condicionantes de garantia e revisão "
            "trimestral. Rejeitadas duas em razão de concentração setorial e de deterioração "
            "do indicador de inadimplência do segmento. O comitê determinou a redução do apetite "
            "para o setor de comércio varejista não alimentar em vinte por cento até a próxima "
            "revisão de política."
        ),
    ),
    Ativo(
        id="ATV-025",
        nome="Projeção financeira e plano de capital",
        categoria="estrategica",
        classificacao="confidencial",
        area_dona="Financeiro",
        repositorio="drive-financeiro",
        texto=(
            "A projeção de receita para o próximo exercício considera crescimento de trinta e "
            "dois por cento na receita de serviços e estabilidade na margem financeira, com "
            "o índice de Basileia mantido acima do mínimo regulatório em todos os cenários "
            "simulados. O cenário adverso contempla elevação de duzentos pontos base na curva "
            "de juros e aumento de quarenta por cento na provisão para perdas esperadas. O "
            "plano de capital prevê retenção integral do resultado no primeiro semestre."
        ),
    ),
    Ativo(
        id="ATV-026",
        nome="Laudo de teste de intrusão — ambiente de liquidação",
        categoria="propriedade_intelectual",
        classificacao="confidencial",
        area_dona="Segurança da Informação",
        repositorio="drive-seguranca",
        texto=(
            "O teste de intrusão executado no ambiente de liquidação identificou três achados "
            "de severidade média e um de severidade alta. O achado de severidade alta refere-se "
            "à exposição de endpoint administrativo sem restrição por lista de endereços, "
            "permitindo enumeração de identificadores internos. Recomenda-se a implementação "
            "imediata de restrição de rede e a rotação das credenciais de serviço envolvidas. "
            "Os achados de severidade média envolvem cabeçalhos de segurança ausentes e "
            "verbosidade excessiva em mensagens de erro."
        ),
    ),

    # ---------------- CRÍTICO ----------------
    Ativo(
        id="ATV-030",
        nome="Base de clientes PJ — segmento Enterprise",
        categoria="clientes",
        classificacao="critico",
        area_dona="Comercial",
        repositorio="data-warehouse",
        texto=(
            "Extração da base de clientes pessoa jurídica do segmento enterprise contendo "
            "razão social, cadastro nacional de pessoa jurídica, nome e documento do "
            "representante legal, endereço de correspondência, volume financeiro transacionado "
            "nos últimos doze meses, saldo médio em conta e classificação interna de risco. "
            "A extração está sujeita ao sigilo de operações bancárias e seu compartilhamento "
            "externo depende de autorização expressa do titular ou de determinação legal."
        ),
    ),
    Ativo(
        id="ATV-031",
        nome="Modelo de score de crédito v4 — variáveis e pesos",
        categoria="financeiro_regulado",
        classificacao="critico",
        area_dona="Risco e Crédito",
        repositorio="git-modelos",
        texto=(
            "O modelo de score de crédito na quarta versão combina vinte e três variáveis "
            "agrupadas em quatro blocos: comportamento transacional na própria instituição, "
            "histórico de inadimplência no sistema financeiro, indicadores setoriais e "
            "características cadastrais. O bloco de comportamento transacional responde por "
            "quarenta e um por cento do poder discriminante do modelo, com destaque para a "
            "razão entre saldo médio e volume liquidado e para a volatilidade do fluxo de "
            "recebíveis. Os pontos de corte por faixa e os pesos calibrados constituem "
            "informação proprietária cuja divulgação permitiria engenharia reversa da política "
            "de crédito e induziria seleção adversa."
        ),
    ),
    Ativo(
        id="ATV-032",
        nome="Relatório de operações suspeitas — PLD/FT",
        categoria="financeiro_regulado",
        classificacao="critico",
        area_dona="Compliance",
        repositorio="drive-compliance",
        texto=(
            "Relatório consolidado das operações sinalizadas pelo monitoramento de prevenção à "
            "lavagem de dinheiro no período. Foram analisadas trezentas e quarenta sinalizações, "
            "das quais dezenove resultaram em comunicação ao órgão regulador. As tipologias "
            "predominantes envolvem fracionamento de valores, incompatibilidade entre movimentação "
            "e capacidade econômica declarada e uso de contas de passagem. A identificação dos "
            "titulares envolvidos e o conteúdo das comunicações estão submetidos a sigilo legal "
            "e não podem ser compartilhados fora do comitê de prevenção."
        ),
    ),
    Ativo(
        id="ATV-033",
        nome="Folha de pagamento e tabela salarial",
        categoria="dados_pessoais",
        classificacao="critico",
        area_dona="People",
        repositorio="sistema-folha",
        texto=(
            "Planilha consolidada da folha de pagamento contendo nome completo, cadastro de "
            "pessoa física, cargo, nível, salário base, bônus variável, participação em "
            "resultados e dados bancários de crédito de cada pessoa colaboradora. O acesso é "
            "restrito à liderança de People e à diretoria financeira, com registro de acesso "
            "individual e revisão trimestral de permissões."
        ),
    ),
    Ativo(
        id="ATV-034",
        nome="Extrato transacional de cliente — investigação em curso",
        categoria="clientes",
        classificacao="critico",
        area_dona="Compliance",
        repositorio="drive-compliance",
        texto=(
            "Extrato detalhado de movimentação transacional de titular específico, extraído "
            "para instrução de apuração interna. Contém data e horário de cada operação, "
            "contraparte, chave Pix utilizada, valor, canal de origem e endereço de rede do "
            "dispositivo. O documento é coberto por sigilo de operações bancárias e sua "
            "circulação está limitada aos membros designados da apuração."
        ),
    ),
    Ativo(
        id="ATV-035",
        nome="Chaves de integração e segredos de ambiente",
        categoria="propriedade_intelectual",
        classificacao="critico",
        area_dona="Engenharia",
        repositorio="cofre-segredos",
        texto=(
            "Inventário de credenciais de integração dos ambientes produtivos, incluindo chaves "
            "privadas de assinatura de requisição, tokens de acesso aos provedores de "
            "infraestrutura e segredos de conexão com o banco de dados primário. A rotação é "
            "automática a cada noventa dias e qualquer exposição deve ser tratada como incidente "
            "de severidade máxima com revogação imediata."
        ),
    ),
    Ativo(
        id="ATV-036",
        nome="Dossiê de due diligence — aquisição em negociação",
        categoria="estrategica",
        classificacao="critico",
        area_dona="Financeiro",
        repositorio="drive-financeiro",
        texto=(
            "Dossiê de auditoria prévia relativo à sociedade alvo em negociação, contendo "
            "estrutura societária, contingências trabalhistas e tributárias mapeadas, "
            "múltiplo de avaliação proposto e cronograma de fechamento. A operação não foi "
            "comunicada ao mercado. O vazamento desta informação configuraria uso indevido de "
            "informação privilegiada e comprometeria a negociação em andamento."
        ),
    ),
]


ACERVO_POR_ID: dict[str, Ativo] = {a.id: a for a in ACERVO}
