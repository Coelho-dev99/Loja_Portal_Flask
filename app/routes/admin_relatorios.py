from flask import Blueprint, render_template, request, send_file

from app import excel, relatorios
from app.auth import login_required
from app.db import get_db

bp = Blueprint("admin_relatorios", __name__, url_prefix="/admin/relatorios")

TIPO_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


@bp.route("")
@login_required
def mensal():
    mes = relatorios.intervalo(request.args.get("mes"))
    with get_db().cursor() as cur:
        dados = relatorios.relatorio_do_mes(cur, mes)
    return render_template("admin/relatorio.html", **dados)


@bp.route("/exportar")
@login_required
def exportar():
    mes = relatorios.intervalo(request.args.get("mes"))
    with get_db().cursor() as cur:
        dados = relatorios.relatorio_do_mes(cur, mes)
    return send_file(
        excel.relatorio_mensal(dados),
        mimetype=TIPO_XLSX,
        as_attachment=True,
        download_name=f"relatorio-{mes['texto']}.xlsx",
    )
