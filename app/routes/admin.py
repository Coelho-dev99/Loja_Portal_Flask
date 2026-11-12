import hmac
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

from app.auth import login_required
from app.db import get_db

bp = Blueprint("admin", __name__, url_prefix="/admin")


# ---------------------------------------------------------------
# Login / logout
# ---------------------------------------------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")

        usuario_ok = hmac.compare_digest(
            usuario.encode(), current_app.config["ADMIN_USUARIO"].encode()
        )

        senha_hash = current_app.config["ADMIN_SENHA_HASH"]
        try:
            senha_ok = bool(senha_hash) and check_password_hash(senha_hash, senha)
        except ValueError:  # hash mal formatado no .env
            senha_ok = False

        if usuario_ok and senha_ok:
            session.clear()
            session["admin"] = True

            # So aceita voltar para caminhos internos do proprio site
            destino = request.args.get("next", "")
            if not destino.startswith("/") or destino.startswith("//"):
                destino = url_for("admin.produtos")
            return redirect(destino)

        flash("Usuário ou senha incorretos.", "erro")

    return render_template("admin/login.html")


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    return redirect(url_for("admin.login"))


@bp.route("/")
@login_required
def inicio():
    return redirect(url_for("admin.produtos"))


# ---------------------------------------------------------------
# Produtos (pronta entrega)
# ---------------------------------------------------------------
def ler_formulario():
    """Le e valida os campos do formulario de produto.

    Retorna (dados, erros). Se a lista de erros estiver vazia, os dados
    estao prontos para ir ao banco.
    """
    nome = request.form.get("nome", "").strip()
    descricao = request.form.get("descricao", "").strip() or None
    foto_url = request.form.get("foto_url", "").strip() or None
    erros = []

    if not nome:
        erros.append("Informe o nome do produto.")
    elif len(nome) > 120:
        erros.append("O nome pode ter no máximo 120 caracteres.")

    if foto_url and len(foto_url) > 255:
        erros.append("O link da foto é longo demais (máximo 255 caracteres).")

    try:
        preco = Decimal(request.form.get("preco", "").strip().replace(",", "."))
        if not preco.is_finite() or preco < 0 or preco > Decimal("99999999.99"):
            raise InvalidOperation
        preco = preco.quantize(Decimal("0.01"))
    except InvalidOperation:
        preco = None
        erros.append("Preço inválido. Exemplo: 12,50")

    try:
        estoque = int(request.form.get("estoque", "").strip() or 0)
        if estoque < 0 or estoque > 1_000_000:
            raise ValueError
    except ValueError:
        estoque = None
        erros.append("Estoque inválido. Use um número inteiro, 0 ou maior.")

    dados = {
        "nome": nome,
        "descricao": descricao,
        "preco": preco,
        "foto_url": foto_url,
        "estoque": estoque,
    }
    return dados, erros


@bp.route("/produtos")
@login_required
def produtos():
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            """
            SELECT id, nome, preco, estoque, ativo
            FROM produtos
            ORDER BY ativo DESC, nome
            """
        )
        lista = cur.fetchall()
    return render_template("admin/produtos.html", produtos=lista)


@bp.route("/produtos/novo", methods=["GET", "POST"])
@login_required
def produto_novo():
    produto = {}

    if request.method == "POST":
        dados, erros = ler_formulario()

        if not erros:
            db = get_db()
            with db.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO produtos (nome, descricao, preco, foto_url, estoque)
                    VALUES (%(nome)s, %(descricao)s, %(preco)s, %(foto_url)s, %(estoque)s)
                    """,
                    dados,
                )
            db.commit()
            flash("Produto cadastrado.", "ok")
            return redirect(url_for("admin.produtos"))

        for erro in erros:
            flash(erro, "erro")
        produto = dados

    return render_template(
        "admin/produto_form.html", produto=produto, titulo="Novo produto"
    )


@bp.route("/produtos/<int:produto_id>/editar", methods=["GET", "POST"])
@login_required
def produto_editar(produto_id):
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT * FROM produtos WHERE id = %s", (produto_id,))
        produto = cur.fetchone()

    if produto is None:
        abort(404)

    if request.method == "POST":
        dados, erros = ler_formulario()

        if not erros:
            dados["id"] = produto_id
            with db.cursor() as cur:
                cur.execute(
                    """
                    UPDATE produtos
                    SET nome = %(nome)s,
                        descricao = %(descricao)s,
                        preco = %(preco)s,
                        foto_url = %(foto_url)s,
                        estoque = %(estoque)s
                    WHERE id = %(id)s
                    """,
                    dados,
                )
            db.commit()
            flash("Produto atualizado.", "ok")
            return redirect(url_for("admin.produtos"))

        for erro in erros:
            flash(erro, "erro")
        produto = dados

    return render_template(
        "admin/produto_form.html", produto=produto, titulo="Editar produto"
    )


@bp.route("/produtos/<int:produto_id>/alternar", methods=["POST"])
@login_required
def produto_alternar(produto_id):
    """Oculta ou mostra o produto na vitrine (nao apaga, para manter o historico)."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute(
            "UPDATE produtos SET ativo = NOT ativo WHERE id = %s", (produto_id,)
        )
    db.commit()
    return redirect(url_for("admin.produtos"))


# ---------------------------------------------------------------
# Tipos de peca personalizada (tapete, quadro, moldura...)
# ---------------------------------------------------------------
@bp.route("/tipos", methods=["GET", "POST"])
@login_required
def tipos():
    db = get_db()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()

        if not nome:
            flash("Informe o nome do tipo.", "erro")
        elif len(nome) > 60:
            flash("O nome do tipo pode ter no máximo 60 caracteres.", "erro")
        else:
            with db.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM tipos_personalizado WHERE lower(nome) = lower(%s)",
                    (nome,),
                )
                if cur.fetchone():
                    flash("Esse tipo já existe.", "erro")
                else:
                    cur.execute(
                        "INSERT INTO tipos_personalizado (nome) VALUES (%s)", (nome,)
                    )
                    db.commit()
                    flash("Tipo cadastrado.", "ok")
        return redirect(url_for("admin.tipos"))

    with db.cursor() as cur:
        cur.execute(
            """
            SELECT t.id, t.nome, COUNT(i.id) AS usos
            FROM tipos_personalizado t
            LEFT JOIN itens_pedido i ON i.tipo_personalizado_id = t.id
            GROUP BY t.id
            ORDER BY t.nome
            """
        )
        lista = cur.fetchall()
    return render_template("admin/tipos.html", tipos=lista)
