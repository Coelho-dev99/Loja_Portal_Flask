"""Servidor de DESENVOLVIMENTO (no seu computador).

Para publicar o site, NAO use este arquivo: use o servidor.py (Windows/Linux)
ou o gunicorn (Linux). Veja o README_SEGURANCA.md.
"""
import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    # O modo debug so liga com FLASK_DEBUG=1 no .env local.
    # Em producao ele fica desligado: o depurador do Flask permite executar
    # codigo no servidor para quem conseguir acessa-lo.
    app.run(debug=os.getenv("FLASK_DEBUG", "0") == "1")
