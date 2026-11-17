"""Servidor de PRODUCAO (Windows e Linux), usando o waitress.

Uso:
    python servidor.py

Por padrao escuta so em 127.0.0.1:8000 (acesso local), que e o correto quando
ha um proxy, tunel ou nginx na frente. Para mudar: HOST e PORT no .env.

No Linux voce pode usar o gunicorn no lugar:
    gunicorn -w 1 --threads 8 -b 127.0.0.1:8000 run:app
(use 1 processo: o limitador de tentativas guarda a contagem na memoria.)
"""
import os

from waitress import serve

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    porta = int(os.getenv("PORT", "8000"))
    print(f"Site no ar em http://{host}:{porta}  (Ctrl+C para parar)")
    serve(app, host=host, port=porta, threads=8)
