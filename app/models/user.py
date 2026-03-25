import enum
import uuid

from flask_login import UserMixin
from geoalchemy2 import Geometry
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from werkzeug.security import check_password_hash, generate_password_hash

from app.database import db


class Role(enum.Enum):
    COMENSAL = "comensal"
    SOCIO_RESTAURANTE = "socio_restaurante"
    ADMIN_GLOBAL = "admin_global"


class User(db.Model, UserMixin):
    __tablename__ = "User"

    user_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100))
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column("password", db.String(255), nullable=False)
    ubicacion = db.Column(Geometry("POINT", srid=4326))
    nivel = db.Column(db.Numeric(3, 2), nullable=False, default=1.0)
    foto_perfil = db.Column(db.String(255))
    rol = db.Column(
        SqlEnum(
            Role,
            name="user_roles",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=Role.COMENSAL,
    )

    def __init__(self, username, email, password, name=None, rol=Role.COMENSAL, ubicacion=None):
        self.username = username.strip()
        self.email = email.strip().lower()
        self.name = name.strip() if isinstance(name, str) and name.strip() else None
        self.rol = rol if isinstance(rol, Role) else Role(rol)
        self.password = password
        if ubicacion is not None:
            self.ubicacion = ubicacion

    @property
    def password(self):
        return self.password_hash

    @password.setter
    def password(self, raw_password):
        if not isinstance(raw_password, str) or not raw_password:
            raise ValueError("La contraseña es obligatoria.")
        self.password_hash = generate_password_hash(raw_password, method="pbkdf2:sha256")

    def check_password(self, password):
        if not self.password_hash or not isinstance(password, str):
            return False
        return check_password_hash(self.password_hash, password)

    def get_id(self):
        return str(self.user_id)
