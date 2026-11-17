import os

from flask import Flask, g

from config import Config
from app import carrinho
from app.db import close_db
from app.status import ROTULOS


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Fecha a conexao com o banco ao final de cada requisicao
    app.teardown_appcontext(close_db)

    @app.errorhandler(413)
    def arquivo_grande(e):
        return "As fotos são grandes demais. Envie até 40 MB de uma vez.", 413

    # ---- Dados disponiveis em todos os templates ----
    @app.context_processor
    def dados_da_loja():
        return {
            "loja_nome": "Portal Lãb",
            "instagram_usuario": app.config["INSTAGRAM_USUARIO"],
            "carrinho_qtd": carrinho.quantidade_total(),
            "tem_logo": os.path.exists(os.path.join(app.static_folder, "logo.png")),
        }

    # ---- Cookie do carrinho ----
    @app.after_request
    def cookie_do_carrinho(resposta):
        token = g.get("carrinho_cookie")
        if token:
            resposta.set_cookie(
                carrinho.COOKIE,
                token,
                max_age=carrinho.VALIDADE_SEGUNDOS,
                httponly=True,
                samesite="Lax",
                secure=app.config["SESSION_COOKIE_SECURE"],
            )
        elif g.get("carrinho_limpar"):
            resposta.delete_cookie(carrinho.COOKIE)
        return resposta

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

    @app.template_filter("dia_br")
    def dia_br(valor):
        return valor.strftime("%d/%m/%Y") if valor else ""

    @app.template_filter("rotulo_status")
    def rotulo_status(status):
        return ROTULOS.get(status, status)

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
    from app.routes.loja import bp as loja_bp
    from app.routes.admin import bp as admin_bp
    from app.routes.admin_produtos import bp as admin_produtos_bp
    from app.routes.admin_pedidos import bp as admin_pedidos_bp
    from app.routes.checkout import bp as checkout_bp
    from app.routes.acompanhar import bp as acompanhar_bp
    from app.routes.admin_relatorios import bp as admin_relatorios_bp
    from app.routes.admin_clientes import bp as admin_clientes_bp
    from app.routes.admin_melhor_envio import bp as admin_melhor_envio_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(loja_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(admin_produtos_bp)
    app.register_blueprint(admin_pedidos_bp)
    app.register_blueprint(checkout_bp)
    app.register_blueprint(acompanhar_bp)
    app.register_blueprint(admin_relatorios_bp)
    app.register_blueprint(admin_clientes_bp)
    app.register_blueprint(admin_melhor_envio_bp)

    return app
