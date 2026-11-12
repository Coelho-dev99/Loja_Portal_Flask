import os
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
