import enum
import uuid
from datetime import date, datetime

from flask_login import UserMixin
from geoalchemy2 import Geometry
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.hybrid import hybrid_property
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
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    birth_date = db.Column(db.Date)

    def __init__(
        self,
        username,
        email,
        password,
        name=None,
        rol=Role.COMENSAL,
        ubicacion=None,
        birth_date=None,
        is_admin=False,
    ):
        self.username = username.strip()
        self.email = email.strip().lower()
        self.name = name.strip() if isinstance(name, str) and name.strip() else None
        self.rol = rol if isinstance(rol, Role) else Role(rol)
        self.password = password
        self.is_admin = bool(is_admin)
        self.birth_date = self.parse_birth_date(birth_date)
        if ubicacion is not None:
            self.ubicacion = ubicacion

    @staticmethod
    def parse_birth_date(value):
        if value is None or value == "":
            return None
        if isinstance(value, date) and not isinstance(value, datetime):
            return value
        if isinstance(value, datetime):
            return value.date()
        if not isinstance(value, str):
            raise ValueError("La fecha de nacimiento no tiene un formato válido.")

        months = {
            "enero": 1,
            "febrero": 2,
            "marzo": 3,
            "abril": 4,
            "mayo": 5,
            "junio": 6,
            "julio": 7,
            "agosto": 8,
            "septiembre": 9,
            "setiembre": 9,
            "octubre": 10,
            "noviembre": 11,
            "diciembre": 12,
        }

        normalized = " ".join(value.strip().lower().split())
        for separator in ("-", "/", "."):
            try:
                return datetime.strptime(normalized, f"%d{separator}%m{separator}%Y").date()
            except ValueError:
                pass

        parts = normalized.split(" ")
        if len(parts) == 3 and parts[1] in months:
            return date(int(parts[2]), months[parts[1]], int(parts[0]))

        raise ValueError("La fecha de nacimiento no tiene un formato válido.")

    @hybrid_property
    def age(self):
        if not self.birth_date:
            return None
        today = date.today()
        years = today.year - self.birth_date.year
        if (today.month, today.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years

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
