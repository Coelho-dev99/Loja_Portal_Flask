-- =====================================================
-- Loja Portal La.B - Schema PostgreSQL (versao 2)
-- Catalogo com carrinho, pedidos, frete e acompanhamento.
-- Use este arquivo para criar o banco do zero.
-- Se voce ja tem o banco da versao 1, use sql/migracao_02.sql.
-- =====================================================

-- CLIENTES
-- O telefone (somente numeros) identifica o cliente que volta a comprar.
CREATE TABLE clientes (
    id          SERIAL PRIMARY KEY,
    nome        VARCHAR(120) NOT NULL,
    instagram   VARCHAR(60),
    telefone    VARCHAR(20)  NOT NULL UNIQUE,
    cpf         VARCHAR(11),                       -- opcional (dado sensivel, LGPD)
    criado_em   TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- CPF unico apenas quando preenchido
CREATE UNIQUE INDEX uq_clientes_cpf ON clientes (cpf) WHERE cpf IS NOT NULL;

-- ENDERECOS
-- Em apartamento, o complemento (bloco, numero do apto) e obrigatorio.
CREATE TABLE enderecos (
    id            SERIAL PRIMARY KEY,
    cliente_id    INTEGER      NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    cep           CHAR(8)      NOT NULL,
    rua           VARCHAR(150) NOT NULL,
    numero        VARCHAR(10)  NOT NULL,
    tipo_moradia  VARCHAR(12)  NOT NULL DEFAULT 'casa',
    complemento   VARCHAR(80),
    bairro        VARCHAR(80)  NOT NULL,
    cidade        VARCHAR(80)  NOT NULL,
    estado        CHAR(2)      NOT NULL,
    criado_em     TIMESTAMP    NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_enderecos_moradia
        CHECK (tipo_moradia IN ('casa', 'apartamento')),
    CONSTRAINT ck_enderecos_apto_complemento
        CHECK (tipo_moradia = 'casa' OR complemento IS NOT NULL)
);

-- CATEGORIAS DO CATALOGO (Tapetes, Quadros, Porta-copos...)
CREATE TABLE categorias (
    id    SERIAL PRIMARY KEY,
    nome  VARCHAR(60) NOT NULL UNIQUE,
    slug  VARCHAR(80) NOT NULL UNIQUE
);

-- TIPOS DE PECA PERSONALIZADA (usados no relatorio mensal)
CREATE TABLE tipos_personalizado (
    id    SERIAL PRIMARY KEY,
    nome  VARCHAR(60) NOT NULL UNIQUE
);

INSERT INTO tipos_personalizado (nome) VALUES
    ('Tapete'),
    ('Quadro'),
    ('Moldura'),
    ('Outros');

-- PRODUTOS DO CATALOGO
-- modalidade 'pronta_entrega': existe e tem estoque.
-- modalidade 'personalizavel': feito sob encomenda; preco = "a partir de".
-- peso e medidas da embalagem alimentam o calculo do frete.
CREATE TABLE produtos (
    id                     SERIAL PRIMARY KEY,
    nome                   VARCHAR(120)  NOT NULL,
    slug                   VARCHAR(140)  NOT NULL,
    descricao              TEXT,
    categoria_id           INTEGER REFERENCES categorias(id) ON DELETE SET NULL,
    modalidade             VARCHAR(20)   NOT NULL DEFAULT 'pronta_entrega',
    tipo_personalizado_id  INTEGER REFERENCES tipos_personalizado(id),
    preco                  NUMERIC(10,2) NOT NULL CHECK (preco >= 0),
    estoque                INTEGER       NOT NULL DEFAULT 0 CHECK (estoque >= 0),
    peso_g                 INTEGER,
    altura_cm              NUMERIC(6,1),
    largura_cm             NUMERIC(6,1),
    comprimento_cm         NUMERIC(6,1),
    ativo                  BOOLEAN       NOT NULL DEFAULT TRUE,
    criado_em              TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_produtos_slug UNIQUE (slug),
    CONSTRAINT ck_produtos_modalidade
        CHECK (modalidade IN ('pronta_entrega', 'personalizavel')),
    CONSTRAINT ck_produtos_personalizavel_tipo
        CHECK (modalidade <> 'personalizavel' OR tipo_personalizado_id IS NOT NULL),
    CONSTRAINT ck_produtos_peso
        CHECK (peso_g IS NULL OR peso_g > 0),
    CONSTRAINT ck_produtos_medidas
        CHECK ((altura_cm IS NULL OR altura_cm > 0)
           AND (largura_cm IS NULL OR largura_cm > 0)
           AND (comprimento_cm IS NULL OR comprimento_cm > 0))
);

-- FOTOS DOS PRODUTOS (a de menor "ordem" e a principal)
CREATE TABLE produto_fotos (
    id          SERIAL PRIMARY KEY,
    produto_id  INTEGER      NOT NULL REFERENCES produtos(id) ON DELETE CASCADE,
    arquivo     VARCHAR(120) NOT NULL,
    ordem       INTEGER      NOT NULL DEFAULT 0,
    criado_em   TIMESTAMP    NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_produto_fotos ON produto_fotos (produto_id, ordem);

-- PEDIDOS
-- Nascem quando o cliente finaliza o carrinho (ja com cliente e endereco).
-- frete_valor vazio = frete a confirmar (ex.: pedido com peca personalizada).
-- O estoque das pecas de pronta entrega e reservado ao criar o pedido
-- e devolvido se o pedido for cancelado.
CREATE TABLE pedidos (
    id                SERIAL PRIMARY KEY,
    cliente_id        INTEGER NOT NULL REFERENCES clientes(id),
    endereco_id       INTEGER NOT NULL REFERENCES enderecos(id),
    status            VARCHAR(20) NOT NULL DEFAULT 'aguardando_pagamento',
    frete_valor       NUMERIC(10,2) CHECK (frete_valor >= 0),
    frete_servico     VARCHAR(60),
    frete_prazo_dias  INTEGER,
    codigo_rastreio   VARCHAR(40),
    observacoes       TEXT,
    criado_em         TIMESTAMP NOT NULL DEFAULT NOW(),
    atualizado_em     TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT ck_pedidos_status
        CHECK (status IN ('aguardando_pagamento', 'pago', 'processando',
                          'enviado', 'concluido', 'cancelado'))
);

-- HISTORICO DE STATUS (alimenta a linha do tempo do acompanhamento)
CREATE TABLE pedido_status_historico (
    id         SERIAL PRIMARY KEY,
    pedido_id  INTEGER     NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    status     VARCHAR(20) NOT NULL,
    criado_em  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- ITENS DO PEDIDO
-- tipo = 'pronta_entrega' -> usa produto_id e valor fixo
-- tipo = 'personalizado'  -> usa tipo_personalizado_id + descricao do cliente
--                            (produto_id aponta o item do catalogo, se houver)
-- valor_unitario vazio = valor a combinar no chat (so em personalizado).
-- O valor fica gravado no item para o historico nao mudar se o preco
-- do produto for alterado depois.
CREATE TABLE itens_pedido (
    id                     SERIAL PRIMARY KEY,
    pedido_id              INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    tipo                   VARCHAR(20) NOT NULL
        CHECK (tipo IN ('pronta_entrega', 'personalizado')),
    produto_id             INTEGER REFERENCES produtos(id),
    tipo_personalizado_id  INTEGER REFERENCES tipos_personalizado(id),
    descricao              TEXT,
    quantidade             INTEGER NOT NULL DEFAULT 1 CHECK (quantidade > 0),
    valor_unitario         NUMERIC(10,2) CHECK (valor_unitario >= 0),
    CONSTRAINT ck_item_coerente CHECK (
        (tipo = 'pronta_entrega'
            AND produto_id IS NOT NULL
            AND tipo_personalizado_id IS NULL
            AND valor_unitario IS NOT NULL)
        OR
        (tipo = 'personalizado'
            AND tipo_personalizado_id IS NOT NULL
            AND descricao IS NOT NULL)
    )
);

-- CARRINHOS (sem login do cliente)
-- O visitante recebe um cookie com o token; os itens ficam aqui.
-- Carrinhos parados ha mais de 30 dias sao apagados pelo proprio site.
CREATE TABLE carrinhos (
    token          VARCHAR(64) PRIMARY KEY,
    itens          JSONB       NOT NULL DEFAULT '[]',
    criado_em      TIMESTAMP   NOT NULL DEFAULT NOW(),
    atualizado_em  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- INTEGRACOES (chaves de acesso do Melhor Envio)
-- O token vale 30 dias e e renovado automaticamente pelo site.
-- Nunca envie um backup deste banco para o GitHub.
CREATE TABLE integracoes (
    nome           VARCHAR(40) PRIMARY KEY,
    access_token   TEXT        NOT NULL,
    refresh_token  TEXT        NOT NULL,
    expira_em      TIMESTAMP   NOT NULL,   -- horario UTC
    atualizado_em  TIMESTAMP   NOT NULL DEFAULT NOW()
);

-- INDICES (consultas mais rapidas)
CREATE INDEX idx_pedidos_cliente   ON pedidos (cliente_id);
CREATE INDEX idx_pedidos_criado_em ON pedidos (criado_em);
CREATE INDEX idx_itens_pedido      ON itens_pedido (pedido_id);
CREATE INDEX idx_historico_pedido  ON pedido_status_historico (pedido_id);
CREATE INDEX idx_carrinhos_atualizado ON carrinhos (atualizado_em);

-- =====================================================
-- RELATORIOS DO MES (exemplos de consultas)
-- Considera como "vendido": pago, processando, enviado ou concluido
-- =====================================================

-- 1) Pronta entrega: quantidade e total por produto no mes atual
-- SELECT p.nome,
--        SUM(i.quantidade)                    AS qtd_vendida,
--        SUM(i.quantidade * i.valor_unitario) AS total
-- FROM itens_pedido i
-- JOIN pedidos  pe ON pe.id = i.pedido_id
-- JOIN produtos p  ON p.id  = i.produto_id
-- WHERE i.tipo = 'pronta_entrega'
--   AND pe.status IN ('pago', 'processando', 'enviado', 'concluido')
--   AND date_trunc('month', pe.criado_em) = date_trunc('month', CURRENT_DATE)
-- GROUP BY p.nome
-- ORDER BY total DESC;

-- 2) Personalizados: quantidade e total por tipo no mes atual
-- SELECT t.nome,
--        SUM(i.quantidade)                                AS qtd,
--        SUM(i.quantidade * COALESCE(i.valor_unitario, 0)) AS total
-- FROM itens_pedido i
-- JOIN pedidos pe             ON pe.id = i.pedido_id
-- JOIN tipos_personalizado t  ON t.id  = i.tipo_personalizado_id
-- WHERE i.tipo = 'personalizado'
--   AND pe.status IN ('pago', 'processando', 'enviado', 'concluido')
--   AND date_trunc('month', pe.criado_em) = date_trunc('month', CURRENT_DATE)
-- GROUP BY t.nome
-- ORDER BY total DESC;

-- 3) Clientes que compraram mais de uma vez
-- SELECT c.nome, c.instagram, COUNT(pe.id) AS total_pedidos
-- FROM clientes c
-- JOIN pedidos pe ON pe.cliente_id = c.id
-- WHERE pe.status IN ('pago', 'processando', 'enviado', 'concluido')
-- GROUP BY c.id
-- HAVING COUNT(pe.id) > 1
-- ORDER BY total_pedidos DESC;
