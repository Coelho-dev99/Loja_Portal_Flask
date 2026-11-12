from flask import Flask

from config import Config
from app.db import close_db


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Fecha a conexao com o banco ao final de cada requisicao
    app.teardown_appcontext(close_db)

    from app.routes.public import bp as public_bp
    from app.routes.admin import bp as admin_bp

    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp)

    return app
