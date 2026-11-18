-- =====================================================
-- Usuario do banco SO PARA O SITE (privilegio minimo)
--
-- Por que: hoje o .env usa o usuario "postgres", que e o administrador de
-- todo o servidor. Se alguem conseguir acesso ao site, teria acesso total ao
-- banco. O usuario "loja_app" so consegue LER e GRAVAR os dados da loja:
-- nao cria, nao apaga e nao altera tabelas, nao le outros bancos de dados
-- do servidor e nao mexe em usuarios.
--
-- COMO USAR (uma vez):
--  1. Abra este arquivo e troque TROQUE_ESTA_SENHA por uma senha forte
--     (16+ caracteres, sem aspas simples).
--  2. No pgAdmin, abra o Query Tool CONECTADO NO BANCO DA LOJA (ex.: loja_portal),
--     como administrador (postgres), cole o arquivo inteiro e execute (F5).
--  3. No .env do site, troque para:
--        DB_USER=loja_app
--        DB_PASSWORD="a senha que voce escolheu"
--  4. Reinicie o site e teste.
--
-- Pode rodar de novo sem problema (ele atualiza a senha e os acessos).
-- As migracoes (sql/migracao_*.sql) continuam sendo rodadas por voce, como
-- administrador. O site nunca precisa alterar a estrutura do banco.
-- =====================================================

DO $$
DECLARE
    senha text := 'TROQUE_ESTA_SENHA';
BEGIN
    IF senha = 'TROQUE_ESTA_SENHA' OR length(senha) < 16 THEN
        RAISE EXCEPTION 'Edite o arquivo: troque TROQUE_ESTA_SENHA por uma senha forte de 16 ou mais caracteres.';
    END IF;

    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'loja_app') THEN
        EXECUTE format('CREATE ROLE loja_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', senha);
    ELSE
        EXECUTE format('ALTER ROLE loja_app LOGIN PASSWORD %L NOSUPERUSER NOCREATEDB NOCREATEROLE', senha);
    END IF;

    -- Conecta somente neste banco (o nome e o do banco em que voce esta)
    EXECUTE format('GRANT CONNECT ON DATABASE %I TO loja_app', current_database());
END
$$;

-- So le e grava dados (nada de CREATE, DROP, ALTER ou TRUNCATE)
GRANT USAGE ON SCHEMA public TO loja_app;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO loja_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO loja_app;

-- Tabelas novas criadas por futuras migracoes (rodadas por este mesmo administrador)
-- ja nascem com esse acesso.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO loja_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO loja_app;
