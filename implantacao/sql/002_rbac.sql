-- GerencIA — papéis e acesso.
--
-- O paradoxo do projeto: a ferramenta que vigia o vazamento de informação
-- sensível é, ela própria, um repositório de informação sensível. O acesso a
-- ela precisa ser mais restrito que a média dos sistemas do banco, não menos.
--
-- Quatro papéis, e nenhum deles é "administrador que vê tudo".

BEGIN;
SET search_path TO espia, public;

-- 1. ANALISTA — vê alerta e evidência, não vê identidade fora da sua área.
CREATE ROLE espia_analista NOLOGIN;
GRANT USAGE ON SCHEMA espia TO espia_analista;
GRANT SELECT ON eventos, alertas, ferramentas, tipos_informacao, regras,
                indicadores, achados_auditoria TO espia_analista;
GRANT UPDATE (estado, responsavel, tratado_em, desfecho) ON alertas TO espia_analista;

-- 2. COMPLIANCE — edita a política; NÃO altera desfecho de alerta.
CREATE ROLE espia_compliance NOLOGIN;
GRANT USAGE ON SCHEMA espia TO espia_compliance;
GRANT SELECT ON ALL TABLES IN SCHEMA espia TO espia_compliance;
GRANT INSERT ON politica_versoes TO espia_compliance;
GRANT UPDATE (vigente) ON politica_versoes TO espia_compliance;
GRANT INSERT, UPDATE ON regras TO espia_compliance;

-- 3. AUDITOR — só leitura, inclusive da trilha. Não muda nada, em lugar nenhum.
CREATE ROLE espia_auditor NOLOGIN;
GRANT USAGE ON SCHEMA espia TO espia_auditor;
GRANT SELECT ON ALL TABLES IN SCHEMA espia TO espia_auditor;

-- 4. SERVIÇO — o que os contêineres usam. Escreve evento e alerta, e nada mais.
CREATE ROLE espia_servico NOLOGIN;
GRANT USAGE ON SCHEMA espia TO espia_servico;
GRANT SELECT, INSERT ON eventos, alertas, trilha, indicadores, achados_auditoria
      TO espia_servico;
GRANT UPDATE ON alertas TO espia_servico;
GRANT SELECT ON ferramentas, tipos_informacao, usuarios, regras, politica_versoes
      TO espia_servico;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA espia TO espia_servico;

-- ── segregação por área ──────────────────────────────────────────────────────
-- Um analista de SegInfo do varejo não precisa ver, por padrão, os eventos da
-- mesa de operações. Row Level Security faz isso no banco, e não na aplicação,
-- porque controle de acesso implementado só na tela é contornável pela API.
ALTER TABLE eventos ENABLE ROW LEVEL SECURITY;
ALTER TABLE alertas ENABLE ROW LEVEL SECURITY;

CREATE POLICY analista_por_area ON alertas FOR SELECT TO espia_analista
  USING (area = ANY (string_to_array(current_setting('espia.areas', true), ',')));
CREATE POLICY analista_evento_por_area ON eventos FOR SELECT TO espia_analista
  USING (area = ANY (string_to_array(current_setting('espia.areas', true), ',')));

-- Auditor e compliance veem tudo — é a função deles, e cada consulta que fazem
-- fica registrada na trilha.
CREATE POLICY auditor_tudo   ON alertas FOR SELECT TO espia_auditor   USING (true);
CREATE POLICY auditor_ev     ON eventos FOR SELECT TO espia_auditor   USING (true);
CREATE POLICY compliance_al  ON alertas FOR SELECT TO espia_compliance USING (true);
CREATE POLICY compliance_ev  ON eventos FOR SELECT TO espia_compliance USING (true);
CREATE POLICY servico_tudo   ON eventos TO espia_servico USING (true) WITH CHECK (true);
CREATE POLICY servico_al     ON alertas TO espia_servico USING (true) WITH CHECK (true);

-- ── a exceção do direito de resposta ─────────────────────────────────────────
-- O modelo de risco preditivo é preventivo, nunca punitivo, e a pessoa tem
-- direito de ver o próprio score. Esta visão é o que dá esse direito.
CREATE VIEW meu_risco AS
  SELECT usuario_id, max(score_modelo) AS score, count(*) AS eventos,
         max(ocorrido_em) AS ultimo
    FROM eventos
   WHERE usuario_id = current_setting('espia.usuario', true)
   GROUP BY usuario_id;

COMMIT;
