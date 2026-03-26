import uuid

from sqlalchemy import func
from werkzeug.security import check_password_hash

from app.models.user import Role, User


class ModelUser:
    @staticmethod
    def get_by_id(db, user_id):
        try:
            normalized_id = uuid.UUID(str(user_id))
        except (TypeError, ValueError, AttributeError):
            return None
        return db.session.get(User, normalized_id)

    @staticmethod
    def login(db, username, password):
        normalized_username = (username or "").strip()
        if not normalized_username or not isinstance(password, str) or not password:
            return None

        user = (
            db.session.query(User)
            .filter(func.lower(User.username) == normalized_username.lower())
            .first()
        )
        if user and check_password_hash(user.password_hash, password):
            return user
        return None

    @staticmethod
    def register(db, username, email, password, name=None, birth_date=None, rol=Role.COMENSAL):
        normalized_username = (username or "").strip()
        normalized_email = (email or "").strip().lower()
        normalized_name = (name or "").strip() or None

        if not normalized_username:
            raise ValueError("El nombre de usuario es obligatorio.")
        if not normalized_email:
            raise ValueError("El correo electrónico es obligatorio.")
        if not isinstance(password, str) or not password:
            raise ValueError("La contraseña es obligatoria.")

        if db.session.query(User).filter(func.lower(User.username) == normalized_username.lower()).first():
            raise ValueError("El nombre de usuario ya está en uso.")
        if db.session.query(User).filter(func.lower(User.email) == normalized_email.lower()).first():
            raise ValueError("El correo electrónico ya está registrado.")

        user = User(
            username=normalized_username,
            email=normalized_email,
            password=password,
            name=normalized_name,
            birth_date=birth_date,
            rol=rol,
        )
        db.session.add(user)
        db.session.commit()
        return user
