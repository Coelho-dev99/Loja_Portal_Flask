from flask import Blueprint, abort, render_template, request, send_file

from app import excel, relatorios
from app.auth import login_required
from app.db import get_db
from app.routes.admin_relatorios import TIPO_XLSX

bp = Blueprint("admin_clientes", __name__, url_prefix="/admin/clientes")


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
    return render_template("admin/cliente_detalhe.html", **dados)
