import uuid

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from app.config import Config
from app.database import db, ensure_menu_schema
from app.models.user import User
from app.routes.admin import admin_bp
from app.routes.admin import system as admin_routes
from app.routes.auth import auth_bp
from app.routes.restaurante import restaurante_bp
from app.routes.restaurante import dashboard as restaurante_routes
from app.routes.usuario import usuario_bp
from app.routes.usuario import home as usuario_home_routes
from app.routes.usuario import profile as usuario_profile_routes


def create_app():
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)

    csrf = CSRFProtect()
    csrf.init_app(flask_app)
    db.init_app(flask_app)

    with flask_app.app_context():
        db.create_all()
        ensure_menu_schema()

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(flask_app)

    @login_manager.user_loader
    def load_user(user_id):
        try:
            normalized_id = uuid.UUID(str(user_id))
        except (TypeError, ValueError, AttributeError):
            return None
        return db.session.get(User, normalized_id)

    flask_app.register_blueprint(auth_bp)
    flask_app.register_blueprint(usuario_bp)
    flask_app.register_blueprint(restaurante_bp)
    flask_app.register_blueprint(admin_bp)


    return flask_app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
