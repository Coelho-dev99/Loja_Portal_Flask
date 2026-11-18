import os
import re
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()

# Modo de desenvolvimento: so liga se voce definir FLASK_DEBUG=1 no seu .env LOCAL.
# Nunca defina isto no servidor (o depurador do Flask permite executar codigo).
MODO_DEBUG = os.getenv("FLASK_DEBUG", "0") == "1"


def _chave_secreta():
    """Exige uma SECRET_KEY forte. Sem ela o site nao inicia.

    Com a chave a mostra (ou fraca), qualquer pessoa conseguiria forjar um
    login de administrador. Por isso nao existe valor padrao.
    """
    chave = os.getenv("SECRET_KEY", "").strip()
    fraca = (
        len(chave) < 32
        or "troque" in chave.lower()
        or chave.lower().startswith("dev-")
    )
    if fraca:
        raise RuntimeError(
            "SECRET_KEY ausente ou fraca. Gere uma chave e coloque no .env:\n"
            '  python -c "import secrets; print(secrets.token_hex(32))"\n'
            "e copie o resultado para a linha SECRET_KEY=... do arquivo .env "
            "(minimo de 32 caracteres, sem a frase de exemplo)."
        )
    return chave


class Config:
    SECRET_KEY = _chave_secreta()

    # Banco de dados
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "loja_portal")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")
    # Criptografia da conexao com o banco. Deixe em branco se o banco esta na
    # MESMA maquina do site. Se estiver em outro servidor (banco na nuvem),
    # use "require" (ou "verify-full" com certificado).
    DB_SSLMODE = os.getenv("DB_SSLMODE", "").strip().lower()
    # Prazo (segundos) para o banco responder ao conectar. Banco na nuvem pode
    # levar um instante para acordar; 10 s e um bom meio-termo.
    DB_CONNECT_TIMEOUT = int(os.getenv("DB_CONNECT_TIMEOUT", "10") or "10")

    # Painel administrativo (a senha fica guardada como hash, nunca em texto)
    ADMIN_USUARIO = os.getenv("ADMIN_USUARIO", "admin")
    ADMIN_SENHA_HASH = os.getenv("ADMIN_SENHA_HASH", "")

    # Cookie de sessao
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Login do painel expira apos 2 horas SEM uso (o prazo renova a cada clique).
    # So vale para o administrador; a sessao dos clientes nao e afetada.
    PERMANENT_SESSION_LIFETIME = timedelta(hours=2)

    # Limite do total enviado numa requisicao (fotos dos produtos)
    MAX_CONTENT_LENGTH = 40 * 1024 * 1024

    # Fotos dos produtos no Supabase Storage (opcional).
    # Sem SUPABASE_URL e SUPABASE_SECRET_KEY, as fotos ficam em app/static/uploads.
    SUPABASE_URL = os.getenv("SUPABASE_URL", "").strip().rstrip("/")
    # Chave SECRETA (sb_secret_... ou service_role): so no servidor, nunca no git.
    SUPABASE_SECRET_KEY = os.getenv("SUPABASE_SECRET_KEY", "").strip()
    SUPABASE_BUCKET = os.getenv("SUPABASE_BUCKET", "produtos").strip()

    # Loja
    INSTAGRAM_USUARIO = os.getenv("INSTAGRAM_USUARIO", "portal_la.b")

    # Cookies so trafegam por HTTPS. O padrao e SEGURO (1); so o modo de
    # desenvolvimento (FLASK_DEBUG=1, http://localhost) usa 0 por padrao.
    # No servidor nao defina COOKIES_SEGUROS=0.
    SESSION_COOKIE_SECURE = (
        os.getenv("COOKIES_SEGUROS", "0" if MODO_DEBUG else "1") == "1"
    )

    # O CSRF vale enquanto a sessao do visitante valer (formulario aberto por
    # muito tempo, como o de finalizar pedido, nao pode expirar).
    WTF_CSRF_TIME_LIMIT = None

    # Como o site enxerga o IP real do visitante (usado nos limites de tentativas):
    #   "nenhum"     -> acesso direto, sem proxy na frente (padrao)
    #   "proxy"      -> um proxy confiavel na frente (nginx, Render, Railway...) via X-Forwarded-For
    #   "cloudflare" -> atras da Cloudflare (proxy laranja ou Tunnel), via CF-Connecting-IP
    # So use "proxy" ou "cloudflare" se o site NAO puder ser acessado sem passar por eles.
    PROXY_MODO = os.getenv("PROXY_MODO", "nenhum").strip().lower()

    # Anti-robo opcional no checkout (Cloudflare Turnstile, gratuito).
    # Deixe em branco para desligar.
    TURNSTILE_SITE_KEY = os.getenv("TURNSTILE_SITE_KEY", "").strip()
    TURNSTILE_SECRET_KEY = os.getenv("TURNSTILE_SECRET_KEY", "").strip()

    # Frete automatico (Melhor Envio)
    MELHOR_ENVIO_CLIENT_ID = os.getenv("MELHOR_ENVIO_CLIENT_ID", "").strip()
    MELHOR_ENVIO_CLIENT_SECRET = os.getenv("MELHOR_ENVIO_CLIENT_SECRET", "").strip()
    MELHOR_ENVIO_REDIRECT_URI = os.getenv("MELHOR_ENVIO_REDIRECT_URI", "").strip()
    MELHOR_ENVIO_AMBIENTE = os.getenv("MELHOR_ENVIO_AMBIENTE", "producao").strip().lower()
    CEP_ORIGEM = re.sub(r"\D", "", os.getenv("CEP_ORIGEM", ""))
    CONTATO_API_EMAIL = os.getenv("CONTATO_API_EMAIL", "").strip()
