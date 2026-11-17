"""Consultas do relatorio mensal e das paginas de clientes.

Regra de venda: conta como venda o pedido pago (ou ja em andamento, enviado ou
concluido), no mes em que foi marcado como Pago. Pedidos cancelados e
aguardando pagamento ficam de fora.
"""
import re
from datetime import date

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]

CTE_VENDAS = """
    vendas AS (
        SELECT pe.id, pe.cliente_id, pe.frete_valor,
               COALESCE(
                   (SELECT MIN(h.criado_em) FROM pedido_status_historico h
                    WHERE h.pedido_id = pe.id
                      AND h.status IN ('pago', 'processando', 'enviado', 'concluido')),
                   pe.criado_em
               ) AS data_venda
        FROM pedidos pe
        WHERE pe.status IN ('pago', 'processando', 'enviado', 'concluido')
    )
"""

CTE_PEDIDOS_VENDIDOS = (
    CTE_VENDAS
    + """,
    ped AS (
        SELECT v.id, v.cliente_id, v.data_venda,
               COALESCE((SELECT SUM(i.quantidade * i.valor_unitario)
                         FROM itens_pedido i WHERE i.pedido_id = v.id), 0)
               + COALESCE(v.frete_valor, 0) AS total
        FROM vendas v
    )
"""
)

PERIODO = "v.data_venda >= %(inicio)s AND v.data_venda < %(fim)s"


# ---------------------------------------------------------------
# Periodo
# ---------------------------------------------------------------
def _rotulo(d):
    return f"{MESES[d.month - 1]} de {d.year}"


def _texto(d):
    return f"{d.year:04d}-{d.month:02d}"


def intervalo(mes_texto):
    """Le '2026-11' e devolve o mes pedido (ou o mes atual, se o texto for invalido)."""
    hoje = date.today()
    ano, mes = hoje.year, hoje.month
    if mes_texto and re.fullmatch(r"\d{4}-\d{2}", mes_texto):
        a, m = int(mes_texto[:4]), int(mes_texto[5:])
        if 2000 <= a <= 2100 and 1 <= m <= 12:
            ano, mes = a, m

    inicio = date(ano, mes, 1)
    fim = date(ano + (mes == 12), mes % 12 + 1, 1)
    anterior = date(ano - (mes == 1), (mes - 2) % 12 + 1, 1)
    primeiro_do_mes_atual = date(hoje.year, hoje.month, 1)

    return {
        "inicio": inicio,
        "fim": fim,
        "texto": _texto(inicio),
        "rotulo": _rotulo(inicio),
        "anterior_texto": _texto(anterior),
        "anterior_rotulo": _rotulo(anterior),
        "proximo_texto": _texto(fim) if inicio < primeiro_do_mes_atual else None,
        "proximo_rotulo": _rotulo(fim) if inicio < primeiro_do_mes_atual else None,
    }


# ---------------------------------------------------------------
# Relatorio do mes
# ---------------------------------------------------------------
def resumo(cur, p):
    cur.execute(
        f"""
        WITH {CTE_VENDAS}
        SELECT COUNT(*) AS pedidos, COALESCE(SUM(v.frete_valor), 0) AS frete
        FROM vendas v WHERE {PERIODO}
        """,
        p,
    )
    base = cur.fetchone()

    cur.execute(
        f"""
        WITH {CTE_VENDAS}
        SELECT COALESCE(SUM(i.quantidade), 0) AS pecas,
               COALESCE(SUM(i.quantidade * i.valor_unitario), 0) AS faturamento,
               COUNT(*) FILTER (WHERE i.valor_unitario IS NULL) AS sem_valor
        FROM vendas v JOIN itens_pedido i ON i.pedido_id = v.id
        WHERE {PERIODO}
        """,
        p,
    )
    itens = cur.fetchone()

    cur.execute("SELECT COUNT(*) AS n FROM pedidos WHERE status = 'aguardando_pagamento'")
    aguardando = cur.fetchone()["n"]
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM pedidos
        WHERE status = 'cancelado' AND criado_em >= %(inicio)s AND criado_em < %(fim)s
        """,
        p,
    )
    cancelados = cur.fetchone()["n"]

    return {
        "pedidos": base["pedidos"],
        "frete": base["frete"],
        "pecas": itens["pecas"],
        "faturamento": itens["faturamento"],
        "sem_valor": itens["sem_valor"],
        "total": itens["faturamento"] + base["frete"],
        "aguardando": aguardando,
        "cancelados": cancelados,
    }


def por_produto(cur, p):
    cur.execute(
        f"""
        WITH {CTE_VENDAS}
        SELECT pr.nome, SUM(i.quantidade) AS qtd,
               SUM(i.quantidade * i.valor_unitario) AS total
        FROM vendas v
        JOIN itens_pedido i ON i.pedido_id = v.id
        JOIN produtos pr ON pr.id = i.produto_id
        WHERE i.tipo = 'pronta_entrega' AND {PERIODO}
        GROUP BY pr.id, pr.nome
        ORDER BY total DESC, pr.nome
        """,
        p,
    )
    return cur.fetchall()


def por_tipo(cur, p):
    cur.execute(
        f"""
        WITH {CTE_VENDAS}
        SELECT t.nome, SUM(i.quantidade) AS qtd,
               COALESCE(SUM(i.quantidade * i.valor_unitario), 0) AS total,
               COUNT(*) FILTER (WHERE i.valor_unitario IS NULL) AS sem_valor
        FROM vendas v
        JOIN itens_pedido i ON i.pedido_id = v.id
        JOIN tipos_personalizado t ON t.id = i.tipo_personalizado_id
        WHERE i.tipo = 'personalizado' AND {PERIODO}
        GROUP BY t.id, t.nome
        ORDER BY qtd DESC, total DESC, t.nome
        """,
        p,
    )
    return cur.fetchall()


def itens_personalizados(cur, p):
    cur.execute(
        f"""
        WITH {CTE_VENDAS}
        SELECT v.id AS pedido, v.data_venda, c.nome AS cliente, t.nome AS tipo,
               i.descricao, i.quantidade, i.valor_unitario
        FROM vendas v
        JOIN clientes c ON c.id = v.cliente_id
        JOIN itens_pedido i ON i.pedido_id = v.id
        JOIN tipos_personalizado t ON t.id = i.tipo_personalizado_id
        WHERE i.tipo = 'personalizado' AND {PERIODO}
        ORDER BY v.data_venda, v.id, i.id
        """,
        p,
    )
    return cur.fetchall()


def pedidos_do_mes(cur, p):
    cur.execute(
        f"""
        WITH {CTE_VENDAS}
        SELECT v.id, v.data_venda, c.nome AS cliente, pe.status, v.frete_valor,
               COALESCE(SUM(i.quantidade), 0) AS pecas,
               COALESCE(SUM(i.quantidade * i.valor_unitario), 0) AS valor_pecas,
               COUNT(*) FILTER (WHERE i.id IS NOT NULL AND i.valor_unitario IS NULL) AS sem_valor
        FROM vendas v
        JOIN pedidos pe ON pe.id = v.id
        JOIN clientes c ON c.id = v.cliente_id
        LEFT JOIN itens_pedido i ON i.pedido_id = v.id
        WHERE {PERIODO}
        GROUP BY v.id, v.data_venda, c.nome, pe.status, v.frete_valor
        ORDER BY v.data_venda, v.id
        """,
        p,
    )
    return cur.fetchall()


def clientes_do_mes(cur, p):
    """Quantos clientes compraram pela primeira vez no mes e quantos ja tinham comprado antes."""
    cur.execute(
        f"""
        WITH {CTE_VENDAS},
        no_mes AS (SELECT DISTINCT v.cliente_id FROM vendas v WHERE {PERIODO}),
        primeira AS (SELECT v.cliente_id, MIN(v.data_venda) AS primeira
                     FROM vendas v GROUP BY v.cliente_id)
        SELECT COUNT(*) FILTER (WHERE pr.primeira >= %(inicio)s) AS novos,
               COUNT(*) FILTER (WHERE pr.primeira < %(inicio)s) AS recorrentes
        FROM no_mes n JOIN primeira pr ON pr.cliente_id = n.cliente_id
        """,
        p,
    )
    return cur.fetchone()


def recorrentes(cur):
    """Clientes com 2 ou mais pedidos vendidos (em qualquer mes)."""
    cur.execute(
        f"""
        WITH {CTE_PEDIDOS_VENDIDOS}
        SELECT c.id, c.nome, c.instagram, c.telefone,
               COUNT(*) AS pedidos, SUM(ped.total) AS total,
               MIN(ped.data_venda) AS primeira, MAX(ped.data_venda) AS ultima
        FROM ped JOIN clientes c ON c.id = ped.cliente_id
        GROUP BY c.id
        HAVING COUNT(*) >= 2
        ORDER BY COUNT(*) DESC, SUM(ped.total) DESC, c.nome
        """
    )
    return cur.fetchall()


def relatorio_do_mes(cur, mes):
    p = {"inicio": mes["inicio"], "fim": mes["fim"]}
    return {
        "mes": mes,
        "resumo": resumo(cur, p),
        "produtos": por_produto(cur, p),
        "tipos": por_tipo(cur, p),
        "personalizados": itens_personalizados(cur, p),
        "pedidos": pedidos_do_mes(cur, p),
        "clientes_mes": clientes_do_mes(cur, p),
        "recorrentes": recorrentes(cur),
    }


# ---------------------------------------------------------------
# Clientes
# ---------------------------------------------------------------
def _padrao_busca(termo):
    escapado = termo.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    digitos = re.sub(r"\D", "", termo)
    return f"%{escapado}%", (f"%{digitos}%" if digitos else "")


def lista_de_clientes(cur, termo="", limite=300):
    like, tel = _padrao_busca(termo)
    cur.execute(
        f"""
        WITH {CTE_PEDIDOS_VENDIDOS}
        SELECT c.id, c.nome, c.instagram, c.telefone, c.criado_em,
               (SELECT e.cidade || '/' || e.estado FROM enderecos e
                WHERE e.cliente_id = c.id ORDER BY e.id DESC LIMIT 1) AS cidade_uf,
               COUNT(ped.id) AS pedidos,
               COALESCE(SUM(ped.total), 0) AS total,
               MIN(ped.data_venda) AS primeira,
               MAX(ped.data_venda) AS ultima
        FROM clientes c LEFT JOIN ped ON ped.cliente_id = c.id
        WHERE (%(termo)s = '' OR c.nome ILIKE %(like)s OR c.instagram ILIKE %(like)s
               OR (%(tel)s <> '' AND c.telefone LIKE %(tel)s))
        GROUP BY c.id
        ORDER BY MAX(ped.data_venda) DESC NULLS LAST, c.nome
        LIMIT %(limite)s
        """,
        {"termo": termo, "like": like, "tel": tel, "limite": limite},
    )
    return cur.fetchall()


def detalhe_do_cliente(cur, cliente_id):
    cur.execute("SELECT * FROM clientes WHERE id = %s", (cliente_id,))
    cliente = cur.fetchone()
    if cliente is None:
        return None

    cur.execute(
        """
        SELECT cep, rua, numero, tipo_moradia, complemento, bairro, cidade, estado
        FROM enderecos WHERE cliente_id = %s ORDER BY id DESC
        """,
        (cliente_id,),
    )
    enderecos = cur.fetchall()

    cur.execute(
        """
        SELECT pe.id, pe.status, pe.criado_em, pe.frete_valor,
               COALESCE(SUM(i.quantidade * i.valor_unitario), 0) AS valor_pecas,
               COUNT(*) FILTER (WHERE i.id IS NOT NULL AND i.valor_unitario IS NULL) AS sem_valor
        FROM pedidos pe LEFT JOIN itens_pedido i ON i.pedido_id = pe.id
        WHERE pe.cliente_id = %s
        GROUP BY pe.id
        ORDER BY pe.criado_em DESC, pe.id DESC
        """,
        (cliente_id,),
    )
    pedidos = cur.fetchall()

    cur.execute(
        f"""
        WITH {CTE_VENDAS}
        SELECT pr.nome, SUM(i.quantidade) AS qtd, SUM(i.quantidade * i.valor_unitario) AS total
        FROM vendas v
        JOIN itens_pedido i ON i.pedido_id = v.id
        JOIN produtos pr ON pr.id = i.produto_id
        WHERE v.cliente_id = %s AND i.tipo = 'pronta_entrega'
        GROUP BY pr.id, pr.nome ORDER BY qtd DESC, pr.nome
        """,
        (cliente_id,),
    )
    pronta_entrega = cur.fetchall()

    cur.execute(
        f"""
        WITH {CTE_VENDAS}
        SELECT t.nome, SUM(i.quantidade) AS qtd,
               COALESCE(SUM(i.quantidade * i.valor_unitario), 0) AS total
        FROM vendas v
        JOIN itens_pedido i ON i.pedido_id = v.id
        JOIN tipos_personalizado t ON t.id = i.tipo_personalizado_id
        WHERE v.cliente_id = %s AND i.tipo = 'personalizado'
        GROUP BY t.id, t.nome ORDER BY qtd DESC, t.nome
        """,
        (cliente_id,),
    )
    personalizados = cur.fetchall()

    cur.execute(
        f"""
        WITH {CTE_PEDIDOS_VENDIDOS}
        SELECT COUNT(*) AS pedidos, COALESCE(SUM(total), 0) AS total,
               MIN(data_venda) AS primeira, MAX(data_venda) AS ultima
        FROM ped WHERE cliente_id = %s
        """,
        (cliente_id,),
    )
    totais = cur.fetchone()

    return {
        "cliente": cliente,
        "enderecos": enderecos,
        "pedidos": pedidos,
        "pronta_entrega": pronta_entrega,
        "personalizados": personalizados,
        "totais": totais,
    }
