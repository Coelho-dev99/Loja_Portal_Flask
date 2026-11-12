from flask import Blueprint, jsonify

from app.db import get_db

bp = Blueprint("public", __name__)


@bp.route("/")
def home():
    return "Portal La.B - em construcao"


@bp.route("/saude")
def saude():
    """Rota de teste da conexao com o banco. Remover antes de publicar."""
    db = get_db()
    with db.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS total FROM tipos_personalizado")
        total = cur.fetchone()["total"]
    return jsonify(banco="conectado", tipos_personalizado=total)
