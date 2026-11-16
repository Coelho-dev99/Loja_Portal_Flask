-- =====================================================
-- Migracao 02: catalogo, fotos, frete e novos status
-- Leva o banco da versao 1 para a versao 2.
--
-- COMO USAR: no pgAdmin, abra o Query Tool no banco loja_portal,
-- cole este arquivo inteiro e execute UMA vez (F5).
-- Se der erro, nada e alterado: clique em ROLLBACK (ou feche a aba)
-- e me envie a mensagem.
--
-- O QUE ACONTECE COM OS DADOS ATUAIS:
--  * Produtos, clientes, enderecos e itens continuam.
--  * Os links de foto antigos (foto_url) sao descartados: envie as fotos
--    de novo pelo painel.
--  * Pedidos criados no fluxo antigo sem cliente (rascunhos com link unico)
--    sao apagados, pois nao existem mais.
--  * Status antigos viram os novos: confirmado -> aguardando_pagamento,
--    entregue -> concluido.
-- =====================================================

BEGIN;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'produtos' AND column_name = 'slug'
    ) THEN
        RAISE EXCEPTION 'Esta migracao ja foi aplicada neste banco.';
    END IF;
END $$;

-- 1) Categorias
CREATE TABLE categorias (
    id    SERIAL PRIMARY KEY,
    nome  VARCHAR(60) NOT NULL UNIQUE,
    slug  VARCHAR(80) NOT NULL UNIQUE
);

-- 2) Produtos: catalogo, modalidade, peso e medidas
ALTER TABLE produtos
    ADD COLUMN slug                   VARCHAR(140),
    ADD COLUMN categoria_id           INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
    ADD COLUMN modalidade             VARCHAR(20) NOT NULL DEFAULT 'pronta_entrega',
    ADD COLUMN tipo_personalizado_id  INTEGER REFERENCES tipos_personalizado(id),
    ADD COLUMN peso_g                 INTEGER,
    ADD COLUMN altura_cm              NUMERIC(6,1),
    ADD COLUMN largura_cm             NUMERIC(6,1),
    ADD COLUMN comprimento_cm         NUMERIC(6,1);

UPDATE produtos SET slug = 'produto-' || id;

ALTER TABLE produtos
    ALTER COLUMN slug SET NOT NULL,
    ADD CONSTRAINT uq_produtos_slug UNIQUE (slug),
    ADD CONSTRAINT ck_produtos_modalidade
        CHECK (modalidade IN ('pronta_entrega', 'personalizavel')),
    ADD CONSTRAINT ck_produtos_personalizavel_tipo
        CHECK (modalidade <> 'personalizavel' OR tipo_personalizado_id IS NOT NULL),
    ADD CONSTRAINT ck_produtos_peso
        CHECK (peso_g IS NULL OR peso_g > 0),
    ADD CONSTRAINT ck_produtos_medidas
        CHECK ((altura_cm IS NULL OR altura_cm > 0)
           AND (largura_cm IS NULL OR largura_cm > 0)
           AND (comprimento_cm IS NULL OR comprimento_cm > 0)),
    DROP COLUMN foto_url;

-- 3) Fotos dos produtos
CREATE TABLE produto_fotos (
    id          SERIAL PRIMARY KEY,
    produto_id  INTEGER      NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    arquivo     VARCHAR(120) NOT NULL,
    ordem       INTEGER      NOT NULL DEFAULT 0,
    criado_em   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_produto_fotos ON produto_fotos (produto_id, ordem);

-- 4) Enderecos: casa ou apartamento
ALTER TABLE enderecos
    ADD COLUMN tipo_moradia VARCHAR(12) NOT NULL DEFAULT 'casa',
    ADD CONSTRAINT ck_enderecos_moradia
        CHECK (tipo_moradia IN ('casa', 'apartamento')),
    ADD CONSTRAINT ck_enderecos_apto_complemento
        CHECK (tipo_moradia = 'casa' OR complemento IS NOT NULL);

-- 5) Pedidos: novos status, frete, rastreio
DELETE FROM pedidos WHERE cliente_id IS NULL OR endereco_id IS NULL;

DO $$
DECLARE r record;
BEGIN
    FOR r IN
        SELECT conname FROM pg_constraint
        WHERE conrelid = 'pedidos'::regclass
          AND contype = 'c'
          AND pg_get_constraintdef(oid) LIKE '%status%'
    LOOP
        EXECUTE format('ALTER TABLE pedidos DROP CONSTRAINT %I', r.conname);
    END LOOP;
END $$;

UPDATE pedidos SET status = CASE status
    WHEN 'aguardando_dados' THEN 'aguardando_pagamento'
    WHEN 'confirmado'       THEN 'aguardando_pagamento'
    WHEN 'entregue'         THEN 'concluido'
    ELSE status
END;

ALTER TABLE pedidos
    ALTER COLUMN status SET DEFAULT 'aguardando_pagamento',
    ADD CONSTRAINT ck_pedidos_status
        CHECK (status IN ('aguardando_pagamento', 'pago', 'processando',
                          'enviado', 'concluido', 'cancelado')),
    ALTER COLUMN cliente_id  SET NOT NULL,
    ALTER COLUMN endereco_id SET NOT NULL,
    ADD COLUMN frete_valor      NUMERIC(10,2) CHECK (frete_valor >= 0),
    ADD COLUMN frete_servico    VARCHAR(60),
    ADD COLUMN frete_prazo_dias INTEGER,
    ADD COLUMN codigo_rastreio  VARCHAR(40),
    ADD COLUMN atualizado_em    TIMESTAMP NOT NULL DEFAULT NOW(),
    DROP COLUMN token,
    DROP COLUMN dados_preenchidos_em;

-- 6) Historico de status (linha do tempo do acompanhamento)
CREATE TABLE pedido_status_historico (
    id         SERIAL PRIMARY KEY,
    pedido_id  INTEGER     NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    status     VARCHAR(20) NOT NULL,
    criado_em  TIMESTAMP   NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_historico_pedido ON pedido_status_historico (pedido_id);

INSERT INTO pedido_status_historico (pedido_id, status, criado_em)
SELECT id, status, criado_em FROM pedidos;

-- 7) Itens: valor a combinar nos personalizados
ALTER TABLE itens_pedido
    ALTER COLUMN valor_unitario DROP NOT NULL,
    DROP CONSTRAINT ck_item_coerente,
    ADD CONSTRAINT ck_item_coerente CHECK (
        (tipo = 'pronta_entrega'
            AND produto_id IS NOT NULL
            AND tipo_personalizado_id IS NULL
            AND valor_unitario IS NOT NULL)
        OR
        (tipo = 'personalizado'
            AND tipo_personalizado_id IS NOT NULL
            AND descricao IS NOT NULL)
    );

COMMIT;
