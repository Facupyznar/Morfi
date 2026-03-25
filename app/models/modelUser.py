import uuid

from geoalchemy2 import WKTElement
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.database import db
from app.models.user import Role, User


class ModelUser:
    @staticmethod
    def _normalize_username(username):
        return username.strip()

    @staticmethod
    def _normalize_email(email):
        return email.strip().lower()

    @staticmethod
    def _normalize_name(name):
        if name is None:
            return None
        normalized = name.strip()
        return normalized or None

    @staticmethod
    def _normalize_role(rol):
        if rol is None:
            return Role.COMENSAL
        if isinstance(rol, Role):
            return rol
        return Role(str(rol).strip())

    @staticmethod
    def _normalize_ubicacion(ubicacion):
        if ubicacion is None:
            return None
        if isinstance(ubicacion, str):
            normalized = ubicacion.strip()
            if not normalized:
                return None
            srid = 4326
            geometry_value = normalized
            if normalized.upper().startswith("SRID="):
                prefix, _, geometry_value = normalized.partition(";")
                try:
                    srid = int(prefix.split("=", 1)[1])
                except ValueError as ex:
                    raise ValueError("La ubicación no tiene un SRID válido.") from ex
            return WKTElement(geometry_value, srid=srid)
        return ubicacion

    @classmethod
    def login(cls, username, password):
        username = cls._normalize_username(username or "")
        if not username or not isinstance(password, str) or not password:
            return None
        user = User.query.filter(func.lower(User.username) == username.lower()).first()
        if user and user.check_password(password):
            return user
        return None

    @classmethod
    def get_by_id(cls, user_id):
        try:
            normalized_id = uuid.UUID(str(user_id))
        except (TypeError, ValueError, AttributeError):
            return None
        return db.session.get(User, normalized_id)

    @classmethod
    def register(cls, username, email, password, name=None, rol=Role.COMENSAL, ubicacion=None):
        normalized_username = cls._normalize_username(username or "")
        normalized_email = cls._normalize_email(email or "")
        normalized_name = cls._normalize_name(name)
        normalized_role = cls._normalize_role(rol)
        normalized_ubicacion = cls._normalize_ubicacion(ubicacion)

        if not normalized_username:
            raise ValueError("El nombre de usuario es obligatorio.")
        if not normalized_email:
            raise ValueError("El correo electrónico es obligatorio.")
        if not isinstance(password, str) or not password:
            raise ValueError("La contraseña es obligatoria.")

        if User.query.filter(func.lower(User.username) == normalized_username.lower()).first():
            raise ValueError("El nombre de usuario ya está en uso.")
        if User.query.filter(func.lower(User.email) == normalized_email.lower()).first():
            raise ValueError("El correo electrónico ya está registrado.")

        new_user = User(
            username=normalized_username,
            email=normalized_email,
            password=password,
            name=normalized_name,
            rol=normalized_role,
            ubicacion=normalized_ubicacion,
        )

        try:
            db.session.add(new_user)
            db.session.commit()
        except IntegrityError as ex:
            db.session.rollback()
            raise ValueError("El usuario no pudo registrarse porque ya existe un registro con esos datos.") from ex
        except Exception:
            db.session.rollback()
            raise

        return new_user
