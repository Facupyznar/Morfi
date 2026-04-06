import uuid

from flask import Flask
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect

from app.config import Config
from app.database import db
from app.models.user import User
from app.routes.admin import admin_bp
from app.routes.auth import auth_bp
from app.routes.home import home_bp
from app.routes.profile import profile_bp
from app.routes.system import system_bp


def create_app():
    flask_app = Flask(__name__)
    flask_app.config.from_object(Config)

    csrf = CSRFProtect()
    csrf.init_app(flask_app)
    db.init_app(flask_app)

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
    flask_app.register_blueprint(admin_bp)
    flask_app.register_blueprint(home_bp)
    flask_app.register_blueprint(profile_bp)
    flask_app.register_blueprint(system_bp)


    return flask_app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
