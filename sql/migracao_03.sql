-- =====================================================
-- Migracao 03: carrinho de compras sem login
-- Rode UMA vez, no banco loja_portal, pelo Query Tool do pgAdmin.
-- (Pode rodar de novo sem problema: nao altera nada se a tabela ja existe.)
-- =====================================================

BEGIN;

CREATE TABLE IF NOT EXISTS carrinhos (
    token          VARCHAR(64) PRIMARY KEY,
    itens          JSONB       NOT NULL DEFAULT '[]',
    criado_em      TIMESTAMP   NOT NULL DEFAULT NOW(),
    atualizado_em  TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_carrinhos_atualizado ON carrinhos (atualizado_em);

COMMIT;
