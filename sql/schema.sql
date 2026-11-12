-- =====================================================
-- Loja Portal La.B - Schema PostgreSQL
-- Controle de clientes, estoque e vendas (pronta entrega + personalizados)
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
CREATE TABLE enderecos (
    id           SERIAL PRIMARY KEY,
    cliente_id   INTEGER   NOT NULL,
    complemento  VARCHAR(80),
    bairro       VARCHAR(80)  NOT NULL,
    cidade       VARCHAR(80)  NOT NULL,
    estado       CHAR(2)      NOT NULL,
    criado_em    TIMESTAMP    NOT NULL DEFAULT NOW()
);

-- PRODUTOS (somente pronta entrega, com estoque)
CREATE TABLE produtos (
    id         SERIAL PRIMARY KEY,
    nome       VARCHAR(120)  NOT NULL,
    descricao  TEXT,
    preco      NUMERIC(10,2) NOT NULL CHECK (preco >= 0),
    foto_url   VARCHAR(255),
    estoque    INTEGER       NOT NULL DEFAULT 0 CHECK (estoque >= 0),
    ativo      BOOLEAN       NOT NULL DEFAULT TRUE,
    criado_em  TIMESTAMP     NOT NULL DEFAULT NOW()
);

-- TIPOS DE PERSONALIZADO (voce cria novos tipos quando quiser)
CREATE TABLE tipos_personalizado (
    id    SERIAL PRIMARY KEY,
    nome  VARCHAR(60) NOT NULL UNIQUE
);

INSERT INTO tipos_personalizado (nome) VALUES
    ('Tapete'),
    ('Quadro'),
    ('Moldura'),
    ('Outros');
e
-- PEDIDOS
-- cliente_id e ndereco_id comecam vazios: sao preenchidos quando o
-- cliente abre o link unico (token) e envia o formulario.
CREATE TABLE pedidos (
    id                     SERIAL PRIMARY KEY,
    cliente_id             INTEGER REFERENCES clientes(id),
    endereco_id            INTEGER REFERENCES enderecos(id),
    token                  VARCHAR(64) NOT NULL UNIQUE,
    status                 VARCHAR(20) NOT NULL DEFAULT 'aguardando_dados'
        CHECK (status IN ('aguardando_dados', 'confirmado', 'pago',
                          'enviado', 'entr    NOT NULL REFERENCES clientes(id) ON DELETE CASCADE,
    cep          CHAR(8)      NOT NULL,
    rua          VARCHAR(150) NOT NULL,
    numero       VARCHAR(10) egue', 'cancelado')),
    observacoes            TEXT,
    criado_em              TIMESTAMP NOT NULL DEFAULT NOW(),
    dados_preenchidos_em   TIMESTAMP
);

-- ITENS DO PEDIDO
-- tipo = 'pronta_entrega'  -> usa produto_id e baixa o estoque
-- tipo = 'personalizado'   -> usa tipo_personalizado_id + descricao
-- valor_unitario fica gravado no item para o historico nao mudar
-- se o preco do produto for alterado depois.
CREATE TABLE itens_pedido (
    id                      SERIAL PRIMARY KEY,
    pedido_id               INTEGER NOT NULL REFERENCES pedidos(id) ON DELETE CASCADE,
    tipo                    VARCHAR(20) NOT NULL
        CHECK (tipo IN ('pronta_entrega', 'personalizado')),
    produto_id              INTEGER REFERENCES produtos(id),
    tipo_personalizado_id   INTEGER REFERENCES tipos_personalizado(id),
    descricao               TEXT,
    quantidade              INTEGER NOT NULL DEFAULT 1 CHECK (quantidade > 0),
    valor_unitario          NUMERIC(10,2) NOT NULL CHECK (valor_unitario >= 0),
    CONSTRAINT ck_item_coerente CHECK (
        (tipo = 'pronta_entrega'
            AND produto_id IS NOT NULL
            AND tipo_personalizado_id IS NULL)
        OR
        (tipo = 'personalizado'
            AND produto_id IS NULL
            AND tipo_personalizado_id IS NOT NULL
            AND descricao IS NOT NULL)
    )
);

-- INDICES (consultas mais rapidas nos relatorios)
CREATE INDEX idx_pedidos_cliente   ON pedidos (cliente_id);
CREATE INDEX idx_pedidos_criado_em ON pedidos (criado_em);
CREATE INDEX idx_itens_pedido      ON itens_pedido (pedido_id);

-- =====================================================
-- RELATORIOS DO MES (exemplos de consultas)
-- Considera como "vendido": pago, enviado ou entregue
-- =====================================================

-- 1) Pronta entrega: quantidade e total por produto no mes atual
-- SELECT p.nome,
--        SUM(i.quantidade)                    AS qtd_vendida,
--        SUM(i.quantidade * i.valor_unitario) AS total
-- FROM itens_pedido i
-- JOIN pedidos  pe ON pe.id = i.pedido_id
-- JOIN produtos p  ON p.id  = i.produto_id
-- WHERE i.tipo = 'pronta_entrega'
--   AND pe.status IN ('pago', 'enviado', 'entregue')
--   AND date_trunc('month', pe.criado_em) = date_trunc('month', CURRENT_DATE)
-- GROUP BY p.nome
-- ORDER BY total DESC;

-- 2) Personalizados: quantidade e total por tipo no mes atual
-- SELECT t.nome,
--        SUM(i.quantidade)                    AS qtd,
--        SUM(i.quantidade * i.valor_unitario) AS total
-- FROM itens_pedido i
-- JOIN pedidos pe             ON pe.id = i.pedido_id
-- JOIN tipos_personalizado t  ON t.id  = i.tipo_personalizado_id
-- WHERE i.tipo = 'personalizado'
--   AND pe.status IN ('pago', 'enviado', 'entregue')
--   AND date_trunc('month', pe.criado_em) = date_trunc('month', CURRENT_DATE)
-- GROUP BY t.nome
-- ORDER BY total DESC;

-- 3) Clientes que compraram mais de uma vez
-- SELECT c.nome, c.instagram, COUNT(pe.id) AS total_pedidos
-- FROM clientes c
-- JOIN pedidos pe ON pe.cliente_id = c.id
-- WHERE pe.status IN ('pago', 'enviado', 'entregue')
-- GROUP BY c.id
-- HAVING COUNT(pe.id) > 1
-- ORDER BY total_pedidos DESC;
