import time

import psycopg2
import psycopg2.extras
from flask import current_app, g

# Banco na nuvem (Neon) pode demorar um instante para "acordar" depois de um
# tempo parado. Por isso a conexao tem prazo maximo e uma segunda tentativa.
TENTATIVAS_CONEXAO = 2
PAUSA_ENTRE_TENTATIVAS = 1.0  # segundos


def _conectar():
    cfg = current_app.config
    extras = {}
    if cfg["DB_SSLMODE"]:
        extras["sslmode"] = cfg["DB_SSLMODE"]

    ultimo_erro = None
    for tentativa in range(1, TENTATIVAS_CONEXAO + 1):
        try:
            return psycopg2.connect(
                host=cfg["DB_HOST"],
                port=cfg["DB_PORT"],
                dbname=cfg["DB_NAME"],
                user=cfg["DB_USER"],
                password=cfg["DB_PASSWORD"],
                connect_timeout=cfg["DB_CONNECT_TIMEOUT"],
                cursor_factory=psycopg2.extras.RealDictCursor,
                **extras,
            )
        except psycopg2.OperationalError as erro:
            ultimo_erro = erro
            current_app.logger.warning(
                "Falha ao conectar no banco (tentativa %s de %s): %s",
                tentativa,
                TENTATIVAS_CONEXAO,
                str(erro).strip(),
            )
            if tentativa < TENTATIVAS_CONEXAO:
                time.sleep(PAUSA_ENTRE_TENTATIVAS)
    raise ultimo_erro


def get_db():
    """Abre (ou reaproveita) a conexao com o PostgreSQL na requisicao atual."""
    if "db" not in g:
        g.db = _conectar()
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()
