from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth import login_required
from app.db import get_db
from app.status import PROXIMOS, ROTULOS
from app.util import ler_decimal, ler_inteiro

bp = Blueprint("admin_pedidos", __name__, url_prefix="/admin/pedidos")

# Pedidos por pagina na lista do painel
POR_PAGINA = 50

ITENS_SQL = """
    SELECT i.id, i.tipo, i.quantidade, i.valor_unitario, i.descricao,
           p.nome AS produto_nome, t.nome AS tipo_nome
    FROM itens_pedido i
    LEFT JOIN produtos p ON p.id = i.produto_id
    LEFT JOIN tipos_personalizado t ON t.id = i.tipo_personalizado_id
    WHERE i.pedido_id = %s
    ORDER BY i.id
"""


def voltar(pedido_id):
    return redirect(url_for("admin_pedidos.detalhe", pedido_id=pedido_id))


# ---------------------------------------------------------------
# Lista
# ---------------------------------------------------------------
@bp.route("")
@login_required
def lista():
    status = request.args.get("status", "")
    if status not in ROTULOS:
        status = ""

    pagina = ler_inteiro(request.args.get("pagina", "1"), 1, 100000) or 1

    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT status, COUNT(*) AS n FROM pedidos GROUP BY status")
        contagem = {linha["status"]: linha["n"] for linha in cur.fetchall()}
        total_geral = sum(contagem.values())

        # Quantas paginas existem para o filtro escolhido (sem passar do fim)
        total_filtro = contagem.get(status, 0) if status else total_geral
        total_paginas = max(1, -(-total_filtro // POR_PAGINA))
        pagina = min(pagina, total_paginas)

        cur.execute(
            """
            SELECT pe.id, pe.status, pe.criado_em, pe.frete_valor,
                   c.nome AS cliente,
                   COUNT(i.id) AS qtd_itens,
                   COUNT(*) FILTER (WHERE i.tipo = 'personalizado'
                                    AND i.valor_unitario IS NULL) AS a_definir,
                   COALESCE(SUM(i.quantidade * i.valor_unitario), 0) AS subtotal
            FROM pedidos pe
            JOIN clientes c ON c.id = pe.cliente_id
            LEFT JOIN itens_pedido i ON i.pedido_id = pe.id
            WHERE (%(status)s = '' OR pe.status = %(status)s)
            GROUP BY pe.id, c.nome
            ORDER BY pe.criado_em DESC, pe.id DESC
            LIMIT %(limite)s OFFSET %(deslocamento)s
            """,
            {
                "status": status,
                "limite": POR_PAGINA,
                "deslocamento": (pagina - 1) * POR_PAGINA,
            },
        )
        pedidos = cur.fetchall()

    return render_template(
        "admin/pedidos.html",
        pedidos=pedidos,
        status=status,
        contagem=contagem,
        total_geral=total_geral,
        rotulos=ROTULOS,
        pagina=pagina,
        total_paginas=total_paginas,
    )


# ---------------------------------------------------------------
# Detalhe
# ---------------------------------------------------------------
@bp.route("/<int:pedido_id>")
@login_required
def detalhe(pedido_id):
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT pe.*, c.nome AS cliente_nome, c.instagram, c.telefone,
                   e.cep, e.rua, e.numero, e.tipo_moradia, e.complemento,
                   e.bairro, e.cidade, e.estado
            FROM pedidos pe
            JOIN clientes c ON c.id = pe.cliente_id
            JOIN enderecos e ON e.id = pe.endereco_id
            WHERE pe.id = %s
            """,
            (pedido_id,),
        )
        pedido = cur.fetchone()
        if pedido is None:
            abort(404)

        cur.execute(ITENS_SQL, (pedido_id,))
        itens = cur.fetchall()

        cur.execute(
            """
            SELECT status, criado_em FROM pedido_status_historico
            WHERE pedido_id = %s ORDER BY criado_em, id
            """,
            (pedido_id,),
        )
        historico = cur.fetchall()

    subtotal = sum(
        (i["quantidade"] * i["valor_unitario"] for i in itens if i["valor_unitario"] is not None),
        0,
    )
    a_definir = sum(1 for i in itens if i["valor_unitario"] is None)
    total = subtotal + (pedido["frete_valor"] or 0)

    return render_template(
        "admin/pedido_detalhe.html",
        pedido=pedido,
        itens=itens,
        historico=historico,
        subtotal=subtotal,
        a_definir=a_definir,
        total=total,
        proximos=PROXIMOS[pedido["status"]],
        rotulos=ROTULOS,
    )


# ---------------------------------------------------------------
# Valor combinado das pecas personalizadas
# ---------------------------------------------------------------
@bp.route("/<int:pedido_id>/itens/<int:item_id>/valor", methods=["POST"])
@login_required
def item_valor(pedido_id, item_id):
    db = get_db()
    valor = ler_decimal(request.form.get("valor", ""), 0, 99999999.99)
    if valor is None:
        flash("Valor inválido. Exemplo: 280,00", "erro")
        return voltar(pedido_id)

    with db.cursor() as cur:
        cur.execute("SELECT status FROM pedidos WHERE id = %s FOR UPDATE", (pedido_id,))
        pedido = cur.fetchone()
        if pedido is None:
            abort(404)
        if pedido["status"] != "aguardando_pagamento":
            flash("O valor só pode ser alterado enquanto o pedido aguarda pagamento.", "erro")
            return voltar(pedido_id)

        cur.execute(
            """
            UPDATE itens_pedido SET valor_unitario = %s
            WHERE id = %s AND pedido_id = %s AND tipo = 'personalizado'
            RETURNING id
            """,
            (valor, item_id, pedido_id),
        )
        if cur.fetchone() is None:
            abort(404)
        cur.execute("UPDATE pedidos SET atualizado_em = NOW() WHERE id = %s", (pedido_id,))
    db.commit()
    flash("Valor combinado salvo.", "ok")
    return voltar(pedido_id)


# ---------------------------------------------------------------
# Frete e rastreio (preenchidos por voce)
# ---------------------------------------------------------------
@bp.route("/<int:pedido_id>/frete", methods=["POST"])
@login_required
def frete(pedido_id):
    f = request.form
    erros = []

    frete_valor = None
    texto_valor = f.get("frete_valor", "").strip()
    if texto_valor:
        frete_valor = ler_decimal(texto_valor, 0, 99999.99)
        if frete_valor is None:
            erros.append("Valor do frete inválido. Exemplo: 25,90")

    servico = f.get("frete_servico", "").strip() or None
    if servico and len(servico) > 60:
        erros.append("O nome do serviço de frete aceita no máximo 60 caracteres.")

    prazo = None
    texto_prazo = f.get("frete_prazo_dias", "").strip()
    if texto_prazo:
        prazo = ler_inteiro(texto_prazo, 0, 90)
        if prazo is None:
            erros.append("Prazo inválido. Informe os dias úteis, de 0 a 90.")

    rastreio = f.get("codigo_rastreio", "").strip() or None
    if rastreio and len(rastreio) > 40:
        erros.append("O código de rastreio aceita no máximo 40 caracteres.")

    if erros:
        for e in erros:
            flash(e, "erro")
        return voltar(pedido_id)

    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """
            UPDATE pedidos
            SET frete_valor = %s, frete_servico = %s, frete_prazo_dias = %s,
                codigo_rastreio = %s, atualizado_em = NOW()
            WHERE id = %s AND status <> 'cancelado'
            RETURNING id
            """,
            (frete_valor, servico, prazo, rastreio, pedido_id),
        )
        if cur.fetchone() is None:
            flash("Pedido não encontrado ou já cancelado.", "erro")
            return voltar(pedido_id)
    db.commit()
    flash("Frete e rastreio salvos.", "ok")
    return voltar(pedido_id)


# ---------------------------------------------------------------
# Andamento do pedido
# ---------------------------------------------------------------
@bp.route("/<int:pedido_id>/status", methods=["POST"])
@login_required
def mudar_status(pedido_id):
    novo_status = request.form.get("status", "")

    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT status FROM pedidos WHERE id = %s FOR UPDATE", (pedido_id,))
        pedido = cur.fetchone()
        if pedido is None:
            abort(404)

        if novo_status not in PROXIMOS[pedido["status"]]:
            flash("Essa mudança de status não é permitida.", "erro")
            return voltar(pedido_id)

        # Cancelamento devolve ao estoque as pecas de pronta entrega
        if novo_status == "cancelado":
            cur.execute(
                """
                UPDATE produtos p
                SET estoque = p.estoque + s.qtd
                FROM (
                    SELECT produto_id, SUM(quantidade) AS qtd
                    FROM itens_pedido
                    WHERE pedido_id = %s AND tipo = 'pronta_entrega'
                    GROUP BY produto_id
                ) s
                WHERE p.id = s.produto_id
                """,
                (pedido_id,),
            )

        cur.execute(
            "UPDATE pedidos SET status = %s, atualizado_em = NOW() WHERE id = %s",
            (novo_status, pedido_id),
        )
        cur.execute(
            "INSERT INTO pedido_status_historico (pedido_id, status) VALUES (%s, %s)",
            (pedido_id, novo_status),
        )
    db.commit()
    flash("Status atualizado.", "ok")
    return voltar(pedido_id)
