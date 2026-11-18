from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from app import excel, relatorios
from app.auth import login_required
from app.db import get_db
from app.routes.admin_relatorios import TIPO_XLSX

bp = Blueprint("admin_clientes", __name__, url_prefix="/admin/clientes")

NOME_ANONIMO = "Cliente removido"

# Mantem cidade e estado nos pedidos antigos (so para saber de que regioes voce vende).
# Mude para False se preferir apagar tambem esses dois campos.
MANTER_CIDADE_ESTADO = True


@bp.route("")
@login_required
def lista():
    termo = request.args.get("q", "").strip()[:60]
    with get_db().cursor() as cur:
        clientes = relatorios.lista_de_clientes(cur, termo)
    return render_template("admin/clientes.html", clientes=clientes, termo=termo)


@bp.route("/exportar")
@login_required
def exportar():
    with get_db().cursor() as cur:
        clientes = relatorios.lista_de_clientes(cur, "", limite=100000)
    return send_file(
        excel.lista_de_clientes(clientes),
        mimetype=TIPO_XLSX,
        as_attachment=True,
        download_name="clientes.xlsx",
    )


@bp.route("/<int:cliente_id>")
@login_required
def detalhe(cliente_id):
    with get_db().cursor() as cur:
        dados = relatorios.detalhe_do_cliente(cur, cliente_id)
    if dados is None:
        abort(404)
    return render_template(
        "admin/cliente_detalhe.html",
        **dados,
        anonimizado=dados["cliente"]["nome"] == NOME_ANONIMO,
    )


@bp.route("/<int:cliente_id>/anonimizar", methods=["POST"])
@login_required
def anonimizar(cliente_id):
    """Atende o pedido de exclusao de dados (LGPD) sem perder o historico de vendas.

    Apaga tudo o que identifica a pessoa (nome, telefone, Instagram, endereco,
    observacoes e descricoes de pecas personalizadas) e mantem os pedidos,
    valores e datas, para os seus relatorios continuarem corretos.
    """
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT id, nome FROM clientes WHERE id = %s FOR UPDATE", (cliente_id,))
        cliente = cur.fetchone()
        if cliente is None:
            abort(404)

        voltar = redirect(url_for("admin_clientes.detalhe", cliente_id=cliente_id))
        if cliente["nome"] == NOME_ANONIMO:
            flash("Os dados deste cliente já foram removidos.", "ok")
            return voltar

        # Nao apaga dados de quem ainda tem pedido a entregar
        cur.execute(
            """SELECT count(*) AS n FROM pedidos
               WHERE cliente_id = %s AND status NOT IN ('concluido', 'cancelado')""",
            (cliente_id,),
        )
        if cur.fetchone()["n"]:
            flash(
                "Este cliente tem pedido em andamento. Conclua ou cancele os pedidos "
                "dele antes de remover os dados.",
                "erro",
            )
            return voltar

        cur.execute(
            "UPDATE clientes SET nome = %s, telefone = %s, instagram = NULL WHERE id = %s",
            (NOME_ANONIMO, f"removido-{cliente_id}", cliente_id),
        )
        cur.execute(
            """UPDATE enderecos
               SET cep = '00000000', rua = 'Removido', numero = '0',
                   tipo_moradia = 'casa', complemento = NULL, bairro = 'Removido'
               WHERE cliente_id = %s""",
            (cliente_id,),
        )
        if not MANTER_CIDADE_ESTADO:
            cur.execute(
                "UPDATE enderecos SET cidade = 'Removido', estado = 'XX' WHERE cliente_id = %s",
                (cliente_id,),
            )
        cur.execute("UPDATE pedidos SET observacoes = NULL WHERE cliente_id = %s", (cliente_id,))
        # A descricao de peca personalizada e texto livre do cliente; fica so um aviso
        cur.execute(
            """UPDATE itens_pedido
               SET descricao = CASE WHEN tipo = 'personalizado' THEN 'Descrição removida' END
               WHERE descricao IS NOT NULL
                 AND pedido_id IN (SELECT id FROM pedidos WHERE cliente_id = %s)""",
            (cliente_id,),
        )
    db.commit()
    current_app.logger.info("Dados do cliente %s foram anonimizados.", cliente_id)
    flash("Dados do cliente removidos. O histórico de pedidos foi mantido sem identificação.", "ok")
    return voltar
