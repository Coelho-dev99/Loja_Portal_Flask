from flask import Flask

from config import Config
from app.db import close_db
from app.status import ROTULOS


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Fecha a conexao com o banco ao final de cada requisicao
    app.teardown_appcontext(close_db)

    # ---- Filtros usados nos templates ----
    @app.template_filter("brl")
    def brl(valor):
        if valor is None:
            return ""
        texto = f"{valor:,.2f}"
        return texto.replace(",", "X").replace(".", ",").replace("X", ".")

    @app.template_filter("data_br")
    def data_br(valor):
        return valor.strftime("%d/%m/%Y %H:%M") if valor else ""

    @app.template_filter("rotulo_status")
    def rotulo_status(status):
        return ROTULOS.get(status, status)

    @app.template_filter("cpf")
    def cpf_formatado(valor):
        if valor and len(valor) == 11:
            return f"{valor[:3]}.{valor[3:6]}.{valor[6:9]}-{valor[9:]}"
        return valor or ""

    @app.template_filter("fone")
    def fone_formatado(valor):
        if not valor:
            return ""
        if len(valor) == 11:
            return f"({valor[:2]}) {valor[2:7]}-{valor[7:]}"
        if len(valor) == 10:
            return f"({valor[:2]}) {valor[2:6]}-{valor[6:]}"
        return valor

    @app.template_filter("cep")
    def cep_formatado(valor):
        if valor and len(valor) == 8:
            return f"{valor[:5]}-{valor[5:]}"
        return valor or ""

    # ---- Rotas ----
    from app.routes.public import bp as public_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.admin_pedidos import bp as admin_pedidos_bp
    from app.routes.formulario import bp as formulario_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_pedidos_bp)
    app.register_blueprint(formulario_bp)

    return app
