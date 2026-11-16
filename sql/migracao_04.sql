-- =====================================================
-- Migracao 04: conexao com o Melhor Envio (frete automatico)
-- Rode UMA vez, no banco loja_portal, pelo Query Tool do pgAdmin.
-- (Pode rodar de novo sem problema: nao altera nada se a tabela ja existe.)
-- =====================================================

BEGIN;

CREATE TABLE IF NOT EXISTS integracoes (
    nome           VARCHAR(40) PRIMARY KEY,
    access_token   TEXT        NOT NULL,
    refresh_token  TEXT        NOT NULL,
    expira_em      TIMESTAMP   NOT NULL,   -- horario UTC
    atualizado_em  TIMESTAMP   NOT NULL DEFAULT NOW()
);

COMMIT;
