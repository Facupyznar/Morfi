import uuid

from flask import Flask
from flask_login import LoginManager

from app.config import Config
from app.database import db, ensure_menu_schema, ensure_user_schema, ensure_wishlist_schema
from app.helpers.mail import mail
from app.helpers.oauth import init_oauth
from app.helpers.security import csrf
from app.helpers.markdown import render_markdown
from app.models.user import User
from app.routes.admin import admin_bp
from app.routes.admin import system as admin_routes
from app.routes.auth import auth_bp
from app.routes.restaurante import restaurante_bp
from app.routes.restaurante import dashboard as restaurante_routes
from app.routes.restaurante import reservas_routes as restaurante_reservas_routes
from app.routes.restaurante import beneficios_routes as restaurante_beneficios_routes
from app.routes.restaurante import ofertas_routes as restaurante_ofertas_routes
from app.routes.restaurante import exportar_routes as restaurante_exportar_routes
from app.routes.usuario import usuario_bp
from app.routes.usuario import home as usuario_home_routes
from app.routes.usuario import profile as usuario_profile_routes
from app.routes.usuario import notifications as usuario_notifications_routes
from app.routes.usuario import promos as usuario_promos_routes
from app.routes.usuario import contacts as usuario_contacts_routes


def create_app():
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)

    csrf.init_app(flask_app)
    db.init_app(flask_app)
    mail.init_app(flask_app)
    init_oauth(flask_app)

    with flask_app.app_context():
        db.create_all()
        ensure_user_schema()
        ensure_menu_schema()
        ensure_wishlist_schema()

    login_manager = LoginManager()
    login_manager.login_view = "auth.login"
    login_manager.init_app(flask_app)

    flask_app.add_template_filter(render_markdown, "markdown")

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