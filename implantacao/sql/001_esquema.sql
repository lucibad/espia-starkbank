-- EspIA — esquema PostgreSQL.
--
-- Roda uma vez, no primeiro `up`, pelo docker-entrypoint-initdb.d.
-- É a versão de produção do esquema que o protótipo cria em SQLite: as mesmas
-- entidades, com o que só faz sentido em produção — partição por mês,
-- imutabilidade da trilha, versionamento de política e retenção declarada.
--
-- Três milhões e seiscentas mil linhas por ano é uma tabela PostgreSQL comum.
-- Não há Kafka, não há data lake, e isso é decisão de engenharia, não economia.

BEGIN;

CREATE SCHEMA IF NOT EXISTS espia;
SET search_path TO espia, public;

-- ── vocabulário ──────────────────────────────────────────────────────────────
-- Os níveis vêm da planilha da organização, não do código. REVISAR não é um
-- nível de risco: é a recusa de atribuir um, quando falta rastreabilidade.
CREATE TYPE nivel_risco AS ENUM ('Baixo', 'Médio', 'Alto', 'Crítico', 'REVISAR');
CREATE TYPE estado_alerta AS ENUM ('Aberto', 'Em análise', 'Tratado', 'Descartado');

-- ── cadastros ────────────────────────────────────────────────────────────────
CREATE TABLE ferramentas (
  id           text PRIMARY KEY,
  nome         text NOT NULL,
  tipo         text,
  status       text NOT NULL,              -- Aprovada · Não aprovada · Aprovada apenas para conteúdo público
  aprovada     boolean GENERATED ALWAYS AS (status = 'Aprovada') STORED,
  publica      boolean NOT NULL DEFAULT false,
  logs         text,
  controles    text,
  finalidade   text,
  descoberta_em timestamptz,               -- ferramenta achada pelo coletor, fora do cadastro
  atualizado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE tipos_informacao (
  id            text PRIMARY KEY,
  nome          text NOT NULL,
  categoria     text,
  classificacao text NOT NULL,             -- Pública · Interna · Confidencial · Crítica
  area_tipica   text,
  atualizado_em timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE usuarios (
  id       text PRIMARY KEY,
  nome     text,
  area     text,
  cargo    text,
  perfil   text,
  status   text,
  sso_sub  text UNIQUE,                    -- sujeito do OIDC; é por aqui que o enriquecedor resolve
  ativo    boolean NOT NULL DEFAULT true
);
CREATE INDEX idx_usuarios_area ON usuarios (area);

-- ── política ─────────────────────────────────────────────────────────────────
-- A política é versionada. Um alerta de junho tem de poder ser relido com a
-- política que valia em junho — sem isso, a trilha de auditoria não se sustenta.
CREATE TABLE politica_versoes (
  id           bigserial PRIMARY KEY,
  publicada_em timestamptz NOT NULL DEFAULT now(),
  autor        text NOT NULL,
  nota         text,
  conteudo     jsonb NOT NULL,             -- regras, precedência, ferramentas, limites
  hash         text NOT NULL,
  vigente      boolean NOT NULL DEFAULT false
);
CREATE UNIQUE INDEX uq_politica_vigente ON politica_versoes (vigente) WHERE vigente;

CREATE TABLE regras (
  id        text PRIMARY KEY,              -- R01..R14, R15+ para as propostas
  tema      text,
  texto     text NOT NULL,
  nivel     nivel_risco,
  acao      text,
  ativa     boolean NOT NULL DEFAULT true,
  ordem     integer                        -- posição na precedência declarada
);

-- ── eventos ──────────────────────────────────────────────────────────────────
-- Particionada por mês: a consulta é quase sempre por janela de tempo, e o
-- expurgo por retenção vira DROP PARTITION em vez de DELETE de milhões de linhas.
CREATE TABLE eventos (
  id             text NOT NULL,
  ocorrido_em    timestamptz NOT NULL,
  recebido_em    timestamptz NOT NULL DEFAULT now(),
  fora_horario   boolean NOT NULL DEFAULT false,
  usuario_id     text REFERENCES usuarios(id),
  area           text,
  ferramenta_id  text REFERENCES ferramentas(id),
  informacao_id  text REFERENCES tipos_informacao(id),
  sensibilidade  text,
  forma_uso      text,
  qtd_itens      integer NOT NULL DEFAULT 1,
  finalidade     text,
  origem         text NOT NULL,            -- DLP · SWG · gateway · extensão · SDK
  assinatura     bytea,                    -- MinHash/SimHash. O CONTEÚDO nunca é gravado.
  risco          nivel_risco,
  regra          text,
  achados        jsonb,                    -- a cadeia de evidências inteira
  politica_id    bigint REFERENCES politica_versoes(id),
  score_modelo   real,
  teste          boolean NOT NULL DEFAULT false,
  PRIMARY KEY (id, ocorrido_em)
) PARTITION BY RANGE (ocorrido_em);

CREATE INDEX idx_ev_ocorrido  ON eventos (ocorrido_em DESC);
CREATE INDEX idx_ev_risco     ON eventos (risco) WHERE risco IN ('Alto','Crítico','REVISAR');
CREATE INDEX idx_ev_info      ON eventos (informacao_id);   -- a BUSCA REVERSA vive deste índice
CREATE INDEX idx_ev_usuario   ON eventos (usuario_id);
CREATE INDEX idx_ev_ferramenta ON eventos (ferramenta_id);

-- Partições do ano corrente e do próximo trimestre. A rotina mensal cria as
-- seguintes; a falta de partição futura derruba a ingestão, então isso é alarme.
DO $$
DECLARE inicio date := date_trunc('month', now())::date - interval '3 months';
        i integer;
BEGIN
  FOR i IN 0..17 LOOP
    EXECUTE format(
      'CREATE TABLE IF NOT EXISTS eventos_%s PARTITION OF eventos
         FOR VALUES FROM (%L) TO (%L)',
      to_char(inicio + (i || ' months')::interval, 'YYYYMM'),
      (inicio + (i     || ' months')::interval)::date,
      (inicio + (i + 1 || ' months')::interval)::date);
  END LOOP;
END $$;

-- ── alertas ──────────────────────────────────────────────────────────────────
CREATE TABLE alertas (
  id             text PRIMARY KEY,
  evento_id      text NOT NULL,
  ocorrido_em    timestamptz NOT NULL,
  criado_em      timestamptz NOT NULL DEFAULT now(),
  usuario_id     text,
  area           text,
  ferramenta_id  text,
  informacao_id  text,
  risco          nivel_risco NOT NULL,
  regra          text,
  evidencia      text,
  prioridade     real,                     -- do modelo 7.3; NULL enquanto não houver modelo
  estado         estado_alerta NOT NULL DEFAULT 'Aberto',
  responsavel    text,
  -- Achado A-05: 47 alertas "Tratado" sem data de tratamento tornam o SLA de
  -- 24 h inapurável. Aqui o carimbo é obrigatório para fechar. Proposta R17.
  tratado_em     timestamptz,
  desfecho       text,                     -- procede · não procede · aceito com mascaramento
  notificado_em  timestamptz,
  CONSTRAINT alerta_tratado_tem_data
    CHECK (estado NOT IN ('Tratado','Descartado') OR tratado_em IS NOT NULL)
);
CREATE INDEX idx_al_estado ON alertas (estado, risco, criado_em DESC);
CREATE INDEX idx_al_area   ON alertas (area);

-- ── trilha de auditoria ──────────────────────────────────────────────────────
-- Append-only de verdade: a regra abaixo faz o banco recusar UPDATE e DELETE.
-- Quem audita o auditor é esta tabela.
CREATE TABLE trilha (
  id         bigserial PRIMARY KEY,
  em         timestamptz NOT NULL DEFAULT now(),
  ator       text NOT NULL,
  acao       text NOT NULL,                -- login · consulta · exportação · publicação de política
  objeto     text,
  detalhe    jsonb,
  ip         inet
);
CREATE RULE trilha_sem_update AS ON UPDATE TO trilha DO INSTEAD NOTHING;
CREATE RULE trilha_sem_delete AS ON DELETE TO trilha DO INSTEAD NOTHING;
CREATE INDEX idx_trilha_em ON trilha (em DESC);

-- ── indicadores e achados ────────────────────────────────────────────────────
CREATE TABLE indicadores (
  nome        text NOT NULL,
  apurado_em  date NOT NULL,
  declarado   text,
  apurado     text,
  confere     boolean,
  observacao  text,
  PRIMARY KEY (nome, apurado_em)
);

CREATE TABLE achados_auditoria (
  id           text PRIMARY KEY,
  detectado_em timestamptz NOT NULL DEFAULT now(),
  familia      text,
  gravidade    text,
  titulo       text NOT NULL,
  resumo       text,
  consequencia text,
  evidencia    text,
  n_eventos    integer,
  eventos      text[],
  estado       text NOT NULL DEFAULT 'Aberto'
);

-- ── retenção ─────────────────────────────────────────────────────────────────
-- Declarada no esquema, não num documento que ninguém lê. Evento: 5 anos, pela
-- guarda de registros; alerta e trilha: 7. Os valores são da política do banco,
-- e este comentário é onde o auditor vai procurar.
COMMENT ON TABLE eventos  IS 'Retenção 5 anos. Expurgo por DROP PARTITION, rotina mensal.';
COMMENT ON TABLE alertas  IS 'Retenção 7 anos.';
COMMENT ON TABLE trilha   IS 'Retenção 7 anos. Append-only por regra do banco.';
COMMENT ON COLUMN eventos.assinatura IS
  'MinHash/SimHash do trecho. O conteúdo original NUNCA é persistido — nem aqui, nem no MinIO.';

COMMIT;
