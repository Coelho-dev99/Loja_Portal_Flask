-- =====================================================
-- Migracao 05: remove a coluna CPF dos clientes
--
-- O site nunca pediu nem gravou CPF. Manter uma coluna de dado sensivel sem
-- uso so aumenta o estrago se o banco vazar (LGPD: colete so o necessario).
--
-- Rode UMA vez, no banco da loja, pelo Query Tool do pgAdmin, como administrador.
-- Se algum cliente tiver CPF gravado (alguem inseriu na mao), o script PARA
-- sem apagar nada, para voce decidir o que fazer com esses dados.
-- Pode rodar de novo sem problema.
-- =====================================================

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = 'clientes' AND column_name = 'cpf'
    ) THEN
        IF EXISTS (SELECT 1 FROM clientes WHERE cpf IS NOT NULL) THEN
            RAISE EXCEPTION 'Ha clientes com CPF gravado. Nada foi apagado. Confira com: SELECT id, nome FROM clientes WHERE cpf IS NOT NULL;';
        END IF;
    END IF;
END
$$;

DROP INDEX IF EXISTS uq_clientes_cpf;
ALTER TABLE clientes DROP COLUMN IF EXISTS cpf;

COMMIT;
