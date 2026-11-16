import hmac

from flask import (
    Blueprint,
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
from app.util import slugify

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
                destino = url_for("admin_pedidos.lista")
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
    return redirect(url_for("admin_pedidos.lista"))


# ---------------------------------------------------------------
# Tipos de peca personalizada (usados no relatorio mensal)
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
            SELECT t.id, t.nome,
                   (SELECT COUNT(*) FROM itens_pedido i
                    WHERE i.tipo_personalizado_id = t.id) AS usos
            FROM tipos_personalizado t
            ORDER BY t.nome
            """
        )
        lista = cur.fetchall()
    return render_template("admin/tipos.html", tipos=lista)


# ---------------------------------------------------------------
# Categorias do catalogo (Tapetes, Quadros, Porta-copos...)
# ---------------------------------------------------------------
@bp.route("/categorias", methods=["GET", "POST"])
@login_required
def categorias():
    db = get_db()

    if request.method == "POST":
        nome = request.form.get("nome", "").strip()
        slug = slugify(nome)

        if not nome or not slug:
            flash("Informe o nome da categoria.", "erro")
        elif len(nome) > 60:
            flash("O nome da categoria pode ter no máximo 60 caracteres.", "erro")
        else:
            with db.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM categorias WHERE slug = %s OR lower(nome) = lower(%s)",
                    (slug, nome),
                )
                if cur.fetchone():
                    flash("Essa categoria já existe.", "erro")
                else:
                    cur.execute(
                        "INSERT INTO categorias (nome, slug) VALUES (%s, %s)",
                        (nome, slug),
                    )
                    db.commit()
                    flash("Categoria cadastrada.", "ok")
        return redirect(url_for("admin.categorias"))

    with db.cursor() as cur:
        cur.execute(
            """
            SELECT c.id, c.nome, COUNT(p.id) AS produtos
            FROM categorias c
            LEFT JOIN produtos p ON p.categoria_id = c.id
            GROUP BY c.id
            ORDER BY c.nome
            """
        )
        lista = cur.fetchall()
    return render_template("admin/categorias.html", categorias=lista)


@bp.route("/categorias/<int:categoria_id>/excluir", methods=["POST"])
@login_required
def categoria_excluir(categoria_id):
    db = get_db()
    with db.cursor() as cur:
        cur.execute("DELETE FROM categorias WHERE id = %s", (categoria_id,))
    db.commit()
    flash("Categoria excluída. Os produtos dela ficaram sem categoria.", "ok")
    return redirect(url_for("admin.categorias"))
