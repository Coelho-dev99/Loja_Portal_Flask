from flask import Blueprint, jsonify

bp = Blueprint("public", __name__)


@bp.route("/healthz")
@bp.route("/saude")  # endereco antigo: continua respondendo (Render, monitores)
def saude():
    """Verificacao de que o site esta no ar.

    De proposito NAO consulta o banco: assim ninguem de fora enxerga dados do
    banco por aqui, e um monitor que chame esta rota o dia todo nao mantem o
    banco acordado (o que gasta o plano gratuito do Neon).
    """
    return jsonify(status="ok")
