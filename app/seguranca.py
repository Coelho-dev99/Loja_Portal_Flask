"""Cabecalhos de seguranca de todas as respostas do site.

- Content-Security-Policy: o navegador so executa scripts do proprio site ou
  que tragam o codigo (nonce) gerado a cada pagina. Isso barra a maior parte
  dos ataques de XSS, mesmo que um dia um campo deixe de ser escapado.
- X-Frame-Options / frame-ancestors: ninguem consegue colocar o site dentro de
  outra pagina (clickjacking).
- X-Content-Type-Options, Referrer-Policy, Permissions-Policy.
- Strict-Transport-Security: so quando o acesso ja e por HTTPS.
- Cache-Control: no-store nas paginas com dados de clientes, para nao ficarem
  guardadas no navegador (computador compartilhado, botao Voltar).
"""
import secrets

from flask import g, request

# Para onde um formulario pode levar o navegador. O Melhor Envio entra porque
# o botao "Conectar" do painel redireciona para a tela de autorizacao dele.
DESTINOS_DE_FORMULARIO = (
    "'self'",
    "https://melhorenvio.com.br",
    "https://sandbox.melhorenvio.com.br",
)

# Paginas com dados pessoais ou de sessao: nunca guardar em cache
CAMINHOS_SEM_CACHE = ("/admin", "/acompanhar", "/pedido-enviado", "/finalizar", "/frete")

TURNSTILE = "https://challenges.cloudflare.com"


def montar_csp(nonce, turnstile_ativo=False):
    extra = f" {TURNSTILE}" if turnstile_ativo else ""
    frames = TURNSTILE if turnstile_ativo else "'none'"
    return "; ".join(
        [
            "default-src 'self'",
            f"script-src 'self' 'nonce-{nonce}'{extra}",
            "script-src-attr 'none'",  # sem onclick="..." e parecidos
            "style-src 'self'",
            "img-src 'self' data:",
            f"connect-src 'self' https://viacep.com.br{extra}",
            f"frame-src {frames}",
            "object-src 'none'",
            "base-uri 'none'",
            "frame-ancestors 'none'",
            "form-action " + " ".join(DESTINOS_DE_FORMULARIO),
        ]
    )


def init_seguranca(app):
    @app.before_request
    def gerar_nonce():
        g.csp_nonce = secrets.token_urlsafe(16)

    @app.context_processor
    def expor_nonce():
        return {"csp_nonce": g.get("csp_nonce", "")}

    @app.after_request
    def cabecalhos(resposta):
        turnstile = bool(
            app.config.get("TURNSTILE_SITE_KEY") and app.config.get("TURNSTILE_SECRET_KEY")
        )
        resposta.headers["Content-Security-Policy"] = montar_csp(
            g.get("csp_nonce", ""), turnstile
        )
        resposta.headers["X-Content-Type-Options"] = "nosniff"
        resposta.headers["X-Frame-Options"] = "DENY"
        resposta.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        resposta.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), payment=(), usb=()"
        )
        if request.is_secure:
            resposta.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.path.startswith(CAMINHOS_SEM_CACHE):
            resposta.headers["Cache-Control"] = "no-store"
        return resposta
