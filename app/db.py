import psycopg2
import psycopg2.extras
from flask import current_app, g


def get_db():
    """Abre (ou reaproveita) a conexao com o PostgreSQL na requisicao atual."""
    if "db" not in g:
        extras = {}
        if current_app.config["DB_SSLMODE"]:
            extras["sslmode"] = current_app.config["DB_SSLMODE"]
        g.db = psycopg2.connect(
            host=current_app.config["DB_HOST"],
            port=current_app.config["DB_PORT"],
            dbname=current_app.config["DB_NAME"],
            user=current_app.config["DB_USER"],
            password=current_app.config["DB_PASSWORD"],
            cursor_factory=psycopg2.extras.RealDictCursor,
            **extras,
        )
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
