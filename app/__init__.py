import os

import psycopg2
from flask import Flask, g
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config
from app import carrinho, turnstile
from app.db import close_db
from app.imagens import url_foto
from app.seguranca import init_seguranca
from app.status import ROTULOS

MODOS_PROXY = {"nenhum", "proxy", "cloudflare"}
SSLMODES_VALIDOS = {"", "disable", "allow", "prefer", "require", "verify-ca", "verify-full"}


def _pagina_erro(codigo, titulo, texto):
    """Pagina de erro simples, SEM consultar o banco.

    Se o banco estiver fora do ar, uma pagina de erro que dependesse dele
    (como o contador do carrinho) falharia de novo. Por isso o HTML e montado
    aqui, so com o CSS do site.
    """
    html = (
        '<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        '<meta name="robots" content="noindex">'
        f"<title>{titulo} · Portal Lãb</title>"
        '<link rel="stylesheet" href="/static/loja.css"></head>'
        f'<body><main class="miolo erro-pagina"><h1>{titulo}</h1><p>{texto}</p>'
        '<p><a class="botao" href="/">Voltar à loja</a></p></main></body></html>'
    )
    return html, codigo


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # ---- Proxy na frente do site (Cloudflare, nginx, Render...) ----
    modo_proxy = app.config["PROXY_MODO"]
    if modo_proxy not in MODOS_PROXY:
        raise RuntimeError(
            f'PROXY_MODO invalido: "{modo_proxy}". Use: nenhum, proxy ou cloudflare.'
        )
    if app.config["DB_SSLMODE"] not in SSLMODES_VALIDOS:
        raise RuntimeError(
            f'DB_SSLMODE invalido: "{app.config["DB_SSLMODE"]}". '
            "Deixe em branco ou use: disable, allow, prefer, require, verify-ca, verify-full."
        )
    if modo_proxy != "nenhum":
        # Confia em UM proxy: acerta o IP (remote_addr) e o https nos links gerados.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    if not app.debug and not app.config["SESSION_COOKIE_SECURE"]:
        app.logger.warning(
            "ATENCAO: COOKIES_SEGUROS=0. Os cookies de login e do carrinho podem "
            "trafegar sem HTTPS. Use isso so no seu computador (FLASK_DEBUG=1)."
        )

    # ---- Cabecalhos de seguranca (CSP, anti-clickjacking, HSTS...) ----
    init_seguranca(app)

    # ---- Protecao CSRF: todo formulario POST precisa do token da sessao ----
    CSRFProtect(app)

    @app.errorhandler(CSRFError)
    def csrf_invalido(e):
        return (
            "O formulário expirou ou não é válido. "
            "Volte à página anterior, recarregue e tente de novo.",
            400,
        )

    # Fecha a conexao com o banco ao final de cada requisicao
    app.teardown_appcontext(close_db)

    @app.errorhandler(413)
    def arquivo_grande(e):
        return "As fotos são grandes demais. Envie até 40 MB de uma vez.", 413

    # ---- Paginas de erro ----
    @app.errorhandler(404)
    def nao_encontrado(e):
        return _pagina_erro(
            404,
            "Página não encontrada",
            "Esse endereço não existe ou a peça não está mais disponível.",
        )

    @app.errorhandler(psycopg2.OperationalError)
    def banco_indisponivel(e):
        # Banco fora do ar ou conexao que caiu: o visitante pode tentar de novo
        app.logger.exception("Banco de dados indisponivel")
        return _pagina_erro(
            503,
            "Estamos com uma instabilidade",
            "Não conseguimos carregar esta página agora. Aguarde um instante e tente de novo.",
        )

    @app.errorhandler(500)
    def erro_interno(e):
        return _pagina_erro(
            500,
            "Algo deu errado",
            "Tivemos um problema do nosso lado. Tente de novo em instantes ou fale com a gente pelo Instagram.",
        )

    # ---- Dados disponiveis em todos os templates ----
    @app.context_processor
    def dados_da_loja():
        return {
            "loja_nome": "Portal Lãb",
            "instagram_usuario": app.config["INSTAGRAM_USUARIO"],
            "carrinho_qtd": carrinho.quantidade_total(),
            "tem_logo": os.path.exists(os.path.join(app.static_folder, "logo.png")),
            "turnstile_site_key": (
                app.config["TURNSTILE_SITE_KEY"] if turnstile.ativo() else ""
            ),
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

    app.jinja_env.globals["url_foto"] = url_foto

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
