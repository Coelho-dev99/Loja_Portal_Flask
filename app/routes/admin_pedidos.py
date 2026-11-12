import secrets
from decimal import Decimal, InvalidOperation

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for

from app.auth import login_required
from app.db import get_db
from app.status import PROXIMOS

bp = Blueprint("admin_pedidos", __name__, url_prefix="/admin/pedidos")

ITENS_SQL = """
    SELECT i.id, i.tipo, i.quantidade, i.valor_unitario, i.descricao,
           p.nome AS produto_nome, t.nome AS tipo_nome
    FROM itens_pedido i
    LEFT JOIN produtos p ON p.id = i.produto_id
    LEFT JOIN tipos_personalizado t ON t.id = i.tipo_personalizado_id
    WHERE i.pedido_id = %s
    ORDER BY i.id
"""


# ---------------------------------------------------------------
# Funcoes auxiliares
# ---------------------------------------------------------------
def ler_valor(texto):
    """Converte '12,50' em Decimal. Retorna None se for invalido."""
    try:
        valor = Decimal(texto.strip().replace(",", "."))
    except InvalidOperation:
        return None
    if not valor.is_finite() or valor < 0 or valor > Decimal("99999999.99"):
        return None
    return valor.quantize(Decimal("0.01"))


def ler_quantidade(texto):
    try:
        quantidade = int(texto.strip())
    except ValueError:
        return None
    return quantidade if 1 <= quantidade <= 1000 else None


def ler_inteiro(texto):
    try:
        return int(texto.strip())
    except ValueError:
        return None


def voltar(pedido_id):
    return redirect(url_for("admin_pedidos.detalhe", pedido_id=pedido_id))


def pedido_aberto(cur, pedido_id):
    """True se o pedido ainda aceita mudancas nos itens (cliente nao enviou os dados)."""
    cur.execute("SELECT status FROM pedidos WHERE id = %s", (pedido_id,))
    linha = cur.fetchone()
    if linha is None:
        abort(404)
    return linha["status"] == "aguardando_dados"


# ---------------------------------------------------------------
# Lista e criacao de pedidos
# ---------------------------------------------------------------
@bp.route("/")
@login_required
def lista():
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT pe.id, pe.status, pe.criado_em, pe.observacoes,
                   c.nome AS cliente,
                   COUNT(i.id) AS qtd_itens,
                   COALESCE(SUM(i.quantidade * i.valor_unitario), 0) AS total
            FROM pedidos pe
            LEFT JOIN clientes c ON c.id = pe.cliente_id
            LEFT JOIN itens_pedido i ON i.pedido_id = pe.id
            GROUP BY pe.id, c.nome
            ORDER BY pe.criado_em DESC, pe.id DESC
            """
        )
        pedidos = cur.fetchall()
    return render_template("admin/pedidos.html", pedidos=pedidos)


@bp.route("/novo", methods=["GET", "POST"])
@login_required
def novo():
    if request.method == "POST":
        referencia = request.form.get("referencia", "").strip()

        if len(referencia) > 200:
            flash("A referência pode ter no máximo 200 caracteres.", "erro")
        else:
            db = get_db()
            with db.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO pedidos (token, observacoes)
                    VALUES (%s, %s)
                    RETURNING id
                    """,
                    (secrets.token_urlsafe(32), referencia or None),
                )
                pedido_id = cur.fetchone()["id"]
            db.commit()
            return voltar(pedido_id)

    return render_template("admin/pedido_novo.html")


# ---------------------------------------------------------------
# Detalhe do pedido
# ---------------------------------------------------------------
@bp.route("/<int:pedido_id>")
@login_required
def detalhe(pedido_id):
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT pe.*, c.nome AS cliente_nome, c.instagram, c.telefone, c.cpf,
                   e.cep, e.rua, e.numero, e.complemento, e.bairro, e.cidade, e.estado
            FROM pedidos pe
            LEFT JOIN clientes c ON c.id = pe.cliente_id
            LEFT JOIN enderecos e ON e.id = pe.endereco_id
            WHERE pe.id = %s
            """,
            (pedido_id,),
        )
        pedido = cur.fetchone()
        if pedido is None:
            abort(404)

        cur.execute(ITENS_SQL, (pedido_id,))
        itens = cur.fetchall()

        produtos = []
        tipos = []
        if pedido["status"] == "aguardando_dados":
            cur.execute(
                """
                SELECT id, nome, preco, estoque
                FROM produtos
                WHERE ativo AND estoque > 0
                ORDER BY nome
                """
            )
            produtos = cur.fetchall()
            cur.execute("SELECT id, nome FROM tipos_personalizado ORDER BY nome")
            tipos = cur.fetchall()

    total = sum(i["quantidade"] * i["valor_unitario"] for i in itens)
    link = url_for("formulario.pedido", token=pedido["token"], _external=True)

    return render_template(
        "admin/pedido_detalhe.html",
        pedido=pedido,
        itens=itens,
        total=total,
        link=link,
        produtos=produtos,
        tipos=tipos,
        proximos=PROXIMOS[pedido["status"]],
    )


# ---------------------------------------------------------------
# Itens do pedido (so enquanto o cliente nao enviou os dados)
# ---------------------------------------------------------------
@bp.route("/<int:pedido_id>/itens/pronta-entrega", methods=["POST"])
@login_required
def item_pronta_entrega(pedido_id):
    db = get_db()
    with db.cursor() as cur:
        if not pedido_aberto(cur, pedido_id):
            flash("Este pedido não aceita mais alterações nos itens.", "erro")
            return voltar(pedido_id)

        produto_id = ler_inteiro(request.form.get("produto_id", ""))
        quantidade = ler_quantidade(request.form.get("quantidade", ""))
        if produto_id is None or quantidade is None:
            flash("Escolha o produto e uma quantidade válida.", "erro")
            return voltar(pedido_id)

        cur.execute(
            "SELECT id, preco, estoque FROM produtos WHERE id = %s AND ativo",
            (produto_id,),
        )
        produto = cur.fetchone()
        if produto is None:
            flash("Produto não encontrado.", "erro")
            return voltar(pedido_id)

        cur.execute(
            """
            SELECT COALESCE(SUM(quantidade), 0) AS ja
            FROM itens_pedido
            WHERE pedido_id = %s AND produto_id = %s
            """,
            (pedido_id, produto_id),
        )
        ja_no_pedido = cur.fetchone()["ja"]
        if ja_no_pedido + quantidade > produto["estoque"]:
            flash(
                f"Estoque insuficiente: há {produto['estoque']} em estoque "
                f"e {ja_no_pedido} já estão neste pedido.",
                "erro",
            )
            return voltar(pedido_id)

        texto_valor = request.form.get("valor", "").strip()
        valor = produto["preco"] if not texto_valor else ler_valor(texto_valor)
        if valor is None:
            flash("Valor inválido. Exemplo: 12,50", "erro")
            return voltar(pedido_id)

        cur.execute(
            """
            INSERT INTO itens_pedido
                (pedido_id, tipo, produto_id, quantidade, valor_unitario)
            VALUES (%s, 'pronta_entrega', %s, %s, %s)
            """,
            (pedido_id, produto_id, quantidade, valor),
        )
    db.commit()
    flash("Item adicionado.", "ok")
    return voltar(pedido_id)


@bp.route("/<int:pedido_id>/itens/personalizado", methods=["POST"])
@login_required
def item_personalizado(pedido_id):
    db = get_db()
    with db.cursor() as cur:
        if not pedido_aberto(cur, pedido_id):
            flash("Este pedido não aceita mais alterações nos itens.", "erro")
            return voltar(pedido_id)

        tipo_id = ler_inteiro(request.form.get("tipo_id", ""))
        descricao = request.form.get("descricao", "").strip()
        quantidade = ler_quantidade(request.form.get("quantidade", "1") or "1")
        valor = ler_valor(request.form.get("valor", ""))

        if not descricao or len(descricao) > 1000:
            flash("Descreva a peça (até 1000 caracteres).", "erro")
            return voltar(pedido_id)
        if quantidade is None:
            flash("Quantidade inválida.", "erro")
            return voltar(pedido_id)
        if valor is None:
            flash("Informe o valor combinado. Exemplo: 280,00", "erro")
            return voltar(pedido_id)

        cur.execute("SELECT 1 FROM tipos_personalizado WHERE id = %s", (tipo_id,))
        if cur.fetchone() is None:
            flash("Escolha o tipo da peça.", "erro")
            return voltar(pedido_id)

        cur.execute(
            """
            INSERT INTO itens_pedido
                (pedido_id, tipo, tipo_personalizado_id, descricao,
                 quantidade, valor_unitario)
            VALUES (%s, 'personalizado', %s, %s, %s, %s)
            """,
            (pedido_id, tipo_id, descricao, quantidade, valor),
        )
    db.commit()
    flash("Peça personalizada adicionada.", "ok")
    return voltar(pedido_id)


@bp.route("/<int:pedido_id>/itens/<int:item_id>/remover", methods=["POST"])
@login_required
def item_remover(pedido_id, item_id):
    db = get_db()
    with db.cursor() as cur:
        if not pedido_aberto(cur, pedido_id):
            flash("Este pedido não aceita mais alterações nos itens.", "erro")
            return voltar(pedido_id)
        cur.execute(
            "DELETE FROM itens_pedido WHERE id = %s AND pedido_id = %s",
            (item_id, pedido_id),
        )
    db.commit()
    flash("Item removido.", "ok")
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
        cur.execute(
            """
            SELECT status, dados_preenchidos_em
            FROM pedidos
            WHERE id = %s
            FOR UPDATE
            """,
            (pedido_id,),
        )
        pedido = cur.fetchone()
        if pedido is None:
            abort(404)

        if novo_status not in PROXIMOS[pedido["status"]]:
            flash("Essa mudança de status não é permitida.", "erro")
            return voltar(pedido_id)

        # Pedido cancelado depois de o estoque ter sido reservado: devolve as pecas
        if novo_status == "cancelado" and pedido["dados_preenchidos_em"] is not None:
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
            "UPDATE pedidos SET status = %s WHERE id = %s", (novo_status, pedido_id)
        )
    db.commit()
    flash("Status atualizado.", "ok")
    return voltar(pedido_id)
