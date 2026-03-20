from database import db
import uuid
from sqlalchemy.dialects.postgresql import UUID
from geoalchemy2 import Geometry
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

class User(db.Model, UserMixin):
    __tablename__ = 'User'

    user_id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    username = db.Column(db.String(100), unique=True, nullable=False)
    name = db.Column(db.String(100))
    email = db.Column(db.String(255), unique=True, nullable=False)
    password = db.Column(db.String(255), nullable=False)
    ubicacion = db.Column(Geometry('POINT')) 
    nivel = db.Column(db.Numeric(3, 2), default=5.0)
    foto_perfil = db.Column(db.String(255))
    rol = db.Column(db.Enum('comensal', 'socio_restaurante', 'admin_global', name='user_roles'))

    def __init__(self, username, email, password, name=None, rol='comensal'):
        self.username = username
        self.email = email
        self.password = generate_password_hash(password)
        self.name = name
        self.rol = rol

    def check_password(self, password):
        return check_password_hash(self.password, password)
    
    def get_id(self):
        return str(self.user_id)
