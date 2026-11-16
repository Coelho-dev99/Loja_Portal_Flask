import os
import re
from dotenv import load_dotenv

load_dotenv()


class Config:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-troque-isto")

    # Banco de dados
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "loja_portal")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASSWORD = os.getenv("DB_PASSWORD", "")

    # Painel administrativo (a senha fica guardada como hash, nunca em texto)
    ADMIN_USUARIO = os.getenv("ADMIN_USUARIO", "admin")
    ADMIN_SENHA_HASH = os.getenv("ADMIN_SENHA_HASH", "")

    # Cookie de sessao
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"

    # Limite do total enviado numa requisicao (fotos dos produtos)
    MAX_CONTENT_LENGTH = 40 * 1024 * 1024

    # Loja
    INSTAGRAM_USUARIO = os.getenv("INSTAGRAM_USUARIO", "portal_la.b")

    # Em producao (site com HTTPS), defina COOKIES_SEGUROS=1 no .env
    SESSION_COOKIE_SECURE = os.getenv("COOKIES_SEGUROS", "0") == "1"

    # Frete automatico (Melhor Envio)
    MELHOR_ENVIO_CLIENT_ID = os.getenv("MELHOR_ENVIO_CLIENT_ID", "").strip()
    MELHOR_ENVIO_CLIENT_SECRET = os.getenv("MELHOR_ENVIO_CLIENT_SECRET", "").strip()
    MELHOR_ENVIO_REDIRECT_URI = os.getenv("MELHOR_ENVIO_REDIRECT_URI", "").strip()
    MELHOR_ENVIO_AMBIENTE = os.getenv("MELHOR_ENVIO_AMBIENTE", "producao").strip().lower()
    CEP_ORIGEM = re.sub(r"\D", "", os.getenv("CEP_ORIGEM", ""))
    CONTATO_API_EMAIL = os.getenv("CONTATO_API_EMAIL", "").strip()
